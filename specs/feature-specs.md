# Feature Specifications

## F-001: Data Ingestion Pipeline
- Source adapters (IBKR, Alpha Vantage, EDGAR, FINRA) implementing `DataSourceInterface`
  - `IBKRDataAdapter` — historical bars + latest bar via `reqHistoricalDataAsync`; rate-limited to 6 req/min
  - `IBKRMarketFeed` — real-time quote streaming via `reqMktData`; auto-reconnects on disconnect
  - `AlphaVantageAdapter` — 20+ yr daily OHLCV, fundamentals (OVERVIEW endpoint); 5 req/min free tier
  - `EdgarAdapter` — SEC Form 4 insider transactions, 10-K/10-Q/8-K filings
  - `FinraAdapter` — biweekly short interest data
- Redis-backed rate limiter (token bucket per source) in `src/data/rate_limiter.py`
- Normalizer: canonical schemas for OHLCV, fundamentals, filings (`src/data/normalizer.py`)
- Storage: TimescaleDB time-series via `TimeSeriesStorage` + DuckDB/Parquet analytics
- APScheduler cron jobs (not Prefect): `daily_bars_job`, `weekly_fundamentals_job`, `biweekly_altdata_job`, `weekly_retrain_job`
  - All jobs are idempotent via Redis done-sets; per-symbol errors are isolated
- One-time backfill: `scripts/backfill_history.py --years 2 --symbols sp500` (resumable via Redis)

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
- **Backtest API** (`POST /api/strategies/backtest`): non-blocking background job via `ThreadPoolExecutor(max_workers=2)`; handler loads OHLCV with `asyncio.gather`, writes `backtest:job:{uuid}` to Redis (1h TTL), returns `{job_id, status, estimated_seconds}` immediately
- **Job polling** (`GET /api/strategies/backtest/jobs/{id}`): reads Redis key, returns status (`running` / `complete` / `failed`) + full `BacktestResult` on completion; registered before wildcard routes to prevent shadowing
- **Timing calibration**: Redis key `backtest:timing:ms_per_symbol` stores rolling average (weight 10%: `new = (old * 9 + sample) / 10`); fallback 50 ms/symbol; persists indefinitely so estimates improve with real runs
- **Equal-weight position sizing**: `SignalStrategy` allocates `initial_capital / max_positions` per slot; capacity cap skips buy signals when `len(_entry_bars) >= max_positions`; `max_positions` sourced from `risk_limits.yaml` (`portfolio_limits.max_positions`) or injected via `BacktraderEngine(max_positions=N)` constructor for testing

## F-003: Signal Generation (ML) — Phase 2
- Feature engineering pipeline (scikit-learn): 50+ technical indicators, fundamental ratios, cross-asset, alternative data, temporal features
- XGBoost with Bayesian hyperparameter tuning (Optuna), weekly retraining
- Walk-forward train/test splits, feature importance tracking
- Model monitoring: accuracy tracking, feature drift detection, automatic fallback to rule-based

## F-004: Trade Execution Engine
- Order generator: Signal + RiskCheck -> Order (Kelly criterion sizing, half-Kelly for safety)
- Pre-trade risk check on every order (calls F-005)
- `BrokerAdapter` interface (`src/core/interfaces.py`) with three implementations:
  - `IBKRBrokerAdapter` — live/paper trading via IB Gateway; exponential backoff reconnect
  - `SimulatedBroker` — in-memory fill simulation using latest stored OHLCV close ± 0.05% slippage; no external deps
  - `PaperStubBroker` — returns static demo data; rejects all orders (development fallback)
- Provider selected by `SA_BROKER__PROVIDER` env var (`ibkr` / `simulated` / other)
- Smart order router in `src/execution/router.py`: market/limit/TWAP based on ADV, spread, urgency
  - Reads `bid_price`/`ask_price` keys from IBKR market feed
- Execution quality tracker: slippage, latency, aggregation (`src/execution/quality.py`)

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
- **Strategies page:** Strategy list with backtest results, ranking scores, live vs backtest performance comparison; **Run Backtest panel** with form (strategy selector, comma-separated symbols, start/end dates, initial capital), artificial time-based progress bar (advances via elapsed ms vs `estimated_seconds * 1000`, capped at 95% until job completes), 8-metric results card (Total Return, Annual Return, Sharpe, Sortino, Max DD, Profit Factor, Win Rate, Trades), "Run another" reset
- **Backtest page:** Run backtests, visualize equity curves, compare strategies, parameter optimization results
- **Risk page:** Drawdown chart, limit utilization bars, circuit breaker status, PDT trade counter (X/3 used)
- **Trades page:** Trade history, pending approvals (in MANUAL_APPROVAL mode), execution quality metrics
- **Agent page (Phase 3):** AI analysis results, trade recommendations, daily briefings
- **Real-time updates:** WebSocket connection for live P&L, new trades, alerts
- **Trade approval UI:** Approve/reject/modify pending trades directly from the dashboard
