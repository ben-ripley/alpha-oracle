# Stock Analysis — AI-Driven Automated Trading System

An automated stock trading system for retail investors managing US equities through a personal brokerage account. The system ingests market data, applies rule-based and ML-driven signal generation, backtests and ranks strategies, executes trades, and manages risk with configurable autonomy levels.

## Key Features

- **Data Ingestion** — IBKR (real-time WebSocket via IB Gateway), Alpha Vantage (historical OHLCV + fundamentals), SEC EDGAR (filings), FINRA short interest
- **Universe Management** — S&P 500 constituent tracking with Wikipedia scrape, Redis cache, and CSV fallback
- **Feature Engineering** — 50+ point-in-time features: technical (RSI, MACD, BB, ATR, OBV), fundamental (sector percentiles, quality score), cross-asset (SPY beta, VIX regime), alternative (insider signals, short interest z-score)
- **ML Pipeline** — XGBoost with walk-forward validation, Optuna hyperparameter tuning, isotonic/Platt confidence calibration
- **Strategy Engine** — Backtrader + VectorBT backtesting, walk-forward validation, composite ranking; `MLSignalStrategy` (min 3-day hold)
- **Built-in Strategies** — SwingMomentum (MA crossover), MeanReversion (Bollinger+RSI), ValueFactor (PE/PB/EV ranking)
- **Execution Engine** — Half-Kelly position sizing, Smart Order Router (market/limit/TWAP), execution quality tracking (slippage, latency); three broker backends: `IBKRBrokerAdapter` (live/paper), `SimulatedBroker` (in-memory fills, no IB Gateway needed), `PaperStubBroker` (demo data)
- **Model Monitoring** — PSI feature drift detection, rolling accuracy tracking, degraded-window fallback, Prometheus gauges
- **Scheduler** — APScheduler cron jobs for daily bars, weekly fundamentals, biweekly alternative data, weekly model retrain
- **Risk Management** — 4-layer defense: position limits, portfolio limits, circuit breakers, autonomy modes
- **PDT Guard** — Bulletproof Pattern Day Trader rule enforcement (max 3 day trades per 5 business days)
- **Web Dashboard** — React/TypeScript terminal-style UI with real-time WebSocket updates, ML signal feed, feature importance, drift heatmap, model version history
- **Monitoring** — Prometheus metrics, Grafana dashboards, Slack/Telegram alerts
- **Kill Switch** — Emergency halt via dashboard, API, or Telegram with typed confirmation

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                 Docker Compose Stack                │
│                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐ │
│  │   Data   │  │ Strategy │  │Execution │  │ Risk │ │
│  │ Ingestion│──│  Engine  │──│  Engine  │──│ Mgr  │ │
│  │  Module  │  │  Module  │  │  Module  │  │Module│ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──┬───┘ │
│       └─────────────┴─────────────┴───────────┘     │
│             Redis (Event Bus + Cache)               │
│                          │                          │
│  ┌────────────┐  ┌───────┴─────┐  ┌──────────────┐  │
│  │TimescaleDB │  │   DuckDB    │  │ Prometheus + │  │
│  │(time-series)│ │ (analytics) │  │   Grafana    │  │
│  └────────────┘  └─────────────┘  └──────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │          FastAPI + React Dashboard           │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

Modular monolith with Redis pub/sub for event-driven communication. Clean interfaces enforced by abstract base classes. See [Architecture ADR](specs/adrs/007-architecture.md).

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+
- [Alpha Vantage](https://www.alphavantage.co/) API key (free tier — for historical data and fundamentals)
- **For live/paper trading:** Interactive Brokers account + [IB Gateway](https://www.interactivebrokers.com/en/trading/ibgateway.php) running locally
- **Without IB Gateway:** set `SA_BROKER__PROVIDER=simulated` to use the in-memory SimulatedBroker

### Setup

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your API keys

# Start infrastructure
docker-compose up -d

# Install Python dependencies
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install frontend dependencies
cd web
npm install
cd ..
```

### Run

```bash
# Start the API server (Docker infra + uvicorn)
./scripts/start-backend.sh

# In another terminal, start the dashboard
./scripts/start-frontend.sh

# Open http://localhost:3000
```

### Test

```bash
python -m pytest tests/ -v
```

## Scripts

All lifecycle scripts live in `scripts/`. They manage background processes via PID files in
`.pids/` and write output to `logs/backend.log` / `logs/frontend.log`.

| Script | Description |
|--------|-------------|
| `./scripts/start-backend.sh` | Start Docker infra (TimescaleDB, Redis, Prometheus, Grafana) + FastAPI on :8000 |
| `./scripts/stop-backend.sh` | Stop FastAPI only |
| `./scripts/stop-backend.sh --all` | Stop FastAPI + Docker infra |
| `./scripts/restart-backend.sh` | Restart FastAPI |
| `./scripts/restart-backend.sh --all` | Restart FastAPI + Docker infra |
| `./scripts/start-frontend.sh` | Start Vite dev server on :3000 |
| `./scripts/stop-frontend.sh` | Stop Vite dev server |
| `./scripts/restart-frontend.sh` | Restart Vite dev server |
| `./scripts/clear_database.sh` | Delete all seed/demo keys from Redis, ready for real data |
| `python scripts/backfill_history.py` | Backfill 2 years of OHLCV for S&P 500 (resumable; tracks progress in Redis) |

## Dashboard

The web dashboard provides a real-time view of your trading system:

| Page | Description |
|---|---|
| **Portfolio** | Positions, P&L, allocation chart, equity curve |
| **Strategies** | Strategy rankings, backtest results, equity curves, ML signal feed, feature importance, model performance |
| **Risk** | PDT counter (X/3), drawdown chart, limit utilization, circuit breakers |
| **Trades** | Trade history, pending approvals, execution quality |
| **Model Health** | Rolling accuracy chart, feature drift heatmap (PSI), model version history |

Dark terminal aesthetic with JetBrains Mono typography, real-time WebSocket updates, and a kill switch with typed confirmation.

## Risk Management

Four independent layers, any of which can halt trading:

| Layer | Controls |
|---|---|
| **Position Limits** | Max 5% per position, 25% per sector, no penny stocks (<$5), 2% stop-loss |
| **Portfolio Limits** | Max 10% drawdown, 3% daily loss, 20 max positions, 10% cash reserve |
| **Circuit Breakers** | VIX >35, stale data (>5min), reconciliation drift, dead man switch (48hr) |
| **Autonomy Modes** | PAPER_ONLY → MANUAL_APPROVAL → BOUNDED_AUTONOMOUS → FULL_AUTONOMOUS |

The **PDT Guard** is hard-enforced and cannot be overridden while the account is under $25K. All strategies enforce minimum 2-day holds to avoid day trading.

## Autonomy Modes

| Mode | Behavior | Transition Requirement |
|---|---|---|
| `PAPER_ONLY` | All trades simulated | Default starting mode |
| `MANUAL_APPROVAL` | Every trade needs human approval | 30 days paper + Sharpe > 1.0 |
| `BOUNDED_AUTONOMOUS` | Auto-trades within limits; large trades need approval | 30 days manual + positive returns |
| `FULL_AUTONOMOUS` | Fully automated within risk layers 1-3 | 60 days bounded + profitable |

Mode transitions require explicit operator action and cannot be changed programmatically.

## Project Structure

```
stock-analysis/
├── docker-compose.yml          # TimescaleDB, Redis, Prometheus, Grafana
├── pyproject.toml              # Python dependencies and tool config
├── config/
│   ├── settings.yaml           # Application settings
│   ├── risk_limits.yaml        # Risk management configuration
│   └── prometheus.yml          # Prometheus scrape config
├── src/
│   ├── core/                   # Models, interfaces, config, database, redis
│   ├── data/                   # Ingestion pipeline, adapters, feeds, parsers, universe
│   ├── strategy/               # Engine, backtesting, built-in strategies, ranker
│   ├── signals/                # Feature store, ML pipeline, signal generation, model monitoring
│   ├── scheduling/             # APScheduler cron jobs and model registry
│   ├── execution/              # Order generation, smart router, broker adapter, quality tracking
│   ├── risk/                   # PDT guard, pre-trade checks, circuit breakers
│   ├── api/                    # FastAPI REST + WebSocket endpoints
│   └── monitoring/             # Prometheus metrics, alert manager
├── web/                        # React + TypeScript + TailwindCSS dashboard
├── tests/unit/                 # 669 unit tests
├── specs/
│   ├── adrs/                   # Architecture Decision Records (001-010)
│   ├── feature-specs.md        # Feature specifications (F-001 to F-008)
│   └── roadmap.md              # Implementation roadmap and cost analysis
└── scripts/
    ├── start-backend.sh        # Start Docker infra + uvicorn API
    ├── stop-backend.sh         # Stop API (--all also stops Docker infra)
    ├── restart-backend.sh      # Restart API
    ├── start-frontend.sh       # Start Vite dev server
    ├── stop-frontend.sh        # Stop Vite dev server
    ├── restart-frontend.sh     # Restart Vite dev server
    ├── clear_database.sh       # Remove seed/demo data from Redis
    ├── seed_demo_data.py       # Populate Redis with demo data for UI testing
    ├── backfill_history.py     # One-time historical OHLCV backfill (resumable)
    └── init_db.sql             # TimescaleDB schema (10 hypertables)
```

## Roadmap

| Phase | Focus | Status |
|---|---|---|
| **Phase 1** | Data + Backtesting + Paper Trading + Dashboard | Implemented |
| **Phase 2** | ML Signals (XGBoost) + Feature Engineering + Smart Execution | Implemented |
| **Phase 3** | LLM Agent (Claude) + Full Automation | Not started |

See [specs/roadmap.md](specs/roadmap.md) for detailed weekly plan and cost analysis.

## Cost

| Phase | Monthly Cost |
|---|---|
| Phase 1 | $0–25 (all free data sources) |
| Phase 2 | $30–100 (VPS + Claude API + optional data) |
| Phase 3 | $75–250 (heavier Claude + paid data + options flow) |

## Documentation

- [Architecture Decision Records](specs/adrs/) — 10 ADRs covering broker, data, ML, backtesting, stack, architecture, LLM, risk, and IBKR migration
- [Feature Specifications](specs/feature-specs.md) — F-001 through F-008
- [Implementation Roadmap](specs/roadmap.md) — Phased plan with exit criteria

## Disclaimer

This software is for educational and research purposes. Automated trading involves substantial risk of loss. Past performance (including backtests) does not guarantee future results. The author is not responsible for any financial losses incurred through use of this system. Always start with paper trading and never risk money you cannot afford to lose.
