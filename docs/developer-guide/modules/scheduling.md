# Scheduling Module

The `src/scheduling/` module orchestrates automated data refresh and model retraining via APScheduler cron jobs: daily bars (5pm ET weekdays), weekly fundamentals (6am Saturday), biweekly alternative data (7am 1st/15th), and weekly XGBoost retraining (2am Sunday). All jobs are idempotent via [Redis](../glossary.md#redis) tracking keys.

## Purpose

The scheduler provides:

- **APScheduler integration** with 4 cron jobs for automated data pipeline
- **Idempotency** via Redis keys (prevents duplicate work on retries)
- **Manual triggers** via API endpoints (for on-demand execution)
- **Lazy imports** in job functions (avoids load-time errors)
- **Market hours safety** (prevents intraday IBKR requests outside 9:30am-5:30pm ET)

## Key Components

### Scheduler Setup

#### `TradingScheduler` (src/scheduling/scheduler.py)

APScheduler instance with 4 jobs.

**Initialization:**
```python
from src.scheduling.scheduler import TradingScheduler

scheduler = TradingScheduler()
scheduler.setup()   # Register jobs
scheduler.start()   # Start background thread
# Jobs run automatically per cron schedules

# On shutdown:
scheduler.stop()
```

**Job Registration:**
```python
scheduler.add_job(
    daily_bars_job,
    trigger="cron",
    hour=17,
    minute=0,
    day_of_week="mon-fri",
    timezone="America/New_York",
    id="daily_bars",
    replace_existing=True
)
```

**Configuration (config/settings.yaml):**
```yaml
scheduler:
  enabled: true
  daily_bars_cron: "0 17 * * 1-5"            # 5pm ET Mon-Fri
  weekly_fundamentals_cron: "0 6 * * 6"      # 6am ET Saturday
  biweekly_altdata_cron: "0 7 1,15 * *"      # 7am ET 1st and 15th
  weekly_retrain_cron: "0 2 * * 0"           # 2am ET Sunday
```

### Job Implementations

All jobs in `src/scheduling/jobs.py`.

#### 1. `daily_bars_job`

**Schedule:** 5pm ET Monday-Friday (after US market close at 4pm ET).

**Purpose:** Fetch daily [OHLCV](../glossary.md#ohlcv) bars for all S&P 500 symbols.

**Data Source:** `AlphaVantageAdapter` (primary) or `IBKRDataAdapter` (fallback).

**Logic:**
```python
async def daily_bars_job() -> None:
    logger.info("job.daily_bars.start")

    # Lazy imports to avoid load-time errors
    from src.core.redis import get_redis
    from src.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
    from src.data.storage import TimeSeriesStorage
    from src.data.universe import SymbolUniverse

    universe = SymbolUniverse()
    symbols = await universe.get_symbols()

    today = date.today()
    end_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)
    start_dt = end_dt - timedelta(days=7)  # 7-day lookback (covers weekends + holidays)

    redis = await get_redis()
    done_key = f"jobs:daily_bars:{today.isoformat()}:done"

    av = AlphaVantageAdapter()
    storage = TimeSeriesStorage()

    fetched = skipped = errors = 0
    for symbol in symbols:
        # Idempotency check
        if await redis.sismember(done_key, symbol):
            skipped += 1
            continue

        try:
            bars = await av.get_historical_bars(symbol, start_dt, end_dt)
            if bars:
                await storage.store_ohlcv(bars)
            await redis.sadd(done_key, symbol)
            await redis.expire(done_key, 90_000)  # 25 hours TTL
            fetched += 1
        except Exception:
            logger.warning("job.daily_bars.symbol_error", symbol=symbol, exc_info=True)
            errors += 1

    logger.info("job.daily_bars.complete", symbols=len(symbols), fetched=fetched, skipped=skipped, errors=errors)
```

**Idempotency Key:** `jobs:daily_bars:{date}:done` (Redis set containing completed symbols).

**TTL:** 25 hours (expires before next day's run).

#### 2. `weekly_fundamentals_job`

**Schedule:** 6am ET Saturday (after market close Friday, before Sunday retraining).

**Purpose:** Fetch fundamental data (P/E, ROE, debt-to-equity, etc.) for all S&P 500 symbols.

**Data Source:** `AlphaVantageAdapter` (Company Overview + Income Statement).

**Logic:**
```python
async def weekly_fundamentals_job() -> None:
    logger.info("job.weekly_fundamentals.start")

    from src.core.redis import get_redis
    from src.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
    from src.data.storage import TimeSeriesStorage
    from src.data.universe import SymbolUniverse

    universe = SymbolUniverse()
    symbols = await universe.get_symbols()

    today = date.today()
    redis = await get_redis()
    week_key = f"{today.year}-W{today.isocalendar()[1]}"  # "2024-W12"
    done_key = f"jobs:weekly_fundamentals:{week_key}:done"

    # Check if job already ran this week
    if await redis.get(done_key):
        logger.info("job.weekly_fundamentals.already_done", week=week_key)
        return

    av = AlphaVantageAdapter()
    storage = TimeSeriesStorage()

    fetched = errors = 0
    for symbol in symbols:
        try:
            fundamentals = await av.get_fundamentals(symbol)
            if fundamentals:
                await storage.store_fundamentals([fundamentals])
            fetched += 1
        except Exception:
            logger.warning("job.weekly_fundamentals.symbol_error", symbol=symbol, exc_info=True)
            errors += 1

    await redis.set(done_key, "1", ex=8 * 86400)  # 8 days TTL
    logger.info("job.weekly_fundamentals.complete", symbols=len(symbols), fetched=fetched, errors=errors)
```

**Idempotency Key:** `jobs:weekly_fundamentals:{year}-W{week_number}:done` (Redis string).

**TTL:** 8 days (expires before next weekly run).

#### 3. `biweekly_altdata_job`

**Schedule:** 7am ET on 1st and 15th of each month.

**Purpose:** Fetch alternative data: SEC Form 4 (insider trades) and FINRA short interest.

**Data Sources:**
- `EdgarAdapter` for Form 4 filings (insider transactions)
- `FinraAdapter` for short interest reports

**Logic:**
```python
async def biweekly_altdata_job() -> None:
    logger.info("job.biweekly_altdata.start")

    from src.core.redis import get_redis
    from src.data.adapters.edgar_adapter import EdgarAdapter
    from src.data.adapters.finra_adapter import FinraAdapter
    from src.data.storage import TimeSeriesStorage
    from src.data.universe import SymbolUniverse

    redis = await get_redis()
    last_run = await redis.get("jobs:altdata:last_run")

    # Only run if > 12 days since last run (prevents double-trigger)
    if last_run:
        last_run_dt = datetime.fromisoformat(last_run)
        if (datetime.now(timezone.utc) - last_run_dt).days < 12:
            logger.info("job.biweekly_altdata.skipped_recent_run")
            return

    universe = SymbolUniverse()
    symbols = await universe.get_symbols()

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)  # 30-day lookback

    edgar = EdgarAdapter()
    finra = FinraAdapter()
    storage = TimeSeriesStorage()

    insider_count = short_count = 0
    for symbol in symbols:
        try:
            # Insider transactions (Form 4)
            insider_txns = await edgar.get_insider_transactions(symbol, start, end)
            if insider_txns:
                await storage.store_insider_transactions(insider_txns)
                insider_count += len(insider_txns)

            # Short interest
            short_interest = await finra.get_short_interest(symbol, start, end)
            if short_interest:
                await storage.store_short_interest(short_interest)
                short_count += len(short_interest)
        except Exception:
            logger.warning("job.biweekly_altdata.symbol_error", symbol=symbol, exc_info=True)

    await redis.set("jobs:altdata:last_run", datetime.now(timezone.utc).isoformat())
    logger.info("job.biweekly_altdata.complete", insider_txns=insider_count, short_reports=short_count)
```

**Idempotency Key:** `jobs:altdata:last_run` (Redis string with ISO timestamp).

**Frequency Guard:** Only runs if > 12 days since last run (prevents accidental double-trigger on 1st/15th).

#### 4. `weekly_retrain_job`

**Schedule:** 2am ET Sunday (after weekly fundamentals on Saturday).

**Purpose:** Retrain XGBoost model with latest feature data.

**Logic:**
```python
async def weekly_retrain_job() -> None:
    logger.info("job.weekly_retrain.start")

    from src.signals.feature_store import FeatureStore
    from src.signals.ml.pipeline import MLPipeline
    from src.signals.ml.registry import ModelRegistry
    from src.data.universe import SymbolUniverse

    universe = SymbolUniverse()
    symbols = await universe.get_symbols()

    # 1. Load features (last 2 years)
    feature_store = FeatureStore()
    end = datetime.now(timezone.utc).date().isoformat()
    start = (datetime.now(timezone.utc) - timedelta(days=730)).date().isoformat()
    features = feature_store.get_features(symbols, start, end)

    if features.empty or len(features) < 500:
        logger.warning("job.weekly_retrain.insufficient_data", rows=len(features))
        return

    # 2. Prepare target (forward returns)
    pipeline = MLPipeline()
    target = pipeline.prepare_target(features, close_col="close")

    # 3. Train model
    metrics = pipeline.train(features, target)

    # 4. Save model to disk
    version_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_path = f"models/xgb_{version_id}.pkl"
    pipeline.save(model_path)

    # 5. Register with model registry
    registry = ModelRegistry(models_dir="models")
    version = registry.register(version_id, model_path, metrics)

    # 6. Promote to active if accuracy > 0.55
    if metrics.get("accuracy", 0.0) > 0.55:
        registry.promote(version_id)
        logger.info("job.weekly_retrain.promoted", version=version_id, accuracy=metrics["accuracy"])
    else:
        logger.warning("job.weekly_retrain.low_accuracy", version=version_id, accuracy=metrics["accuracy"])

    logger.info("job.weekly_retrain.complete", version=version_id, metrics=metrics)
```

**Idempotency:** Models are versioned by timestamp. If retrain runs twice, two versions are created (no data corruption).

**Auto-Promotion:** Model is promoted to active if accuracy > 0.55 (configurable threshold).

### Market Hours Safety

#### `is_market_hours_request_safe` (src/scheduling/jobs.py)

Prevents intraday IBKR historical data requests outside US equity market hours.

**Rationale:**
- [IBKR](../glossary.md#ibkr) rejects intraday bar requests (1Min, 5Min, 15Min, 1Hour) outside market hours (9:30am-5:30pm ET Mon-Fri).
- Daily/weekly/monthly bars are always safe to request.

**Usage:**
```python
from src.scheduling.jobs import is_market_hours_request_safe

if not is_market_hours_request_safe(timeframe="5Min"):
    logger.warning("intraday_request_skipped_outside_market_hours")
    return  # Skip request

# Safe to request intraday bars
bars = await ibkr_adapter.get_historical_bars(symbol, start, end, timeframe="5Min")
```

**Logic:**
- If timeframe is "1Day", "1Week", "1Month": return True (always safe).
- If timeframe is "1Min", "5Min", "15Min", "1Hour":
  - Check if current time (US/Eastern) is within 9:30am-5:30pm Mon-Fri.
  - Return True if within hours, False otherwise.

### Manual Triggers

Jobs can be triggered manually via API endpoints (useful for testing, backfills, urgent updates).

**API Endpoints:**
```
POST /api/system/scheduler/trigger/daily_bars
POST /api/system/scheduler/trigger/weekly_fundamentals
POST /api/system/scheduler/trigger/biweekly_altdata
POST /api/system/scheduler/trigger/weekly_retrain
```

**Example:**
```bash
curl -X POST http://localhost:8000/api/system/scheduler/trigger/daily_bars
```

**Implementation (src/api/routes/system.py):**
```python
@router.post("/scheduler/trigger/{job_name}")
async def trigger_job(job_name: str):
    scheduler = request.app.state.scheduler
    if not scheduler:
        raise HTTPException(500, "Scheduler not running")

    job_map = {
        "daily_bars": daily_bars_job,
        "weekly_fundamentals": weekly_fundamentals_job,
        "biweekly_altdata": biweekly_altdata_job,
        "weekly_retrain": weekly_retrain_job
    }

    if job_name not in job_map:
        raise HTTPException(404, f"Job '{job_name}' not found")

    # Run job in background task (non-blocking)
    asyncio.create_task(job_map[job_name]())
    return {"status": "triggered", "job": job_name}
```

## Configuration

**Settings (config/settings.yaml):**
```yaml
scheduler:
  enabled: true
  daily_bars_cron: "0 17 * * 1-5"            # 5pm ET Mon-Fri
  weekly_fundamentals_cron: "0 6 * * 6"      # 6am ET Saturday
  biweekly_altdata_cron: "0 7 1,15 * *"      # 7am ET 1st and 15th
  weekly_retrain_cron: "0 2 * * 0"           # 2am ET Sunday
```

**Environment Variable Overrides:**
```bash
export SA_SCHEDULER__ENABLED=false  # Disable scheduler (manual triggers only)
export SA_SCHEDULER__DAILY_BARS_CRON="0 18 * * 1-5"  # Change to 6pm ET
```

## Integration with Other Modules

- **Data Ingestion** (`src/data/`): Jobs fetch data via adapters (`AlphaVantageAdapter`, `EdgarAdapter`, `FinraAdapter`).
- **ML Pipeline** (`src/signals/`): `weekly_retrain_job` trains XGBoost model with latest features.
- **API** (`src/api/routes/system.py`): Exposes manual trigger endpoints.
- **Monitoring** (`src/monitoring/`): Prometheus metrics for job success/failure rates, execution time.

## Critical Patterns

1. **Idempotency:** All jobs track completion in Redis. Safe to retry on failure.
2. **Lazy imports:** Adapters and storage imported inside job functions, not at module top-level.
3. **7-day lookback for daily bars:** Covers weekends and market holidays (e.g., Monday fetches Fri-Thu bars).
4. **Market hours safety:** Intraday IBKR requests only during 9:30am-5:30pm ET Mon-Fri.
5. **TTL on Redis keys:** Keys expire after next expected run (prevents stale data).
6. **Graceful degradation:** If AlphaVantage fails, jobs log warnings but don't crash the system.
7. **Timezone-aware:** All cron schedules use `America/New_York` timezone.

## Glossary Links

- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [OHLCV](../glossary.md#ohlcv) — Open/High/Low/Close/Volume bar data
- [Redis](../glossary.md#redis) — In-memory data store
- [XGBoost](../glossary.md#xgboost) — Gradient boosting ML library

<!-- DIAGRAM: Scheduler job timeline — Mon-Fri 5pm (daily bars) → Sat 6am (fundamentals) → 1st/15th 7am (altdata) → Sun 2am (retrain) -->
