# Quick Start Guide

Get the Stock Analysis System running in under 5 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker and Docker Compose
- An Alpha Vantage API key (free tier: [alphavantage.co](https://www.alphavantage.co/support/#api-key))

## Step 1: Clone and Install

```bash
git clone <repository-url> stock-analysis
cd stock-analysis

# Python dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend dependencies
cd web && npm install && cd ..
```

## Step 2: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and add your API key:

```
SA_ALPHA_VANTAGE_API_KEY=your_key_here
```

The system starts in **PAPER_ONLY** mode by default — no real money is at risk.

## Step 3: Start the System

```bash
# Start backend (Docker infra + FastAPI on port 8000)
./scripts/start-backend.sh

# Start frontend (React dashboard on port 3000)
./scripts/start-frontend.sh
```

The backend script automatically starts TimescaleDB, Redis, Prometheus, and Grafana via Docker, waits for health checks, then launches the FastAPI server.

## Step 4: Open the Dashboard

Navigate to **[http://localhost:3000](http://localhost:3000)** in your browser.

You'll see four pages:

| Page | What It Shows |
|------|--------------|
| **Portfolio** | Account equity, positions, P&L, sector allocation |
| **Strategies** | Strategy rankings, ML signals, model health |
| **Risk** | [PDT](glossary.md#pdt) day trade counter, limits, circuit breakers, kill switch |
| **Trades** | Order history, pending approvals, execution quality |

## Step 5: Load Historical Data (Optional)

To populate charts with real historical data:

```bash
# Quick test with 3 symbols (~2 minutes)
python scripts/backfill_history.py --years 2 --symbols AAPL,MSFT,GOOG

# Full S&P 500 universe (~1h 40m on free Alpha Vantage tier)
python scripts/backfill_history.py --years 2 --symbols sp500
```

If interrupted, resume with `--resume`:

```bash
python scripts/backfill_history.py --resume
```

## What's Running

After startup, you have these services:

| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | [localhost:3000](http://localhost:3000) | React frontend |
| API | [localhost:8000](http://localhost:8000) | FastAPI backend |
| Grafana | [localhost:3001](http://localhost:3001) | Monitoring dashboards |
| Prometheus | [localhost:9090](http://localhost:9090) | Metrics collection |

## Stopping the System

```bash
# Stop frontend
./scripts/stop-frontend.sh

# Stop backend (keeps Docker infra running)
./scripts/stop-backend.sh

# Stop everything including Docker containers
./scripts/stop-backend.sh --all
```

## Key Safety Features

The system protects you automatically:

- **[PDT Guard](concepts/pdt-rule.md)** — Prevents FINRA Pattern Day Trader violations (max 3 day trades per 5 business days for accounts under $25K)
- **Risk Limits** — 5% max per position, 25% max per sector, 10% max drawdown, 10% cash reserve
- **Circuit Breakers** — Halts trading on extreme volatility (VIX > 35), stale data, or reconciliation failures
- **[Kill Switch](operations/kill-switch.md)** — Emergency halt button on the Risk page (type "KILL" to activate)

## Next Steps

- **[Getting Started](getting-started.md)** — Detailed orientation and configuration checklist
- **[Dashboard Overview](dashboard/index.md)** — Learn each dashboard page in depth
- **[Autonomy Modes](concepts/autonomy-modes.md)** — Understand PAPER_ONLY vs live trading modes
- **[Risk Management](concepts/risk-management.md)** — How the 4 layers of risk protection work
- **[Glossary](glossary.md)** — Definitions of financial and trading terms
