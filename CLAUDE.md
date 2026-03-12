# CLAUDE.md - Project Guide for AI Assistants

## Project Overview
AI-driven automated stock trading system for retail investor (<$25K, US equities).
Swing/position trading only — no day trading (PDT rule: max 3 day trades per 5 business days).

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy async, Redis, TimescaleDB, DuckDB
- **Frontend:** React 18, TypeScript, TailwindCSS, Vite, Recharts
- **ML (Phase 2):** XGBoost, scikit-learn
- **Infra:** Docker Compose (TimescaleDB, Redis, Prometheus, Grafana)
- **Broker:** Interactive Brokers (IBKR) via IB Gateway / TWS

## Project Structure
```
src/
  core/           # Models (Pydantic), interfaces (ABCs), config, database, redis
  data/           # Ingestion: IBKR/AlphaVantage/EDGAR/FINRA adapters; feeds; parsers; universe
  strategy/       # Engine, backtest (Backtrader/VectorBT), builtin strategies, ranker
  signals/        # Feature store (50+ PIT features), XGBoost pipeline, ML strategy, model monitoring
  scheduling/     # APScheduler cron jobs (bars, fundamentals, alt data, retrain), model registry
  execution/      # Order generator (Kelly sizing), smart router, broker adapter, quality tracker
  risk/           # PDT guard, pre-trade checks, circuit breakers, kill switch, reconciliation
  api/            # FastAPI routes: portfolio, strategies, risk, trades, system, websocket
  monitoring/     # Prometheus metrics, Slack/Telegram alerts
web/              # React dashboard (Portfolio, Strategies, Risk, Trades, Model Health pages)
config/           # settings.yaml, risk_limits.yaml, Prometheus/Grafana configs
tests/unit/       # 421 pytest tests
docs/adrs/        # Architecture Decision Records (001-009)
```

## Key Architecture Rules
- **Modular monolith** — modules communicate via Redis pub/sub, not microservices
- **Abstract interfaces** in `src/core/interfaces.py`: `DataSourceInterface`, `BaseStrategy`, `BrokerAdapter`, `RiskManager`, `BacktestEngine`
- **All models** in `src/core/models.py` — Pydantic BaseModel throughout
- **Config** loaded from YAML + env vars via Pydantic Settings (`src/core/config.py`)
- **Lazy imports** in `__init__.py` files for modules with heavy deps (alpaca, backtrader, pandas_ta)

## Critical Safety: PDT Guard
`src/risk/pdt_guard.py` is the most critical component. It prevents FINRA PDT violations.
- Accounts under $25K: max 3 day trades per rolling 5 business days
- Conservative: rejects when in doubt
- Every decision logged for audit
- **Never weaken or bypass PDT checks without explicit user instruction**

## Risk Management Layers
1. Position limits (5% per position, 25% sector, $5 min price)
2. Portfolio limits (10% max drawdown, 3% daily loss, 10% cash reserve)
3. Circuit breakers (VIX >35, stale data, reconciliation, dead man switch)
4. Autonomy modes: PAPER_ONLY → MANUAL_APPROVAL → BOUNDED_AUTONOMOUS → FULL_AUTONOMOUS

## Commands
```bash
# Backend (Docker infra + uvicorn)
./scripts/start-backend.sh           # Start TimescaleDB, Redis, Prometheus, Grafana + FastAPI
./scripts/stop-backend.sh            # Stop FastAPI (leaves Docker infra running)
./scripts/stop-backend.sh --all      # Stop FastAPI + Docker infra
./scripts/restart-backend.sh         # Restart FastAPI only
./scripts/restart-backend.sh --all   # Restart FastAPI + Docker infra

# Frontend (Vite dev server)
./scripts/start-frontend.sh          # Start React dashboard (port 3000)
./scripts/stop-frontend.sh           # Stop React dashboard
./scripts/restart-frontend.sh        # Restart React dashboard

# Database
./scripts/clear_database.sh          # Remove seed/demo data from Redis (prepare for real data)
cd web && npm run build              # Production build

# Tests
python -m pytest tests/ -v           # Run all tests (421 tests)
python -m pytest tests/unit/test_pdt_guard.py -v  # PDT guard tests only
```

Logs are written to `logs/backend.log` and `logs/frontend.log`. PID files live in `.pids/`.

## Development Notes
- Strategies use `src/strategy/builtin/_indicators.py` shim (falls back from pandas_ta to ta library)
- All strategies enforce `min_hold_days >= 2` (MLSignalStrategy uses `min_hold_days=3`) for PDT compliance
- Feature store in `src/signals/feature_store.py` orchestrates all calculators with point-in-time joins and Parquet persistence
- Model registry in `src/signals/ml/registry.py` handles register/promote/rollback; scheduler in `src/scheduling/` runs 4 APScheduler cron jobs
- Smart order router in `src/execution/router.py` selects market/limit/TWAP based on ADV, spread, urgency
- WebSocket at `/ws` broadcasts Redis pub/sub events to dashboard
- Kill switch requires typed confirmation ("KILL" or "RESUME")
- API proxied from Vite dev server: `/api/*` → localhost:8000

## Phase Status
- **Phase 1 (MVP):** Implemented — data, strategies, execution, risk, API, dashboard
- **Phase 2 (ML):** Implemented — feature store, XGBoost pipeline, walk-forward validation, signal generation, model monitoring, smart execution, ML dashboard
- **Phase 3 (LLM):** Not started — Claude analyst agent, FinBERT, full automation
