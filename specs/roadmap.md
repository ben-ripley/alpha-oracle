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
| 11 | `POST /api/strategies/backtest` non-blocking endpoint: ThreadPoolExecutor background job, Redis job tracking (`backtest:job:{uuid}`), async OHLCV load via `asyncio.gather`, 1h TTL, `estimated_seconds` via rolling `ms_per_symbol` calibration | Done |
| 12 | `GET /api/strategies/backtest/jobs/{id}` polling endpoint: returns job status (running/complete/failed) + result from Redis | Done |
| 13 | Equal-weight position sizing in `SignalStrategy`: fixed `initial_capital / max_positions` per slot, capacity cap skips signals when at `max_positions`, reads limit from `risk_limits.yaml` in production | Done |
| 14 | Run Backtest panel on Strategies page: form (strategy/symbols/dates/capital), artificial time-based progress bar driven by `ms_per_symbol` rolling average, 8-metric results card, polling via `backtestJob` API method | Done |

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

| Track | Deliverable | Status |
|---|---|---|
| A1 | Pydantic models for all agent/analysis types with schema versioning; tiered model config (Sonnet for analyst/briefing, Haiku for advisor); AgentSettings with response caching, rate limits, budget | Done |
| A2 | Agent base infrastructure: BaseAgent ABC, CostTracker (SHA-256 response cache, budget enforcement), AgentRateLimiter (token-bucket per endpoint), LLM guardrails decorator | Done |
| B1 | Data adapters: NewsAdapter (Alpha Vantage NEWS_SENTIMENT), AnalystEstimatesAdapter (AV EARNINGS+OVERVIEW), OptionsFlowAdapter (stub), GoogleTrendsAdapter (stub — pytrends not used, unreliable) | Done |
| B2 | Feature calculators: SentimentFeatureCalculator, EstimatesFeatureCalculator, OptionsFlowFeatureCalculator, TrendsFeatureCalculator — all PIT-safe, return NaN on missing data; FeatureStore extended with 4 optional params | Done |
| B3 | FinBERT sentiment scorer (`src/agents/sentiment_scorer.py`) — optional dep, graceful fallback to `[]` if transformers/torch not installed | Done |
| C1 | ClaudeAnalystAgent: tool_use structured output, tenacity retry, response caching, Redis storage; prompts with few-shot examples | Done |
| C2 | TradeAdvisorAgent: plain async workflow (no LangGraph), autonomy mode gating (PAPER/MANUAL→queue, BOUNDED→auto at confidence≥0.7, FULL→auto); PortfolioReviewAgent: daily DailyBriefing generation; context.py with graceful fallback | Done |
| D1 | MonteCarloSimulator: bootstrapped simulation, 5 percentile bands, VaR 95%, probability of loss | Done |
| D2 | RegimeDetector: rule-based only (50/200 MA + VIX) — no HMM; BULL/BEAR/SIDEWAYS/HIGH_VOLATILITY with confidence scores | Done |
| D3 | MultiStrategyOptimizer: scipy mean-variance, Sharpe maximization, weights in [0, 0.40], sums to 1.0 | Done |
| E1 | AutonomyValidator with tightened thresholds: MANUAL→BOUNDED requires 30d + Sharpe≥0.5 + drawdown check; BOUNDED→FULL requires 90d + Sharpe≥0.5 + drawdown + circuit breakers tested + guardrails verified + typed confirmation | Done |
| E2 | LLMGuardrailsEngine: broker import check, Redis timestamp, recency check, stale-timestamp cleared on failure | Done |
| F1 | Scheduling: daily_sentiment_job, daily_briefing_job, weekly_options_flow_job, weekly_trends_job — all check agent.enabled, idempotent, per-symbol error isolation; weekly_fundamentals_job extended with analyst estimates | Done |
| G1 | API routes: /api/agent/* (10 endpoints, rate-limited, 503 when disabled), /api/analysis/* (3 endpoints, always available), autonomy-mode transition + guardrail status on /api/risk/* | Done |
| G2 | WebSocket: agent:analysis, agent:recommendation, agent:briefing, agent:cost channels | Done |
| H1 | Frontend: Agent dashboard (cost tracker, daily briefing, recommendations with approve/reject, filing analyses), Analysis page (Monte Carlo fan chart, regime timeline, autonomy readiness), AutonomyModeSection on Risk page | Done |
| I1 | Graceful degradation: agent disabled → 503 APIs + scheduler early-return; FinBERT missing → empty sentiment; feature calculators missing data → NaN; analysis endpoints always work | Done |
| I2 | Documentation: CLAUDE.md updated; llm-agents.md, full-autonomous.md, agents module guide, llm-guardrails architecture, agent operations runbook | Done |

**1,119 tests passing (+450 from Phase 3). 0 failures.**

**Status: IMPLEMENTED**

---

## Phase 4 (Optional): Expanded Universe — S&P 400 / S&P 600

Extend the trading universe beyond S&P 500 to include mid-cap (S&P 400) and/or small-cap (S&P 600) equities, increasing the symbol pool from ~425 to ~1,500 and giving the ML model a broader cross-section of return patterns.

### Why mid/small-cap over full Nasdaq
- S&P 400 and S&P 600 are curated, liquid, well-documented indices — no penny stocks or micro-caps
- Meaningful diversification away from large-cap tech concentration in S&P 500
- Existing risk controls (min_price=$5, position limits, PDT guard) apply without modification
- Full Nasdaq (~3,300 symbols) introduces too much illiquid noise for a <$25K account

### Work required

| Task | Deliverable |
|---|---|
| 1 | Update `SymbolUniverse` (`src/data/universe.py`) to support multiple index sources — Wikipedia scrape for S&P 400 and S&P 600, separate Redis cache keys, configurable via `settings.yaml` |
| 2 | Add `universe.indices` config list (`["sp500", "sp400", "sp600"]`) to `config/settings.yaml`; default remains `["sp500"]` |
| 3 | Update `scripts/backfill_history_yf.py` to accept `--symbols sp400`, `--symbols sp600`, `--symbols sp1500` (combined) |
| 4 | Extend `StrategyRanker` and `MLPipeline` to handle larger feature matrices without memory issues |
| 5 | Add liquidity filter to universe: minimum 30-day ADV threshold to exclude thinly traded names |
| 6 | Backfill S&P 400 and/or S&P 600 history (same 5-year window via yfinance) |
| 7 | Re-run walk-forward validation and retrain XGBoost on expanded universe |

### Prerequisites
- Phase 3 complete and stable in BOUNDED_AUTONOMOUS mode
- Sufficient compute for retraining on ~1,500 symbols (memory and time will increase ~3x)
- Review position sizing — Kelly criterion on small-caps may produce oversized positions without an ADV cap

**This phase is entirely optional.** The S&P 500 universe is sufficient for the system's target use case. Expand only if the ML model's signal quality plateaus and broader diversification is needed.

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
