---
title: Database Schema
nav_order: 2
parent: Infrastructure
---

# Database Schema

The system uses [TimescaleDB](../glossary.md#timescaledb) (PostgreSQL 16 with the TimescaleDB extension) as its primary time-series database. All tables are created as [hypertables](../glossary.md#hypertable) partitioned by timestamp for efficient time-range queries.

## Connection

**Driver:** SQLAlchemy async with asyncpg
**Connection String:** `postgresql+asyncpg://trader:password@timescaledb:5432/stock_analysis`

Connection pool settings (configured in `src/core/database.py`):
- Pool size: 20 (default)
- Max overflow: 10 (default)
- Echo mode: Enabled in development environment

---

## Hypertables

All tables use `create_hypertable()` to enable TimescaleDB's automatic time-based partitioning. This provides:
- Efficient time-range queries
- Automatic chunk management
- Better compression for historical data
- Faster inserts for high-throughput data

---

## Tables

### ohlcv

**Purpose:** OHLCV price data (daily and intraday bars)
**Hypertable:** Partitioned by `timestamp`
**Chunk Interval:** 7 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | TEXT | Stock ticker symbol |
| `timestamp` | TIMESTAMPTZ | Bar timestamp (UTC) |
| `open` | DOUBLE PRECISION | Opening price |
| `high` | DOUBLE PRECISION | High price |
| `low` | DOUBLE PRECISION | Low price |
| `close` | DOUBLE PRECISION | Closing price |
| `volume` | BIGINT | Trading volume |
| `adjusted_close` | DOUBLE PRECISION | Split/dividend adjusted close (nullable) |
| `source` | TEXT | Data source (e.g., 'ibkr', 'alpha_vantage') |

**Primary Key:** `(symbol, timestamp)`
**Indexes:**
- `idx_ohlcv_symbol` on `(symbol, timestamp DESC)` — optimized for latest-bar queries

---

### fundamentals

**Purpose:** Fundamental financial metrics
**Hypertable:** Partitioned by `timestamp`
**Chunk Interval:** 30 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | TEXT | Stock ticker symbol |
| `timestamp` | TIMESTAMPTZ | Report timestamp (UTC) |
| `pe_ratio` | DOUBLE PRECISION | Price-to-earnings ratio |
| `pb_ratio` | DOUBLE PRECISION | Price-to-book ratio |
| `ps_ratio` | DOUBLE PRECISION | Price-to-sales ratio |
| `ev_ebitda` | DOUBLE PRECISION | Enterprise value / EBITDA |
| `debt_to_equity` | DOUBLE PRECISION | Debt-to-equity ratio |
| `current_ratio` | DOUBLE PRECISION | Current assets / current liabilities |
| `roe` | DOUBLE PRECISION | Return on equity (%) |
| `revenue_growth` | DOUBLE PRECISION | Year-over-year revenue growth (%) |
| `earnings_growth` | DOUBLE PRECISION | Year-over-year earnings growth (%) |
| `dividend_yield` | DOUBLE PRECISION | Dividend yield (%) |
| `market_cap` | DOUBLE PRECISION | Market capitalization (USD) |
| `sector` | TEXT | GICS sector |
| `industry` | TEXT | GICS industry |

**Primary Key:** `(symbol, timestamp)`

---

### filings

**Purpose:** SEC filings (10-K, 10-Q, 8-K, Form 4)
**Hypertable:** Partitioned by `filed_date`
**Chunk Interval:** 30 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Auto-incrementing ID |
| `symbol` | TEXT | Stock ticker symbol |
| `filing_type` | TEXT | Filing type (e.g., '10-K', 'Form 4') |
| `filed_date` | TIMESTAMPTZ | Date filed with SEC (UTC) |
| `url` | TEXT | EDGAR URL |
| `content` | TEXT | Parsed content or summary |
| `metadata` | JSONB | Additional structured data |

**Primary Key:** `(id, filed_date)`

---

### trades

**Purpose:** Trade execution audit trail
**Hypertable:** Partitioned by `entry_time`
**Chunk Interval:** 7 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Unique trade ID |
| `symbol` | TEXT | Stock ticker symbol |
| `side` | TEXT | 'BUY' or 'SELL' |
| `quantity` | DOUBLE PRECISION | Number of shares |
| `entry_price` | DOUBLE PRECISION | Entry price per share |
| `exit_price` | DOUBLE PRECISION | Exit price per share (nullable until closed) |
| `entry_time` | TIMESTAMPTZ | Trade entry timestamp (UTC) |
| `exit_time` | TIMESTAMPTZ | Trade exit timestamp (nullable until closed) |
| `pnl` | DOUBLE PRECISION | Realized profit/loss (USD) |
| `pnl_pct` | DOUBLE PRECISION | Realized profit/loss (%) |
| `strategy_name` | TEXT | Strategy that generated the trade |
| `hold_duration_days` | DOUBLE PRECISION | Days held |
| `is_day_trade` | BOOLEAN | Whether trade was a day trade (PDT tracking) |

**Primary Key:** `(id, entry_time)`

---

### orders

**Purpose:** Order submission and execution audit trail
**Hypertable:** Partitioned by `created_at`
**Chunk Interval:** 7 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT | Internal order ID (UUID) |
| `symbol` | TEXT | Stock ticker symbol |
| `side` | TEXT | 'BUY' or 'SELL' |
| `order_type` | TEXT | 'MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT' |
| `quantity` | DOUBLE PRECISION | Number of shares |
| `limit_price` | DOUBLE PRECISION | Limit price (nullable) |
| `stop_price` | DOUBLE PRECISION | Stop price (nullable) |
| `status` | TEXT | 'PENDING', 'SUBMITTED', 'FILLED', 'CANCELLED', 'REJECTED' |
| `strategy_name` | TEXT | Strategy that generated the order |
| `signal_strength` | DOUBLE PRECISION | Signal strength (0.0 to 1.0) |
| `created_at` | TIMESTAMPTZ | Order creation timestamp (UTC) |
| `filled_at` | TIMESTAMPTZ | Order fill timestamp (nullable) |
| `filled_price` | DOUBLE PRECISION | Actual fill price (nullable) |
| `filled_quantity` | DOUBLE PRECISION | Actual fill quantity (nullable) |
| `broker_order_id` | TEXT | Broker's order ID (e.g., IBKR order ID) |
| `metadata` | JSONB | Additional order metadata |

**Primary Key:** `(id, created_at)`

---

### portfolio_snapshots

**Purpose:** Point-in-time portfolio state (captured every 5 minutes)
**Hypertable:** Partitioned by `timestamp`
**Chunk Interval:** 7 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | TIMESTAMPTZ | Snapshot timestamp (UTC) |
| `total_equity` | DOUBLE PRECISION | Total account equity (USD) |
| `cash` | DOUBLE PRECISION | Cash balance (USD) |
| `positions_value` | DOUBLE PRECISION | Total position value (USD) |
| `daily_pnl` | DOUBLE PRECISION | Profit/loss since market open (USD) |
| `daily_pnl_pct` | DOUBLE PRECISION | Profit/loss since market open (%) |
| `total_pnl` | DOUBLE PRECISION | All-time profit/loss (USD) |
| `total_pnl_pct` | DOUBLE PRECISION | All-time profit/loss (%) |
| `max_drawdown_pct` | DOUBLE PRECISION | Maximum drawdown (%) |
| `positions` | JSONB | Array of position objects |
| `sector_exposure` | JSONB | Sector exposure breakdown |

**Primary Key:** `timestamp`

---

### signals

**Purpose:** Trading signal log (generated by strategies)
**Hypertable:** Partitioned by `timestamp`
**Chunk Interval:** 7 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `symbol` | TEXT | Stock ticker symbol |
| `timestamp` | TIMESTAMPTZ | Signal generation time (UTC) |
| `direction` | TEXT | 'BUY', 'SELL', 'HOLD' |
| `strength` | DOUBLE PRECISION | Signal strength (0.0 to 1.0) |
| `strategy_name` | TEXT | Strategy that generated the signal |
| `metadata` | JSONB | Additional signal context |

**Primary Key:** `(symbol, timestamp, strategy_name)`

---

### risk_events

**Purpose:** Risk management event log
**Hypertable:** Partitioned by `timestamp`
**Chunk Interval:** 7 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Auto-incrementing ID |
| `timestamp` | TIMESTAMPTZ | Event timestamp (UTC, defaults to NOW()) |
| `event_type` | TEXT | Event type (e.g., 'circuit_breaker', 'pdt_guard') |
| `action` | TEXT | Action taken (e.g., 'REJECT', 'HALT') |
| `reasons` | TEXT[] | Array of reason strings |
| `metadata` | JSONB | Additional event context |

**Primary Key:** `(id, timestamp)`

---

### kill_switch

**Purpose:** Kill switch state (singleton table)
**Not a hypertable** (single-row table)

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `active` | BOOLEAN | Kill switch active flag |
| `activated_at` | TIMESTAMPTZ | Last activation timestamp |
| `reason` | TEXT | Activation reason |
| `deactivated_at` | TIMESTAMPTZ | Last deactivation timestamp |

**Primary Key:** `id`
**Initialization:** Single row inserted with `active = FALSE` on database init

---

### backtest_results

**Purpose:** Backtest performance metrics
**Hypertable:** Partitioned by `run_at`
**Chunk Interval:** 30 days (default)

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Auto-incrementing ID |
| `strategy_name` | TEXT | Strategy name |
| `run_at` | TIMESTAMPTZ | Backtest run timestamp (UTC) |
| `start_date` | TIMESTAMPTZ | Backtest period start |
| `end_date` | TIMESTAMPTZ | Backtest period end |
| `initial_capital` | DOUBLE PRECISION | Starting capital (USD) |
| `final_capital` | DOUBLE PRECISION | Ending capital (USD) |
| `total_return_pct` | DOUBLE PRECISION | Total return (%) |
| `annual_return_pct` | DOUBLE PRECISION | Annualized return (%) |
| `sharpe_ratio` | DOUBLE PRECISION | Sharpe ratio |
| `sortino_ratio` | DOUBLE PRECISION | Sortino ratio |
| `max_drawdown_pct` | DOUBLE PRECISION | Maximum drawdown (%) |
| `profit_factor` | DOUBLE PRECISION | Gross profit / gross loss |
| `total_trades` | INTEGER | Total number of trades |
| `winning_trades` | INTEGER | Number of winning trades |
| `losing_trades` | INTEGER | Number of losing trades |
| `win_rate` | DOUBLE PRECISION | Win rate (%) |
| `equity_curve` | JSONB | Time-series equity values |
| `metadata` | JSONB | Additional backtest parameters |

**Primary Key:** `(id, run_at)`

---

### operator_heartbeat

**Purpose:** Dead man's switch heartbeat tracking (singleton table)
**Not a hypertable** (single-row table)

| Column | Type | Description |
|--------|------|-------------|
| `id` | SERIAL | Primary key |
| `last_heartbeat` | TIMESTAMPTZ | Last operator check-in (UTC) |

**Primary Key:** `id`
**Initialization:** Single row inserted with `last_heartbeat = NOW()` on database init

---

## Initialization

The database schema is created automatically by Docker Compose on first startup via the `init_db.sql` script mounted at `/docker-entrypoint-initdb.d/init.sql`.

To manually re-initialize:
```bash
docker compose down -v  # WARNING: destroys all data
docker compose up -d timescaledb
```

---

<!-- DIAGRAM: ER diagram showing table relationships and hypertable partitioning -->
