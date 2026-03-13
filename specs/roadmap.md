# Implementation Roadmap

## Context

AI-driven automated stock trading system for a retail investor managing US equities through a personal brokerage account (under $25K capital).

### Key Constraints
- **Pattern Day Trader (PDT) Rule:** Under $25K capital means max 3 day trades per rolling 5 business days. All strategies focus on swing trading (2-10 day holds) and position trading (weeks-months).
- **Web Dashboard Required:** React/TypeScript web dashboard as primary interface.
- **Cost Sensitivity:** Free data tier ($0/mo) starting point; any paid upgrade must justify itself against returns on a small capital base.

---

## Phase 1: MVP - Data + Backtesting + Paper Trading + Dashboard

| Task | Deliverable | Status |
|---|---|---|
| 1 | Project scaffolding: repo, Docker Compose (TimescaleDB, Redis), Pydantic config, FastAPI skeleton, CI | Done |
| 2 | Data ingestion: IBKR + Alpha Vantage adapters, normalizer, TimescaleDB storage | Done |
| 3 | Backtest framework: Backtrader integration, walk-forward validation, metrics calculation | Done |
| 4 | Rule-based swing strategies: SwingMomentum, MeanReversion, ValueFactor (all multi-day holds) | Done |
| 5 | Execution engine: IBKR paper trading, pre-trade risk checks (incl. PDT guard), order tracking | Done |
| 6 | Risk management: portfolio monitor, circuit breakers, kill switch, reconciliation | Done |
| 7 | FastAPI backend: REST endpoints for portfolio, strategies, risk metrics, trades; WebSocket for real-time | Done |
| 8 | React web dashboard: portfolio overview, strategy performance, risk dashboard, trade approval UI | Done |
| 9 | InsiderFollowing strategy: SEC Form 4 cluster-buy detection, 21-day hold, net-selling exit | Done |
| 10 | Backtest dashboard page: equity curve, trade log, stats grid, strategy selector | Done |

**Exit criteria:** Paper trading 30+ days, risk limits enforced, Sharpe > 1.0 in backtest, web dashboard operational. Mode: `PAPER_ONLY`

**Status: IMPLEMENTED**

---

## Phase 2: ML Signals + Live Trading

| Track | Deliverable | Status |
|---|---|---|
| A1 | S&P 500 Universe Manager (`src/data/universe.py`) — Wikipedia scrape, Redis cache, CSV fallback | Done |
| A2 | Live Market Data Feed (`src/data/feeds/`) — IBKR WebSocket feed (IBKRMarketFeed), Redis pub/sub | Done |
| A3 | Form 4 Insider Transaction Parser (`src/data/parsers/form4_parser.py`) — XML, typed models | Done |
| A4 | FINRA Short Interest Scraper (`src/data/adapters/finra_adapter.py`) — caching, days-to-cover | Done |
| B1 | Technical Feature Calculator (`src/signals/features/technical.py`) — 25 features | Done |
| B2 | Fundamental Feature Calculator (`src/signals/features/fundamental.py`) — sector percentiles, quality score | Done |
| B3 | Cross-Asset & Alternative Data Features — SPY beta, sector RS, VIX regime, insider signals | Done |
| B4 | Feature Store with Point-in-Time Joins (`src/signals/feature_store.py`) — 50+ features, no look-ahead bias | Done |
| C1 | XGBoost Training Pipeline (`src/signals/ml/pipeline.py`) — train/predict/save/load/feature_importance | Done |
| C2 | Walk-Forward Validation + Optuna Tuning (`src/signals/ml/validation.py`) — expanding/rolling windows | Done |
| C3 | Signal Generation Service — `ConfidenceCalibrator` (isotonic/Platt), `MLSignalStrategy(BaseStrategy)` | Done |
| C4 | Model Monitoring & Drift Detection (`src/signals/ml/monitoring.py`) — PSI drift, Prometheus gauges | Done |
| C5 | Scheduler Orchestration (`src/scheduling/`) — APScheduler, 4 cron jobs, Model Registry | Done |
| D1 | Execution Quality Tracking (`src/execution/quality.py`) — slippage, latency, aggregation | Done |
| D2 | Smart Order Router (`src/execution/router.py`) — market/limit/TWAP routing by ADV+spread+urgency | Done |
| E1 | ML Dashboard Widgets — SignalFeed, FeatureImportance, ModelPerformance on Strategies page | Done |
| E2 | Model Monitoring Dashboard — AccuracyChart, DriftHeatmap, ModelVersionHistory components | Done |
| E3 | Model Health dedicated page (`/model-health`) — status bar, all monitoring widgets, own nav route | Done |

**~248 additional tests added (669 total). TypeScript compiles clean.**

**Status: IMPLEMENTED**

---

## Phase 3: LLM Agent + Full Automation

| Week | Deliverable |
|---|---|
| 1 | Claude analyst agent: filing analysis, earnings summarization |
| 2 | FinBERT sentiment pipeline, news sentiment as ML feature |
| 3 | Trade advisor agent (LangGraph), daily portfolio briefings in dashboard |
| 4 | Alternative data batch 2: analyst estimates, options flow |
| 5 | Monte Carlo simulation, regime analysis, multi-strategy optimization |
| 6 | FULL_AUTONOMOUS mode with all circuit breakers |
| 7 | Production hardening, documentation, runbooks, dashboard polish |

**Exit criteria:** BOUNDED_AUTONOMOUS profitable 60+ days, LLM measurably improves signals. Mode: -> `FULL_AUTONOMOUS`

---

## Cost Analysis

| Phase | Monthly Cost | What's Included |
|---|---|---|
| Phase 1 | $0-25 | All free: IBKR + Alpha Vantage + EDGAR. Optional $5-20 VPS. |
| Phase 2 | $30-100 | + VPS for ML ($10-30) + Claude API ($10-30) + optional data upgrade ($0-50) |
| Phase 3 | $75-250 | + heavier Claude usage ($30-80) + paid data ($20-80) + options flow ($0-30) |

**Break-even at <$25K capital:** At $50/month operating cost, need $600/yr excess returns. On $20K capital that's 3% alpha -- achievable but not guaranteed. Keeping Phase 1-2 costs near $0-25/mo is critical.

---

## Verification (End-to-End Test - Phase 1)

1. `docker-compose up` - starts TimescaleDB, Redis, Prometheus, Grafana, FastAPI, React dev server
2. `python -m src.data.ingest --backfill --symbols SPY,AAPL,MSFT` - backfills 10 years of daily data
3. `python -m src.strategy.backtest --strategy SwingMomentum --start 2015-01-01` - runs backtest with walk-forward validation
4. `python -m src.strategy.rank` - ranks all strategies by composite score
5. Open web dashboard at localhost:3000 - verify portfolio, strategies, risk pages render
6. `python -m src.execution.paper_trade --mode PAPER_ONLY` - starts paper trading
7. Verify real-time updates appear in web dashboard via WebSocket
8. Verify PDT guard blocks a 4th day trade within 5 business days
9. Test kill switch via dashboard button and Telegram `/kill` command
10. Verify Grafana monitoring at localhost:9090 shows system metrics

### Key risks to watch
- Alpha Vantage rate limits during initial backfill (hours, not minutes)
- Walk-forward validation reducing effective training data
- Strategy decay in live markets vs backtest
- PDT rule enforcement must be bulletproof -- a bug here could trigger FINRA restrictions on the account
