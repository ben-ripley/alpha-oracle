# Feature Specifications

## F-001: Data Ingestion Pipeline
- Source adapters (Alpaca, Alpha Vantage, EDGAR) implementing `DataSourceInterface`
- Redis-backed rate limiter (token bucket per source)
- Normalizer: canonical schemas for OHLCV, fundamentals, filings
- Storage: TimescaleDB (time-series) + DuckDB/Parquet (analytics)
- Prefect orchestration: daily OHLCV, weekly fundamentals, 6-hourly filings, persistent WebSocket for real-time

## F-002: Strategy Engine
- `BaseStrategy` class with `generate_signals()`, `get_parameters()`, `get_required_data()`
- Backtrader wrapper for event-driven backtesting with walk-forward validation
- VectorBT wrapper for parameter optimization
- Strategy ranker with composite scoring and minimum thresholds
- Built-in strategies (all swing/position-oriented due to PDT rule):
  - **SwingMomentum**: Multi-day momentum with moving average crossover (hold 3-10 days)
  - **MeanReversion**: Bollinger Band reversion with RSI confirmation (hold 2-5 days)
  - **ValueFactor**: Ranks stocks by composite value score, rebalance weekly/monthly
  - **InsiderFollowing**: Buys stocks with significant insider purchases (hold weeks-months)
  - No intraday or day-trading strategies (PDT constraint)

## F-003: Signal Generation (ML) — Phase 2
- Feature engineering pipeline (scikit-learn): 50+ technical indicators, fundamental ratios, cross-asset, alternative data, temporal features
- XGBoost with Bayesian hyperparameter tuning (Optuna), weekly retraining
- Walk-forward train/test splits, feature importance tracking
- Model monitoring: accuracy tracking, feature drift detection, automatic fallback to rule-based

## F-004: Trade Execution Engine
- Order generator: Signal + RiskCheck -> Order (Kelly criterion sizing, half-Kelly for safety)
- Pre-trade risk check on every order (calls F-005)
- `BrokerAdapter` interface with `AlpacaBrokerAdapter` implementation
- Execution tracker: order status monitoring, fill events to Redis, audit trail in TimescaleDB
- Smart order routing (Phase 2+): adaptive limit orders, TWAP/VWAP for larger orders

## F-005: Risk Management System
- Pre-trade risk engine: synchronous APPROVE/REJECT/REQUIRE_HUMAN_APPROVAL
- Real-time portfolio monitor: P&L, drawdown, exposure, stop-loss proximity
- Circuit breaker manager: health checks, VIX, operator heartbeat
- Reconciliation engine: internal vs broker positions every 5 min
- Kill switch: HTTP + Telegram + CLI

## F-006: AI Agent Decision Layer — Phase 2-3
- Document Analyst Agent: SEC filings + earnings calls -> structured sentiment/insights via Claude
- Trade Advisor Agent (LangGraph): signal -> gather context -> Claude analysis -> recommendation -> [human review] -> execute/skip
- Portfolio Review Agent: daily briefing, position monitoring, catalyst calendar
- Guardrails: agents can read but never directly submit orders

## F-007: Monitoring & Alerting
- Prometheus metrics: system, application, trading, ML
- Grafana dashboards: operations, trading, risk, strategy performance
- Alerts via Slack/Telegram: CRITICAL (circuit breaker, reconciliation), WARNING (approaching limits), INFO (trades, summaries)
- Full audit log in TimescaleDB

## F-008: Web Dashboard (React)
- **Portfolio page:** Current positions, P&L (realized/unrealized), allocation chart, account value over time
- **Strategies page:** Strategy list with backtest results, ranking scores, live vs backtest performance comparison
- **Backtest page:** Run backtests, visualize equity curves, compare strategies, parameter optimization results
- **Risk page:** Drawdown chart, limit utilization bars, circuit breaker status, PDT trade counter (X/3 used)
- **Trades page:** Trade history, pending approvals (in MANUAL_APPROVAL mode), execution quality metrics
- **Agent page (Phase 3):** AI analysis results, trade recommendations, daily briefings
- **Real-time updates:** WebSocket connection for live P&L, new trades, alerts
- **Trade approval UI:** Approve/reject/modify pending trades directly from the dashboard
