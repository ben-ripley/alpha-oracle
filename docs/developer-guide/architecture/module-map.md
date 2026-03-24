---
title: Module Map
nav_order: 1
parent: Architecture
---

# Module Map

This page provides a complete directory tree of the `src/` folder with one-line descriptions for each module and file. Use this as a quick reference for navigating the codebase.

## Top-Level Structure

```
src/
├── core/           # Foundation: models, interfaces, config, database, Redis
├── data/           # Data ingestion pipeline: adapters, feeds, storage, universe
├── strategy/       # Trading strategy engine, backtesting, builtin strategies
├── signals/        # ML pipeline: feature store, XGBoost, model monitoring
├── scheduling/     # APScheduler cron jobs: data ingestion, model retraining
├── execution/      # Order execution: router, broker adapters, order generation
├── risk/           # Risk management: PDT guard, pre-trade checks, circuit breakers
├── api/            # FastAPI REST API: routes, WebSocket, dependencies
└── monitoring/     # Observability: Prometheus metrics, alert manager
```

## Core Module (`src/core/`)

Foundation layer with models, interfaces, and infrastructure.

```
src/core/
├── __init__.py             # Package marker
├── models.py               # All Pydantic models (OHLCV, Signal, Order, Position, etc.)
├── interfaces.py           # 5 ABCs: DataSourceInterface, BaseStrategy, BrokerAdapter, RiskManager, BacktestEngine
├── config.py               # Pydantic Settings: YAML loading, env var overrides
├── database.py             # SQLAlchemy async engine + session factory
└── redis.py                # Redis client singleton, pub/sub helpers
```

**Key Files:**
- `models.py` — Single source of truth for all data structures (OHLCV, Signal, Order, Position, PortfolioSnapshot, BacktestResult)
- `interfaces.py` — Abstract interfaces enforcing module boundaries
- `config.py` — `Settings.from_yaml()` loads `config/settings.yaml` + `config/risk_limits.yaml` with env overrides

## Data Module (`src/data/`)

Data ingestion pipeline: market data, filings, short interest.

```
src/data/
├── __init__.py             # Package marker
├── adapters/               # Data source adapters
│   ├── __init__.py
│   ├── alpha_vantage.py    # AlphaVantageAdapter (REST API, 5 calls/min)
│   ├── ibkr_data.py        # IBKRDataAdapter (historical bars, fundamentals)
│   ├── edgar.py            # EDGARAdapter (SEC filings, Form 4 insider transactions)
│   └── finra.py            # FINRAAdapter (short interest data)
├── feeds/                  # Real-time market data feeds
│   ├── __init__.py
│   └── ibkr_feed.py        # IBKRMarketFeed (WebSocket tick data, bid/ask/last)
├── parsers/                # Data parsers
│   ├── __init__.py
│   └── form4_parser.py     # Parse SEC Form 4 XML (insider transactions)
├── storage.py              # TimeSeriesStorage (TimescaleDB + DuckDB)
└── universe.py             # UniverseManager (S&P 500 symbol list)
```

**Key Files:**
- `storage.py` — `TimeSeriesStorage` writes OHLCV bars to TimescaleDB hypertables, queries via DuckDB for analytics
- `feeds/ibkr_feed.py` — `IBKRMarketFeed` subscribes to IBKR WebSocket, caches bid/ask/last in Redis
- `universe.py` — S&P 500 symbol list with fallback to CSV

## Strategy Module (`src/strategy/`)

Trading strategy engine, backtesting, and builtin strategies.

```
src/strategy/
├── __init__.py             # Package marker
├── engine.py               # StrategyEngine: orchestrates signal generation, ranking
├── ranker.py               # StrategyRanker: multi-criteria strategy ranking
├── backtest/               # Backtest frameworks
│   ├── __init__.py         # Lazy imports for Backtrader, VectorBT
│   ├── backtrader_engine.py  # BacktraderEngine (Backtrader integration)
│   └── vectorbt_engine.py    # VectorBTEngine (vectorized backtesting, optional)
└── builtin/                # Builtin strategies
    ├── __init__.py         # Lazy imports
    ├── _indicators.py      # Indicator shim (pandas_ta with fallback to ta)
    ├── momentum.py         # MomentumStrategy (dual momentum: relative + absolute)
    ├── mean_reversion.py   # MeanReversionStrategy (Bollinger Band reversals)
    └── breakout.py         # BreakoutStrategy (ATR-based breakouts)
```

**Key Files:**
- `engine.py` — `StrategyEngine.generate_signals()` runs all strategies, ranks results
- `ranker.py` — `StrategyRanker.rank_strategies()` uses walk-forward backtest metrics (Sharpe, Sortino, max drawdown)
- `builtin/_indicators.py` — Shim layer for technical indicators (tries `pandas_ta`, falls back to `ta`)

## Signals Module (`src/signals/`)

ML pipeline: feature store, XGBoost, model monitoring, confidence calibration.

```
src/signals/
├── __init__.py             # Package marker
├── feature_store.py        # FeatureStore: orchestrates 50+ PIT feature calculators
├── ml_strategy.py          # MLSignalStrategy: wraps XGBoost model as BaseStrategy
├── calculators/            # Feature calculators (technical, fundamental, cross-asset, alternative)
│   ├── __init__.py
│   ├── technical.py        # RSI, MACD, Bollinger, ATR, ADX, etc.
│   ├── fundamental.py      # PE ratio, ROE, debt/equity, revenue growth
│   ├── cross_asset.py      # VIX, SPY correlation, sector rotation
│   └── alternative.py      # Form 4 insider buys, FINRA short interest
└── ml/                     # ML pipeline
    ├── __init__.py
    ├── pipeline.py         # MLPipeline: training, walk-forward validation, Optuna tuning
    ├── registry.py         # ModelRegistry: register/promote/rollback models
    ├── monitoring.py       # ModelMonitor: PSI drift, rolling accuracy
    ├── confidence.py       # ConfidenceCalibrator: isotonic regression calibration
    └── normalizer.py       # FeatureNormalizer: z-score normalization with PIT
```

**Key Files:**
- `feature_store.py` — `FeatureStore.compute_features()` orchestrates all calculators, caches in Parquet
- `ml_strategy.py` — `MLSignalStrategy.generate_signals()` loads model, predicts, filters by confidence
- `ml/pipeline.py` — `MLPipeline.train()` runs walk-forward validation with Optuna hyperparameter tuning
- `ml/registry.py` — `ModelRegistry.register()` saves model metadata to DB, `promote()` makes it active

## Scheduling Module (`src/scheduling/`)

APScheduler cron jobs for data ingestion and model retraining.

```
src/scheduling/
├── __init__.py             # Package marker
├── jobs.py                 # Cron job functions: daily_bars_job, weekly_fundamentals_job, biweekly_altdata_job
├── weekly_retrain_job.py   # weekly_retrain_job: retrain XGBoost model, update registry
└── scheduler.py            # SchedulerManager: APScheduler setup, job registration
```

**Key Files:**
- `jobs.py` — Data ingestion jobs (daily bars, weekly fundamentals, biweekly alt data) with Redis idempotency keys
- `weekly_retrain_job.py` — ML retraining job: compute features, train XGBoost, register new model
- `scheduler.py` — `SchedulerManager.start()` registers all cron jobs, `trigger_job()` runs jobs manually

**Idempotency Keys:**
- `jobs:daily_bars:{date}:done` — Daily bars job
- `jobs:weekly_fundamentals:{week}:done` — Weekly fundamentals job
- `jobs:altdata:last_run` — Biweekly alt data job (timestamp)
- `backfill:completed` — Historical data backfill

## Execution Module (`src/execution/`)

Order execution: smart router, broker adapters, order generation, quality tracking.

```
src/execution/
├── __init__.py             # Package marker
├── engine.py               # ExecutionEngine: orchestrates order flow (signals → orders → broker)
├── router.py               # SmartOrderRouter: selects market/limit/TWAP based on size, spread, urgency
├── order_generator.py      # OrderGenerator: Kelly criterion position sizing
├── quality_tracker.py      # ExecutionQualityTracker: slippage, effective spread, implementation shortfall
└── broker_adapters/        # Broker integrations
    ├── __init__.py
    ├── ibkr_adapter.py     # IBKRBrokerAdapter: ib-async integration, order submission, position sync
    ├── simulated.py        # SimulatedBroker: in-memory broker with realistic fills and slippage
    └── paper_stub.py       # PaperStubBroker: demo stub with mock data
```

**Key Files:**
- `router.py` — `SmartOrderRouter.route_order()` reads bid/ask from Redis feed, selects order type
- `broker_adapters/ibkr_adapter.py` — `IBKRBrokerAdapter` uses ib-async for IBKR connection
- `broker_adapters/simulated.py` — `SimulatedBroker` provides realistic order execution for testing
- `quality_tracker.py` — `ExecutionQualityTracker.record_fill()` calculates slippage metrics

**IBKR Client ID Scheme:**
- Broker adapter: `client_id` (default 1)
- Data adapter: `client_id + 1` (default 2)
- Market feed: `client_id + 2` (default 3)

## Risk Module (`src/risk/`)

Multi-layer risk management: PDT guard, pre-trade checks, circuit breakers, kill switch.

```
src/risk/
├── __init__.py             # Package marker
├── pdt_guard.py            # PDTGuard: Pattern Day Trader rule enforcement (CRITICAL)
├── pre_trade.py            # PreTradeRiskManager: pre-trade checks (PDT, position limits, portfolio limits)
├── portfolio_monitor.py    # PortfolioMonitor: real-time portfolio risk monitoring
├── circuit_breakers.py     # CircuitBreakers: VIX threshold, stale data, reconciliation, dead man switch
└── kill_switch.py          # KillSwitch: emergency halt mechanism
```

**Key Files:**
- `pdt_guard.py` — **CRITICAL**: `PDTGuard.check_order()` enforces 3 day trades per 5 business days for <$25K accounts
- `pre_trade.py` — `PreTradeRiskManager.check_pre_trade()` runs PDT + position + portfolio checks
- `circuit_breakers.py` — `CircuitBreakers.check_all()` returns status of VIX, stale data, reconciliation, dead man switch
- `kill_switch.py` — `KillSwitch.activate()` requires typed confirmation, cooldown 60 minutes

## API Module (`src/api/`)

FastAPI REST API: routes, WebSocket, dependencies.

```
src/api/
├── __init__.py             # Package marker
├── main.py                 # FastAPI app factory: middleware, startup/shutdown, route registration
├── dependencies.py         # Dependency injection: get_db_session, get_redis, get_broker_adapter
└── routes/                 # API route modules
    ├── __init__.py
    ├── portfolio.py        # Portfolio endpoints: /api/portfolio/snapshot, /api/portfolio/positions
    ├── strategies.py       # Strategy endpoints: /api/strategies/list, /api/strategies/signals
    ├── risk.py             # Risk endpoints: /api/risk/status, /api/risk/kill-switch/activate
    ├── trades.py           # Trade endpoints: /api/trades/history, /api/trades/submit
    ├── system.py           # System endpoints: /api/system/health, /api/system/scheduler/trigger
    └── websocket.py        # WebSocket endpoint: /ws (Redis pub/sub → client)
```

**Key Files:**
- `main.py` — `create_app()` factory, CORS middleware, startup/shutdown hooks
- `routes/websocket.py` — `/ws` WebSocket broadcasts Redis pub/sub events to dashboard
- `routes/system.py` — `/api/system/scheduler/trigger/<job_name>` triggers jobs manually

**Key Endpoints:**
- `GET /api/system/health` — System health check
- `GET /api/portfolio/snapshot` — Portfolio snapshot
- `GET /api/strategies/list` — Active strategies
- `POST /api/trades/submit` — Submit manual order
- `POST /api/risk/kill-switch/activate` — Emergency halt

## Monitoring Module (`src/monitoring/`)

Observability: Prometheus metrics, alert manager.

```
src/monitoring/
├── __init__.py             # Package marker
├── metrics.py              # Prometheus metrics: counters, gauges, histograms
└── alerts.py               # AlertManager: Slack/Telegram notifications
```

**Key Files:**
- `metrics.py` — Defines Prometheus metrics (signals generated, orders submitted, risk rejections, slippage percentiles)
- `alerts.py` — `AlertManager.send_alert()` sends Slack/Telegram notifications on risk breaches

## Entry Points

### Backend Entry Point

**File:** `src/api/main.py`

```python
from fastapi import FastAPI
from src.api.main import create_app

app = create_app()  # Called by uvicorn: `uvicorn src.api.main:app`
```

Run via:

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

Or use the script:

```bash
./scripts/start-backend.sh
```

### CLI Scripts

**Directory:** `scripts/`

```
scripts/
├── start-backend.sh        # Start Docker infra + FastAPI
├── stop-backend.sh         # Stop FastAPI (optionally stop Docker infra)
├── restart-backend.sh      # Restart FastAPI (optionally restart Docker infra)
├── start-frontend.sh       # Start Vite dev server
├── stop-frontend.sh        # Stop Vite dev server
├── restart-frontend.sh     # Restart Vite dev server
├── backfill_history.py     # Backfill historical OHLCV data
└── clear_database.sh       # Remove seed/demo data from Redis
```

## Next Steps

- [Module Reference](../modules/index.md) — In-depth documentation for each module
- [Data Flows](data-flows.md) — Understand how data moves through the system
- [Extending](../extending/index.md) — Write custom strategies, adapters, and risk managers
