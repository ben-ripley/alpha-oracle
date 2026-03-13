# Data Ingestion Module

The `src/data/` module orchestrates multi-source data ingestion: real-time market feeds, historical [OHLCV](../glossary.md#ohlcv) bars, fundamental data, SEC filings, and alternative data (insider trades, short interest). All data flows into [TimescaleDB](../glossary.md#timescaledb) for time-series storage and DuckDB/Parquet for analytics.

## Purpose

Data ingestion provides point-in-time (PIT) data to strategies and the ML pipeline:

- **Adapters** implement `DataSourceInterface` or `FilingSourceInterface` for each data provider
- **Market feeds** publish real-time bid/ask/last to Redis pub/sub channels
- **Storage layer** handles upserts to TimescaleDB with deduplication
- **Universe management** maintains S&P 500 symbol list with 24h cache
- **Parsers** extract structured data from SEC XML filings

## Key Components

### Data Adapters

All adapters live in `src/data/adapters/` and implement core interfaces from `src/core/interfaces.py`.

#### `IBKRDataAdapter` (src/data/adapters/ibkr_data_adapter.py)

Implements `DataSourceInterface` via [IBKR](../glossary.md#ibkr) API using `ib-async` library.

**Methods:**
- `get_historical_bars(symbol, start, end, timeframe="1Day")`: Fetches OHLCV bars. Supports "1Day", "1Min", "5Min", "15Min", "1Hour" timeframes.
- `get_latest_bar(symbol)`: Returns most recent bar (near-real-time during market hours).
- `get_fundamentals(symbol)`: Fetches P/E, P/B, debt-to-equity, ROE, etc. from IBKR fundamental data.
- `health_check()`: Validates IB Gateway / TWS connection.

**Configuration:**
- `SA_BROKER__IBKR__HOST`: IB Gateway host (default: `127.0.0.1`)
- `SA_BROKER__IBKR__PORT`: 4002 (Gateway paper), 4001 (Gateway live), 7497 (TWS paper), 7496 (TWS live)
- `SA_BROKER__IBKR__CLIENT_ID`: Base client ID (default: 1). Data adapter uses `client_id + 1` to avoid collision with broker adapter.

**Rate Limits:**
- 60 historical data requests per 10 minutes (IBKR pacing violation threshold)
- Adapter implements backoff retry on pacing errors

**Important:** Intraday timeframes (1Min, 5Min, 15Min, 1Hour) can only be requested during US equity market hours (Mon-Fri 9:30am-5:30pm ET). The scheduler checks `is_market_hours_request_safe()` before triggering intraday jobs.

#### `AlphaVantageAdapter` (src/data/adapters/alpha_vantage_adapter.py)

Implements `DataSourceInterface` via Alpha Vantage REST API. Used for historical backfills and fundamentals.

**Methods:**
- `get_historical_bars(symbol, start, end, timeframe="1Day")`: Fetches daily OHLCV (adjusted for splits/dividends).
- `get_fundamentals(symbol)`: Company overview + income statement ratios.
- `health_check()`: Validates API key and endpoint availability.

**Configuration:**
- `SA_ALPHA_VANTAGE_API_KEY`: Required. Free tier = 25 requests/day, 5 requests/minute.
- `SA_DATA__ALPHA_VANTAGE__RATE_LIMIT_PER_MINUTE`: Default 5 (aligned with free tier).
- `SA_DATA__ALPHA_VANTAGE__CACHE_TTL_HOURS`: Default 24h.

**Backfill Script:**
```bash
# Backfill 2 years of S&P 500 data (~1h40m on free tier)
python scripts/backfill_history.py --years 2 --symbols sp500

# Resume interrupted run (Redis tracks completed symbols)
python scripts/backfill_history.py --resume

# Quick test with specific symbols
python scripts/backfill_history.py --years 2 --symbols AAPL,MSFT,GOOG
```

Idempotency: `backfill:completed` Redis key prevents duplicate work.

#### `EdgarAdapter` (src/data/adapters/edgar_adapter.py)

Implements `FilingSourceInterface` for SEC EDGAR filings.

**Methods:**
- `get_filings(symbol, filing_type, start, end)`: Returns list of filings (10-K, 10-Q, 8-K, Form 4). Metadata only; content fetched on demand.
- `get_insider_transactions(symbol, start, end)`: Parses Form 4 XML via `Form4Parser` to extract insider buy/sell events.

**Configuration:**
- `SA_DATA__EDGAR__USER_AGENT`: Required by SEC (format: "app-name contact@example.com").
- `SA_DATA__EDGAR__RATE_LIMIT_PER_SECOND`: Default 10 (SEC allows up to 10 req/sec with proper user-agent).

**Form 4 Parser** (`src/data/parsers/form4_parser.py`):
- Extracts: insider_name, insider_title, transaction_type (P=purchase, S=sale, A=grant, D=disposal, M=exercise), shares, price_per_share, shares_owned_after
- Handles both direct and indirect holdings
- Graceful degradation on malformed XML

#### `FinraAdapter` (src/data/adapters/finra_adapter.py)

Fetches FINRA short interest data (alternative data source).

**Methods:**
- `get_short_interest(symbol, start, end)`: Returns short interest reports with settlement_date, short_interest (shares), avg_daily_volume, days_to_cover, short_pct_float.

**Configuration:**
- `SA_DATA__FINRA__RATE_LIMIT_PER_MINUTE`: Default 10.
- `SA_DATA__FINRA__CACHE_TTL_SECONDS`: Default 86400 (24h).
- `SA_DATA__FINRA__BASE_URL`: Default "https://api.finra.org".

**Note:** FINRA short interest is published bi-monthly (settlement dates: mid-month and end-of-month).

### Market Data Feeds

Real-time streaming feeds implement `MarketDataFeed` interface in `src/data/feeds/base.py`.

#### `IBKRMarketFeed` (src/data/feeds/ibkr_feed.py)

WebSocket-like real-time market data feed via IB Gateway / TWS using `ib-async`.

**Published Redis Channels:**
- `market:quotes:{symbol}`: Bid/ask/size on every price tick. Keys: `bid_price`, `ask_price`, `bid_size`, `ask_size`, `timestamp`.
- `market:bars:{symbol}`: Synthetic OHLCV-style bar on every last-price tick. Keys: `open`, `high`, `low`, `close`, `volume`, `timestamp`.

**Features:**
- Subscribes to multiple symbols (up to `symbols_per_connection` per connection, default 200).
- Automatic reconnection with exponential backoff (base delay 5s, max delay 60s, max attempts 10).
- Uses `client_id + 2` to avoid collision with broker adapter (+0) and data adapter (+1).

**Configuration:**
- `SA_DATA__FEED__FEED_TYPE`: `iex` (free, delayed 15min) or `sip` (paid, real-time). IBKR feed ignores this setting.
- `SA_DATA__FEED__SYMBOLS_PER_CONNECTION`: Default 200. IBKR supports up to 100 simultaneous market data subscriptions per connection (free tier) or 500+ (paid).
- `SA_DATA__FEED__RECONNECT_DELAY_SECONDS`: Default 5.
- `SA_DATA__FEED__MAX_RECONNECT_ATTEMPTS`: Default 10.

**Reconnect Logic:**
1. On disconnect, publish `system:feed:disconnected` to Redis.
2. Retry connection with exponential backoff.
3. On success, re-subscribe to all previously subscribed symbols.
4. Publish `system:feed:connected` to Redis.

**Integration:**
- Smart order router (`src/execution/router.py`) reads `bid_price`/`ask_price` from `market:quotes:{symbol}` channel.
- WebSocket (`/ws`) relays feed events to dashboard for real-time price updates.

### Storage Layer

#### `TimeSeriesStorage` (src/data/storage.py)

Dual-backend storage: [TimescaleDB](../glossary.md#timescaledb) for primary time-series data + DuckDB for Parquet analytics.

**Methods:**

| Method | Purpose | Deduplication Strategy |
|--------|---------|------------------------|
| `store_ohlcv(bars: list[OHLCV])` | Upsert OHLCV bars | `ON CONFLICT (symbol, timestamp)` updates existing |
| `get_ohlcv(symbol, start, end)` | Fetch bars for analysis | Indexed on (symbol, timestamp) |
| `store_fundamentals(data: list[FundamentalData])` | Upsert fundamental snapshots | `ON CONFLICT (symbol, timestamp)` |
| `get_fundamentals(symbol, start, end)` | Fetch fundamental history | Point-in-time join support |
| `store_insider_transactions(txns: list[InsiderTransaction])` | Upsert insider trades | `ON CONFLICT (symbol, filed_date, insider_name, transaction_type)` |
| `get_insider_transactions(symbol, start, end)` | Fetch insider activity | Ordered by filed_date DESC |
| `store_short_interest(data: list[ShortInterestData])` | Upsert FINRA short interest | `ON CONFLICT (symbol, settlement_date)` |
| `get_short_interest(symbol, start, end)` | Fetch short interest history | Ordered by settlement_date DESC |
| `store_portfolio_snapshot(snapshot: PortfolioSnapshot)` | Log portfolio state | No dedup (time-series only) |
| `get_portfolio_snapshots(start, end)` | Fetch portfolio history for analytics | N/A |

**DuckDB Integration:**
- Exports TimescaleDB query results to Parquet via `to_parquet()` method.
- Used by feature store for bulk analytics (faster than PostgreSQL for OLAP queries).
- Parquet files stored in `data/features/{symbol}.parquet`.

**Schema:**
- Tables created via Alembic migrations (see `docs/developer-guide/infrastructure.md`).
- Hypertables (TimescaleDB): `ohlcv`, `fundamentals`, `portfolio_snapshots` are time-partitioned by `timestamp`.
- Indexes: `(symbol, timestamp)` on all time-series tables for fast range queries.

### Universe Management

#### `SymbolUniverse` (src/data/universe.py)

Maintains the S&P 500 symbol list for data ingestion and signal generation.

**Methods:**
- `get_symbols() -> list[str]`: Returns S&P 500 tickers from Wikipedia. Falls back to `config/sp500_fallback.csv` on network error.
- Cache TTL: 24 hours (Redis key: `universe:sp500`).

**Fallback CSV:**
- Checked into version control at `config/sp500_fallback.csv`.
- Updated manually (or via script) every quarter.

**Usage:**
```python
from src.data.universe import SymbolUniverse

universe = SymbolUniverse()
symbols = await universe.get_symbols()  # ~500 symbols
```

Scheduler jobs (`daily_bars`, `weekly_fundamentals`) iterate over universe symbols.

### Rate Limiting

#### `RateLimiter` (src/data/rate_limiter.py)

Token-bucket rate limiter for API adapters.

**Usage:**
```python
from src.data.rate_limiter import RateLimiter

limiter = RateLimiter(max_calls=5, period_seconds=60)
async with limiter:
    # API call executes only if rate limit allows
    data = await adapter.fetch_data()
```

**Behavior:**
- Blocks `await` if rate limit exceeded until tokens replenish.
- Prevents 429 (Too Many Requests) errors and FINRA/SEC blocks.

## Data Flow

<!-- DIAGRAM: Data flow from external APIs → adapters → storage → feature store / strategies -->

1. **Scheduled Jobs** (see [Scheduling Module](./scheduling.md)):
   - `daily_bars_job`: Fetches daily OHLCV for all universe symbols via AlphaVantage → `TimeSeriesStorage.store_ohlcv()`.
   - `weekly_fundamentals_job`: Fetches fundamentals via AlphaVantage → `TimeSeriesStorage.store_fundamentals()`.
   - `biweekly_altdata_job`: Fetches Form 4 (Edgar) and short interest (FINRA) → `store_insider_transactions()`, `store_short_interest()`.
   - `weekly_retrain_job`: Reads features from storage → trains XGBoost model.

2. **Real-Time Feed** (during market hours):
   - `IBKRMarketFeed` subscribes to universe symbols.
   - Publishes bid/ask/last to Redis channels (`market:quotes:*`, `market:bars:*`).
   - Smart router reads quotes for limit order pricing.
   - WebSocket relays events to dashboard.

3. **Backfill** (one-time historical load):
   - `scripts/backfill_history.py` iterates over universe symbols.
   - Fetches 1-2 years of daily bars via AlphaVantage.
   - Upserts to TimescaleDB with idempotency (Redis key: `backfill:completed`).

## Configuration Summary

| Setting | Default | Purpose |
|---------|---------|---------|
| `SA_ALPHA_VANTAGE_API_KEY` | (required) | Alpha Vantage API key |
| `SA_DATA__ALPHA_VANTAGE__RATE_LIMIT_PER_MINUTE` | 5 | Free tier limit |
| `SA_DATA__EDGAR__USER_AGENT` | "stock-analysis bot@example.com" | SEC EDGAR user-agent |
| `SA_DATA__EDGAR__RATE_LIMIT_PER_SECOND` | 10 | SEC allows 10 req/sec |
| `SA_DATA__FINRA__RATE_LIMIT_PER_MINUTE` | 10 | FINRA short interest API |
| `SA_DATA__UNIVERSE__CACHE_TTL_SECONDS` | 86400 (24h) | S&P 500 list cache |
| `SA_DATA__UNIVERSE__FALLBACK_CSV` | config/sp500_fallback.csv | Offline fallback |
| `SA_DATA__FEED__SYMBOLS_PER_CONNECTION` | 200 | IBKR feed batch size |
| `SA_DATA__FEED__RECONNECT_DELAY_SECONDS` | 5 | Feed reconnect backoff base |
| `SA_DATA__FEED__MAX_RECONNECT_ATTEMPTS` | 10 | Feed reconnect limit |

## Integration with Other Modules

- **Feature Store** (`src/signals/feature_store.py`): Reads OHLCV, fundamentals, insider trades, short interest from `TimeSeriesStorage` → computes 50+ features.
- **Strategy Engine** (`src/strategy/engine.py`): Calls `adapter.get_historical_bars()` for backtests.
- **Execution Engine** (`src/execution/router.py`): Reads real-time quotes from `market:quotes:{symbol}` Redis channels.
- **Scheduler** (`src/scheduling/jobs.py`): Orchestrates daily/weekly/biweekly data refresh jobs.

## Critical Patterns

1. **Point-in-time safety**: All fundamental/alternative data uses `filed_date` or `settlement_date`, not `timestamp`, to avoid lookahead bias.
2. **Idempotency**: Upserts use `ON CONFLICT` clauses. Jobs track completion in Redis (`jobs:daily_bars:{date}:done`).
3. **Graceful degradation**: If AlphaVantage fails, IBKR adapter provides fallback. If feed disconnects, last known quotes remain in Redis.
4. **Rate limiting**: All adapters use `RateLimiter` to avoid 429 errors and provider blocks.
5. **Lazy imports**: Heavy deps (`ib_async`, `pandas_ta`) are imported inside functions, not at module top-level, to avoid load-time errors.

## Glossary Links

- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [OHLCV](../glossary.md#ohlcv) — Open/High/Low/Close/Volume bar data
- [TimescaleDB](../glossary.md#timescaledb) — Time-series PostgreSQL extension
- [Redis](../glossary.md#redis) — In-memory data store
- [PDT](../glossary.md#pdt) — Pattern Day Trader rule (relevant for scheduling daily bar fetches outside market hours)
