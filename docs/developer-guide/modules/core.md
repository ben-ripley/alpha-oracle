# Core Module

The `src/core/` module provides the foundational building blocks for the stock-analysis system: domain models, interfaces, configuration, database, and [Redis](../glossary.md#redis) client management.

## Purpose

Core establishes type-safe contracts and shared infrastructure:

- **Pydantic models** for all domain objects ([OHLCV](../glossary.md#ohlcv), signals, orders, portfolio snapshots)
- **Abstract base classes (ABCs)** that define interfaces for strategies, brokers, data sources, risk managers, and backtest engines
- **Configuration system** with YAML defaults + environment variable overrides
- **Database and Redis singletons** for async SQLAlchemy and Redis clients

All other modules import from `src.core` but never import from each other directly, enforcing a clean layered architecture.

## Key Files

### `src/core/models.py`

All Pydantic `BaseModel` domain models. Every model uses type hints, field validation, and default factories where applicable.

**Enums:**
- `SignalDirection`: LONG, SHORT, FLAT
- `OrderSide`: BUY, SELL
- `OrderType`: MARKET, LIMIT, STOP, STOP_LIMIT, BRACKET
- `OrderStatus`: PENDING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, EXPIRED
- `RiskAction`: APPROVE, REJECT, REQUIRE_HUMAN_APPROVAL, REDUCE_SIZE
- `AutonomyMode`: PAPER_ONLY, MANUAL_APPROVAL, BOUNDED_AUTONOMOUS, FULL_AUTONOMOUS

**Key Models:**

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `OHLCV` | Time-series bar data | symbol, timestamp, open, high, low, close, volume, source, adjusted_close |
| `FundamentalData` | Company financials | symbol, timestamp, pe_ratio, pb_ratio, debt_to_equity, roe, revenue_growth, sector, industry |
| `Filing` | SEC filing metadata | symbol, filing_type (10-K, 10-Q, 8-K, Form 4), filed_date, url, content |
| `Signal` | Trading signal | symbol, timestamp, direction, strength (0.0-1.0), strategy_name, metadata |
| `Order` | Order request | id, symbol, side, order_type, quantity, limit_price, stop_price, status, strategy_name, filled_price, broker_order_id |
| `Position` | Open position | symbol, quantity, avg_entry_price, current_price, unrealized_pnl, unrealized_pnl_pct, side, sector, entry_date, strategy_name |
| `PortfolioSnapshot` | Portfolio state at a point in time | timestamp, total_equity, cash, positions_value, daily_pnl, daily_pnl_pct, max_drawdown_pct, positions (list), sector_exposure (dict) |
| `TradeRecord` | Closed trade | symbol, side, quantity, entry_price, exit_price, entry_time, exit_time, pnl, pnl_pct, strategy_name, hold_duration_days, is_day_trade |
| `RiskCheckResult` | Risk decision | action, reasons (list of strings), adjusted_quantity, metadata |
| `BacktestResult` | Backtest performance | strategy_name, start/end dates, initial/final capital, sharpe_ratio, sortino_ratio, max_drawdown_pct, profit_factor, total_trades, win_rate, equity_curve, trades |
| `StrategyRanking` | Strategy composite score | strategy_name, composite_score, sharpe_ratio, sortino_ratio, max_drawdown_pct, profit_factor, consistency_score, meets_thresholds |

**Phase 2 Models (Alternative Data & Execution Quality):**
- `InsiderTransaction`: Form 4 insider buy/sell data (symbol, filed_date, insider_name, transaction_type, shares, price_per_share)
- `ShortInterestData`: FINRA short interest reports (symbol, settlement_date, short_interest, days_to_cover, short_pct_float)
- `ExecutionQualityMetrics`: Fill performance (order_id, slippage_bps, arrival_slippage_bps, fill_latency_ms, signal_timestamp, fill_timestamp)

### `src/core/interfaces.py`

Five abstract base classes defining the contract for pluggable components. All methods are `@abstractmethod` — concrete implementations must override them.

**1. `DataSourceInterface`**

```python
async def get_historical_bars(symbol: str, start: datetime, end: datetime, timeframe: str = "1Day") -> list[OHLCV]
async def get_latest_bar(symbol: str) -> OHLCV | None
async def get_fundamentals(symbol: str) -> FundamentalData | None
async def health_check() -> bool
```

Implemented by:
- `IBKRDataAdapter` (src/data/adapters/ibkr_data_adapter.py)
- `AlphaVantageAdapter` (src/data/adapters/alpha_vantage_adapter.py)

**2. `FilingSourceInterface`**

```python
async def get_filings(symbol: str, filing_type: str, start: datetime, end: datetime) -> list[Filing]
async def get_insider_transactions(symbol: str, start: datetime, end: datetime) -> list[InsiderTransaction]
```

Implemented by:
- `EdgarAdapter` (src/data/adapters/edgar_adapter.py)

**3. `BaseStrategy`**

```python
@property name() -> str
@property description() -> str
@property min_hold_days() -> int  # must be >= 2 for PDT compliance
def generate_signals(data: dict[str, list[OHLCV]]) -> list[Signal]
def get_parameters() -> dict[str, Any]
def get_required_data() -> list[str]  # e.g., ["ohlcv", "fundamentals"]
```

Implemented by:
- Built-in strategies in `src/strategy/builtin/`
- `MLSignalStrategy` (src/signals/ml_strategy.py) for XGBoost predictions

**4. `BrokerAdapter`**

```python
async def submit_order(order: Order) -> Order
async def cancel_order(broker_order_id: str) -> bool
async def get_order_status(broker_order_id: str) -> OrderStatus
async def get_positions() -> list[Position]
async def get_portfolio() -> PortfolioSnapshot
async def health_check() -> bool
```

Implemented by:
- `IBKRBrokerAdapter` (src/execution/broker/ibkr_broker.py) — real [IBKR](../glossary.md#ibkr) trades
- `PaperStubBroker` (src/execution/broker/paper_stub.py) — demo fallback with seed data
- `SimulatedBroker` (src/execution/broker/simulated_broker.py) — in-memory simulation

**5. `RiskManager`**

```python
async def check_pre_trade(order: Order, portfolio: PortfolioSnapshot) -> RiskCheckResult
async def check_portfolio(portfolio: PortfolioSnapshot) -> RiskCheckResult
async def is_kill_switch_active() -> bool
async def activate_kill_switch(reason: str) -> None
```

Implemented by:
- `RiskManager` (src/risk/manager.py) orchestrates all risk checks

**6. `BacktestEngine`**

```python
def run(strategy: BaseStrategy, data: dict[str, list[OHLCV]], initial_capital: float, start: datetime, end: datetime) -> BacktestResult
def walk_forward(strategy: BaseStrategy, data: dict[str, list[OHLCV]], initial_capital: float, train_months: int, test_months: int, step_months: int) -> list[BacktestResult]
```

Implemented by:
- `BacktraderEngine` (src/strategy/backtest/backtrader_engine.py)
- `VectorBTEngine` (src/strategy/backtest/vectorbt_engine.py)

### `src/core/config.py`

Configuration is loaded from `config/settings.yaml` and `config/risk_limits.yaml`, with environment variable overrides via Pydantic Settings.

**Environment Variable Convention:**
- Prefix: `SA_`
- Nested delimiter: `__` (double underscore)
- Example: `SA_BROKER__PROVIDER=ibkr` sets `broker.provider = "ibkr"`

**Settings Hierarchy:**

```
Settings (root)
├── environment: str (development | production)
├── log_level: str (INFO | DEBUG | WARNING)
├── alpha_vantage_api_key: str (from env)
├── anthropic_api_key: str (from env)
├── broker: BrokerSettings
│   ├── provider: str (ibkr | simulated | paper_stub)
│   ├── paper_trading: bool
│   └── ibkr: IBKRSettings
│       ├── host: str (default: 127.0.0.1)
│       ├── port: int (4002=paper Gateway, 4001=live Gateway, 7497=paper TWS, 7496=live TWS)
│       ├── client_id: int (default: 1; data=+1, feed=+2)
│       └── account_id: str (blank for single-account setups)
├── data: DataSettings
│   ├── alpha_vantage: rate_limit_per_minute, cache_ttl_hours
│   ├── edgar: user_agent, rate_limit_per_second
│   ├── universe: cache_ttl_seconds (24h), fallback_csv
│   ├── feed: feed_type (iex=free/delayed, sip=paid/realtime), symbols_per_connection, reconnect_delay_seconds, max_reconnect_attempts
│   └── finra: rate_limit_per_minute, cache_ttl_seconds, base_url
├── database: DatabaseSettings (url, pool_size, max_overflow)
├── redis: RedisSettings (url, cache_ttl_seconds)
├── strategy: StrategySettings
│   ├── min_sharpe_ratio, min_profit_factor, max_drawdown_pct, min_trades
│   ├── walk_forward: train_months (24), test_months (6), step_months (3)
│   └── ranking_weights: sharpe (0.30), sortino (0.20), max_drawdown_inverse (0.20), profit_factor (0.15), consistency (0.15)
├── execution: ExecutionSettings (default_order_type, limit_offset_pct, max_slippage_pct, position_sizing: "half_kelly")
├── ml: MLSettings
│   ├── prediction_horizon: 5, up_threshold: 0.01, down_threshold: -0.01
│   ├── min_training_samples: 500, retrain_interval_days: 7, model_staleness_days: 14, confidence_threshold: 0.55
│   └── xgb_params: n_estimators, max_depth, learning_rate, subsample, colsample_bytree, objective=multi:softprob, num_class=3
├── scheduler: SchedulerSettings
│   ├── enabled: bool
│   ├── daily_bars_cron: "0 17 * * 1-5" (5pm ET weekdays)
│   ├── weekly_fundamentals_cron: "0 6 * * 6" (6am Saturday)
│   ├── biweekly_altdata_cron: "0 7 1,15 * *" (7am 1st/15th)
│   └── weekly_retrain_cron: "0 2 * * 0" (2am Sunday)
├── router: RouterSettings
│   ├── size_threshold_small_pct: 0.1, size_threshold_large_pct: 1.0
│   ├── twap_num_slices: 5, twap_interval_seconds: 60
│   └── wide_spread_threshold_bps: 20.0
├── monitoring: MonitoringSettings (prometheus_port: 8001, health_check_interval_seconds: 60)
└── risk: RiskSettings
    ├── autonomy_mode: PAPER_ONLY | MANUAL_APPROVAL | BOUNDED_AUTONOMOUS | FULL_AUTONOMOUS
    ├── position_limits: max_position_pct (5.0), max_sector_pct (25.0), stop_loss_pct (2.0), min_price (5.0), no_leverage (true)
    ├── portfolio_limits: max_drawdown_pct (10.0), max_daily_loss_pct (3.0), max_positions (20), max_daily_trades (50), min_cash_reserve_pct (10.0)
    ├── pdt_guard: enabled (true), max_day_trades (3), rolling_window_days (5), account_threshold (25000.0)
    ├── circuit_breakers: vix_threshold (35.0), stale_data_seconds (300), max_reconciliation_drift_pct (1.0), dead_man_switch_hours (48)
    └── kill_switch: http_enabled (true), telegram_enabled (false), cooldown_minutes (60)
```

**Loading Mechanism:**

```python
from src.core.config import get_settings

settings = get_settings()  # singleton, cached with @functools.lru_cache
```

The `Settings.from_yaml()` classmethod:
1. Loads `config/settings.yaml` and `config/risk_limits.yaml`
2. Flattens nested dicts into Pydantic Settings kwargs
3. Pydantic Settings then overlays env vars (`SA_*`) on top of YAML values
4. Returns fully merged `Settings` instance

### `src/core/database.py`

SQLAlchemy async engine and session factory for [TimescaleDB](../glossary.md#timescaledb) (PostgreSQL-compatible).

**Usage:**

```python
from src.core.database import get_session

async def example():
    async for session in get_session():
        # Use session for queries
        result = await session.execute(text("SELECT * FROM ohlcv WHERE symbol = :sym"), {"sym": "AAPL"})
        # session auto-closes on exit
```

**Key Functions:**
- `get_engine()`: Returns singleton async engine. Created once with pool settings from `config.database`.
- `get_session_factory()`: Returns `async_sessionmaker` for creating sessions.
- `get_session()`: Async generator yielding a session (use with FastAPI Depends or `async for`).

**Connection String:**
- Default: `postgresql+asyncpg://trader:dev_password@localhost:5432/stock_analysis`
- Override with `SA_DATABASE__URL` env var

### `src/core/redis.py`

[Redis](../glossary.md#redis) client singleton for caching, pub/sub, and ephemeral state (PDT tracking, idempotency keys, kill switch).

**Usage:**

```python
from src.core.redis import get_redis

redis = await get_redis()
await redis.set("key", "value", ex=3600)
value = await redis.get("key")
await redis.publish("channel", "message")
```

**Key Functions:**
- `get_redis()`: Returns singleton Redis client. Created once from `config.redis.url`.
- `close_redis()`: Closes the connection (called on shutdown).

**Default URL:**
- `redis://localhost:6379/0`
- Override with `SA_REDIS__URL` env var

## Configuration Examples

**Override broker to IBKR live:**
```bash
export SA_BROKER__PROVIDER=ibkr
export SA_BROKER__PAPER_TRADING=false
export SA_BROKER__IBKR__PORT=4001  # IB Gateway live
```

**Override ML thresholds:**
```bash
export SA_ML__PREDICTION_HORIZON=3
export SA_ML__UP_THRESHOLD=0.015
export SA_ML__CONFIDENCE_THRESHOLD=0.60
```

**Override risk limits:**
```bash
export SA_RISK__POSITION_LIMITS__MAX_POSITION_PCT=3.0
export SA_RISK__PORTFOLIO_LIMITS__MAX_DRAWDOWN_PCT=5.0
```

## Integration with Other Modules

- **Data ingestion** adapters implement `DataSourceInterface` and `FilingSourceInterface`
- **Strategy engine** registers strategies implementing `BaseStrategy`
- **Execution engine** uses a `BrokerAdapter` (IBKR/PaperStub/Simulated) selected by `config.broker.provider`
- **Risk manager** implements `RiskManager` interface and reads limits from `config.risk`
- **Scheduler** reads cron expressions from `config.scheduler`
- **API** reads `config.monitoring.prometheus_port` and serves metrics
- **All modules** call `get_settings()` for their respective config sections

## Critical Patterns

1. **Immutable Pydantic models**: All models are `BaseModel` with default factories, not raw dicts. Use `.model_copy()` for mutations.
2. **Enums for type safety**: Use `OrderSide.BUY`, not string `"BUY"`.
3. **Optional fields are typed correctly**: `float | None`, not `Optional[float]` (Python 3.10+ union syntax).
4. **Config is singleton**: `get_settings()` is cached — changes require restart.
5. **Async-first**: Database and Redis are async. Use `await` for all I/O.
6. **Lazy imports in optional deps**: Heavy deps (xgboost, pandas_ta) are imported inside functions, not at module top-level.

## Glossary Links

- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [OHLCV](../glossary.md#ohlcv) — Open/High/Low/Close/Volume bar data
- [PDT](../glossary.md#pdt) — Pattern Day Trader rule
- [Redis](../glossary.md#redis) — In-memory data store
- [TimescaleDB](../glossary.md#timescaledb) — Time-series PostgreSQL extension
- [XGBoost](../glossary.md#xgboost) — Gradient boosting ML library

<!-- DIAGRAM: Core module dependencies — show how config/models/interfaces are imported by all other modules -->
