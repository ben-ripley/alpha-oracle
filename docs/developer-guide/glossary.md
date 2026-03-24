---
title: Developer Glossary
nav_order: 9
parent: Developer Guide
---

# Developer Glossary

Technical infrastructure and financial/ML terms for developers working on the AlphaOracle system.

---

### ABC (Abstract Base Class) {#abc}
Python base class that defines an interface contract. The system uses ABCs extensively (`DataSourceInterface`, `BaseStrategy`, `BrokerAdapter`, `RiskManager`, `BacktestEngine`) to enforce consistent APIs across implementations.

### ADV (Average Daily Volume) {#adv}
Average number of shares traded daily over a period. The smart order router uses ADV percentage thresholds: >5% of ADV triggers TWAP, <1% ADV with tight spread allows market order.

### APScheduler {#apscheduler}
Python library for cron-style job scheduling. The system runs 4 scheduled jobs: `daily_bars` (5pm ET weekdays), `weekly_fundamentals` (6am Sat), `biweekly_altdata` (7am 1st/15th), `weekly_retrain` (2am Sun).

### AsyncPG {#asyncpg}
High-performance PostgreSQL driver for asyncio. Used by SQLAlchemy async engine for database operations. Significantly faster than psycopg2 for high-throughput workloads.

### Backtrader {#backtrader}
Python backtesting framework with event-driven architecture. The system uses Backtrader alongside VectorBT to validate strategies on historical data with point-in-time integrity.

### Bracket Order {#bracket-order}
Order with attached take-profit and stop-loss levels. IBKR supports native bracket orders; the execution engine constructs them as parent-child orders.

### Circuit Breaker {#circuit-breaker}
Automated trading halt triggered by risk conditions. Implemented in `src/risk/circuit_breakers.py`: VIX > 35, max drawdown > 10%, stale data (>15min), reconciliation failures, dead man switch timeout.

### Client ID (IBKR) {#client-id}
Unique identifier for IBKR API connections. The system uses a scheme: broker adapter = `client_id`, data adapter = `client_id+1`, market feed = `client_id+2` (defaults 1/2/3). Never reuse IDs across simultaneous connections.

### Confidence Calibration {#confidence-calibration}
Adjusting ML model probability outputs to match empirical frequencies. The system uses Platt Scaling after XGBoost training so a 70% confidence prediction is actually correct ~70% of the time.

### Cron Expression {#cron-expression}
Schedule format: `minute hour day month day_of_week`. Example: `0 17 * * 1-5` = 5pm ET Monday-Friday. APScheduler uses cron expressions for job scheduling.

### Day Trade {#day-trade}
Opening and closing the same security within a single trading day. PDT guard logic in `src/risk/pdt_guard.py` tracks day trades per rolling 5 business days, enforcing the 3-trade limit for sub-$25K accounts.

### DuckDB {#duckdb}
In-process analytical database optimized for OLAP queries. The system uses DuckDB for fast feature engineering queries on Parquet files during ML training and backtesting.

### Feature Store {#feature-store}
Centralized repository for ML features with point-in-time correctness. Located in `src/signals/feature_store.py`, orchestrates 50+ features across technical, fundamental, cross-asset, and alternative data categories. Persists to Parquet.

### FINRA {#finra}
Financial Industry Regulatory Authority. Source of short interest data (biweekly updates) ingested by `src/data/adapters/finra_adapter.py` as alternative features.

### Form 4 {#form-4}
SEC filing for insider transactions. The system parses Form 4 XML via `src/data/parsers/form4_parser.py` to generate insider buying/selling features for the ML model.

### Grafana {#grafana}
Visualization and alerting platform. The system's `docker-compose.yml` includes Grafana (port 3001) with pre-configured dashboards for metrics scraped by Prometheus.

### Half-Kelly {#half-kelly}
Position sizing using 50% of the Kelly Criterion optimal fraction. Implemented in `src/execution/order_generator.py`: `position_size = 0.5 * kelly_fraction * portfolio_value / price`.

### Health Check {#health-check}
Endpoint or function verifying system component availability. The API exposes `/api/system/health` checking database, Redis, IBKR connection, data freshness, and scheduler status.

### Hypertable {#hypertable}
TimescaleDB's time-series optimized table type. The system converts `bars`, `trades`, `portfolio_snapshots`, and `predictions` tables to hypertables for efficient time-range queries and compression.

### IB Gateway {#ib-gateway}
Interactive Brokers' lightweight API gateway (vs full TWS). Paper trading port 4002, live port 4001. The system connects via `ib_async` library configured in `src/execution/adapters/ibkr_broker_adapter.py`.

### IBKR (Interactive Brokers) {#ibkr}
Brokerage firm providing API-based trading and market data. The system uses IBKR as its broker via IB Gateway or TWS. Client ID scheme: broker adapter = `client_id` (1), data adapter = `client_id+1` (2), market feed = `client_id+2` (3). Configured in `config/settings.yaml` under `broker.ibkr`.

### Idempotency Key {#idempotency-key}
Unique identifier ensuring operations aren't repeated. The scheduler uses Redis keys like `jobs:daily_bars:{date}:done` to prevent duplicate job execution on restarts.

### Kelly Criterion {#kelly-criterion}
Optimal position sizing formula: `f = (p*w - l) / w` where p=win_probability, w=avg_win, l=avg_loss. The system uses Half-Kelly (0.5 * f) for conservative sizing.

### Kill Switch {#kill-switch}
Emergency system shutdown mechanism. Implemented in `src/risk/kill_switch.py` with typed confirmation ("KILL"/"RESUME") required. Sets Redis flag and database state; all execution checks this before trading.

### Limit Order {#limit-order}
Order specifying maximum buy or minimum sell price. The smart router uses limit orders for mid-liquidity stocks (1-5% ADV) or when spread > 0.2% and urgency is low.

### MACD (Moving Average Convergence Divergence) {#macd}
Trend indicator calculated as `MACD = EMA(12) - EMA(26)` with signal line `EMA(MACD, 9)`. Provided by `src/strategy/builtin/_indicators.py` shim falling back from pandas_ta to ta library.

### Market Order {#market-order}
Order executing immediately at best available price. The router uses market orders for highly liquid stocks (<1% ADV, spread <0.1%) when urgency is high.

### Max Drawdown {#max-drawdown}
Largest peak-to-trough decline. Circuit breaker triggers at 10% max drawdown. Calculated in `src/risk/portfolio_monitor.py` tracking equity curve highs and current value.

### Model Registry {#model-registry}
Service managing ML model versions, promotion, and rollback. Implemented in `src/signals/ml/registry.py`, tracks metadata (accuracy, drift, timestamp) in database and stores pickled models in `models/` directory.

### OHLCV {#ohlcv}
Open, High, Low, Close, Volume bars. Primary time-series data stored in TimescaleDB `bars` hypertable. Ingested from IBKR WebSocket feed and Alpha Vantage historical API.

### Optuna {#optuna}
Hyperparameter optimization framework. The system's `src/signals/ml/training.py` uses Optuna for walk-forward validation: trains XGBoost on in-sample data, tunes hyperparameters, validates on out-of-sample periods.

### Parquet {#parquet}
Columnar storage format optimized for analytics. The feature store persists features to Parquet files (`data/features/*.parquet`) for fast DuckDB queries during backtesting and training.

### PDT (Pattern Day Trader) {#pdt}
FINRA rule requiring $25K minimum for 4+ day trades in 5 business days. The PDT guard (`src/risk/pdt_guard.py`) is the system's most critical safety component, conservatively rejecting trades when in doubt.

### Platt Scaling {#platt-scaling}
Logistic regression calibration method for ML probability outputs. Applied in `src/signals/ml/confidence_calibrator.py` after XGBoost training to ensure confidence scores match empirical accuracy.

### Point-in-Time (PIT) {#point-in-time}
Data as it existed at a historical timestamp, preventing look-ahead bias. The feature store's `FeatureCalculator.calculate()` method enforces PIT constraints: only uses data available before each bar's timestamp.

### Position Sizing {#position-sizing}
Determining trade size. The order generator (`src/execution/order_generator.py`) applies Half-Kelly with constraints: max 5% per position, 25% per sector, $5 minimum price, 10% cash reserve.

### Profit Factor {#profit-factor}
Gross profit / gross loss ratio. Calculated by backtest engines and displayed on strategy cards. Values > 1.5 considered good, > 2.0 excellent.

### Prometheus {#prometheus}
Time-series metrics database and monitoring system. The system exposes metrics at `/metrics` endpoint (port 8000), scraped by Prometheus container (port 9090) configured in `config/prometheus/prometheus.yml`.

### PSI (Population Stability Index) {#psi}
Feature drift metric comparing training vs. production distributions. PSI < 0.1 = stable, 0.1-0.25 = moderate drift, >0.25 = significant drift. Monitored by `src/signals/ml/model_monitoring.py`.

### Pub/Sub {#pubsub}
Publish-subscribe messaging pattern. The system uses Redis pub/sub channels (`signals`, `executions`, `trades`, `risk_events`) to decouple modules. WebSocket endpoint subscribes to channels for real-time dashboard updates.

### Pydantic {#pydantic}
Python data validation library using type hints. All models defined in `src/core/models.py` inherit from `pydantic.BaseModel`, providing validation, serialization, and IDE type checking.

### Redis {#redis}
In-memory data store used for pub/sub, caching (market data, signal cache), session state, and idempotency keys. Configured via `src/core/redis_client.py`, runs on port 6379 in Docker.

### RSI (Relative Strength Index) {#rsi}
Momentum oscillator (0-100). Calculated as `RSI = 100 - 100/(1 + RS)` where RS = avg_gain / avg_loss over 14 periods. Provided by `_indicators.py` shim.

### Sharpe Ratio {#sharpe-ratio}
Risk-adjusted return: `(portfolio_return - risk_free_rate) / portfolio_volatility`. Higher is better; >1.0 good, >2.0 excellent. Calculated by backtest engines and displayed in strategy performance metrics.

### Short Interest {#short-interest}
Percentage of float sold short. The system ingests FINRA short interest data via `src/data/adapters/finra_adapter.py`, updated biweekly. High short interest can signal contrarian opportunity or short squeeze risk.

### Signal {#signal}
Trading recommendation generated by strategies or ML models. Represented by `Signal` Pydantic model with action (BUY/SELL/HOLD), confidence (0-1), symbol, and rationale. Published to Redis `signals` channel.

### Slippage {#slippage}
Difference between expected and actual execution price. The execution quality tracker (`src/execution/quality_tracker.py`) monitors slippage by comparing fill price to mid-quote at order submission time.

### Sortino Ratio {#sortino-ratio}
Risk-adjusted return penalizing only downside volatility: `(return - risk_free) / downside_deviation`. Preferred over Sharpe when upside volatility is desirable. Tracked in strategy performance metrics.

### SQLAlchemy {#sqlalchemy}
Python SQL toolkit and ORM. The system uses SQLAlchemy 2.0 async API (`AsyncSession`, `select()`) with AsyncPG driver. Models in `src/core/database.py` map to TimescaleDB tables.

### Stop-Loss {#stop-loss}
Order closing position when price hits specified level. The order generator sets ATR-based stop-losses: `stop_price = entry - (2 * ATR)` for longs, `entry + (2 * ATR)` for shorts.

### Structlog {#structlog}
Structured logging library producing JSON logs. Configured in `src/core/logging.py`, logs include timestamp, level, module, and contextual key-value pairs for easy parsing and alerting.

### Technical Indicator {#technical-indicator}
Calculation derived from price/volume data (RSI, MACD, Bollinger Bands, etc.). The system's `_indicators.py` shim provides unified API falling back from pandas_ta to ta library for compatibility.

### TimescaleDB {#timescaledb}
PostgreSQL extension optimized for time-series data. The system uses hypertables for efficient time-range queries, automatic partitioning, and compression. Runs on port 5432 in Docker.

### TWAP (Time-Weighted Average Price) {#twap}
Execution algorithm splitting orders across time intervals. The router triggers TWAP for large orders (>5% ADV) to reduce market impact. Implementation delegates to IBKR's native TWAP algo.

### TWS (Trader Workstation) {#tws}
Interactive Brokers' full trading platform. Alternative to IB Gateway with GUI. Paper port 7497, live 7496. The broker adapter auto-detects gateway vs TWS based on port.

### Universe {#universe}
The set of tradeable symbols the system monitors. Default is S&P 500, fetched from Wikipedia with a fallback CSV (`config/sp500_fallback.csv`). Managed by `src/data/universe.py` with a 24-hour cache. All scheduled jobs (daily bars, fundamentals, etc.) iterate over the universe.

### VectorBT {#vectorbt}
Vectorized backtesting library optimized for speed. The system uses VectorBT alongside Backtrader: VectorBT for fast parameter sweeps, Backtrader for event-driven simulation with realistic fills.

### VIX {#vix}
CBOE Volatility Index (S&P 500 implied volatility). VIX > 20 = elevated fear, >35 = panic. The system's circuit breakers halt trading when VIX > 35, fetched from market data adapters.

### Walk-Forward Validation {#walk-forward-validation}
Backtesting method training on period N, testing on N+1, then rolling forward. The ML pipeline (`src/signals/ml/training.py`) uses walk-forward with 252-day train windows, 63-day validation, stepping forward 21 days (monthly).

### WebSocket {#websocket}
Bidirectional communication protocol. The API exposes `/ws` endpoint pushing real-time updates from Redis pub/sub to the React dashboard. Also used by `IBKRMarketFeed` for streaming quotes.

### XGBoost {#xgboost}
Gradient boosting library optimized for tabular data. The system's ML strategy trains XGBoost on 50+ PIT features, using Optuna for hyperparameter tuning and Platt Scaling for confidence calibration. Model pickles stored in `models/` directory.
