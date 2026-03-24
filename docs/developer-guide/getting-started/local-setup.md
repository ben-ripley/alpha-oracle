---
title: Local Dev Setup
nav_order: 1
parent: Getting Started
---

# Local Development Setup

This guide walks through cloning the repository, installing dependencies, configuring the environment, and starting the backend and frontend services.

## 1. Clone the Repository

```bash
git clone https://github.com/yourusername/alpha-oracle.git
cd alpha-oracle
```

## 2. Create Python Virtual Environment

Create and activate a virtual environment to isolate dependencies:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows (WSL2): source venv/bin/activate
```

Your prompt should now show `(venv)`.

## 3. Install Python Dependencies

Install the project and its dependencies:

```bash
pip install --upgrade pip
pip install -e .
```

This installs:
- Core dependencies (FastAPI, SQLAlchemy, Redis, etc.)
- Data adapters (Alpha Vantage, ib-async)
- ML libraries (XGBoost, scikit-learn)
- Testing tools (pytest)

**Optional**: Install advanced dependencies for [VectorBT](../glossary.md#vectorbt) backtesting and pandas_ta indicators:

```bash
pip install -e ".[backtest-advanced]"
```

## 4. Install Frontend Dependencies

Navigate to the `web/` directory and install Node.js packages:

```bash
cd web
npm install
cd ..
```

This installs React 18, TypeScript, TailwindCSS, Vite, and chart libraries.

## 5. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env  # If .env.example exists
```

Edit `.env` and add your API keys:

```bash
# Required: Alpha Vantage API key for market data
SA_ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key

# Optional: Use simulated broker for local dev (no IBKR needed)
SA_BROKER__PROVIDER=simulated

# Optional: Override database URL (docker-compose defaults work)
# SA_DATABASE__URL=postgresql+asyncpg://trader:dev_password@localhost:5432/stock_analysis

# Optional: Override Redis URL
# SA_REDIS__URL=redis://localhost:6379/0
```

> **Tip**: For local development, use `SA_BROKER__PROVIDER=simulated` to avoid needing IB Gateway. The simulated broker provides realistic order execution with in-memory state.

## 6. Start Infrastructure Services

Start [TimescaleDB](../glossary.md#timescaledb), [Redis](../glossary.md#redis), [Prometheus](../glossary.md#prometheus), and [Grafana](../glossary.md#grafana) using Docker Compose:

```bash
docker compose up -d timescaledb redis prometheus grafana
```

**Wait for health checks** (the `start-backend.sh` script does this automatically, but you can check manually):

```bash
docker compose ps
```

All services should show `healthy` status. If not, wait 30 seconds and check again.

**Service ports:**
- TimescaleDB: `localhost:5432`
- Redis: `localhost:6379`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3001` (admin/admin)

## 7. Start the Backend (FastAPI)

Run the backend API server (uvicorn):

```bash
./scripts/start-backend.sh
```

This script:
1. Starts Docker infrastructure if not already running
2. Waits for TimescaleDB and Redis to be healthy
3. Starts the FastAPI dev server on port 8000
4. Writes PID to `.pids/backend.pid` and logs to `logs/backend.log`

**Verify the backend is running:**

```bash
curl http://localhost:8000/api/system/health
```

Expected response:

```json
{
  "status": "healthy",
  "timestamp": "2026-03-12T10:30:00Z",
  "version": "0.1.0",
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "broker": "healthy"
  }
}
```

**View logs:**

```bash
tail -f logs/backend.log
```

## 8. Start the Frontend (React Dashboard)

In a new terminal, start the Vite dev server:

```bash
./scripts/start-frontend.sh
```

This script:
1. Starts the Vite dev server on port 3000
2. Writes PID to `.pids/frontend.pid` and logs to `logs/frontend.log`
3. Proxies `/api/*` requests to the backend (localhost:8000)

**Access the dashboard:**

Open [http://localhost:3000](http://localhost:3000) in your browser.

**View logs:**

```bash
tail -f logs/frontend.log
```

## 9. Verify the Setup

### Test the API

```bash
# System health
curl http://localhost:8000/api/system/health

# Portfolio snapshot
curl http://localhost:8000/api/portfolio/snapshot

# Strategy list
curl http://localhost:8000/api/strategies/list
```

### Test the Dashboard

Navigate to [http://localhost:3000](http://localhost:3000) and verify:

- **Portfolio page**: Shows account balance, positions, and equity curve
- **Strategies page**: Lists active strategies and performance metrics
- **Risk page**: Displays risk limits, [PDT guard](../glossary.md#pdt) status, and circuit breakers
- **Trades page**: Shows order history and execution quality

### Test WebSocket Connection

The dashboard uses a WebSocket at `ws://localhost:8000/ws` for real-time updates. Check the browser console for:

```
WebSocket connected
```

If you see reconnection attempts, verify the backend is running.

## 10. Stop Services

### Stop the Backend

```bash
./scripts/stop-backend.sh
```

This stops the FastAPI server but leaves Docker infrastructure running.

**Stop Docker infrastructure too:**

```bash
./scripts/stop-backend.sh --all
```

### Stop the Frontend

```bash
./scripts/stop-frontend.sh
```

### Stop Docker Services Manually

```bash
docker compose down
```

## 11. Restart Services

### Restart Backend

```bash
./scripts/restart-backend.sh          # Restart FastAPI only
./scripts/restart-backend.sh --all    # Restart FastAPI + Docker infra
```

### Restart Frontend

```bash
./scripts/restart-frontend.sh
```

## 12. Optional: Backfill Historical Data

To populate [TimescaleDB](../glossary.md#timescaledb) with historical [OHLCV](../glossary.md#ohlcv) data for the S&P 500 universe:

```bash
python scripts/backfill_history.py --years 2 --symbols sp500
```

**Warning**: This takes ~1.5-2 hours on a free Alpha Vantage tier (5 calls/minute). For faster testing, backfill a small set:

```bash
python scripts/backfill_history.py --years 2 --symbols AAPL,MSFT,GOOG
```

**Resume interrupted backfills:**

```bash
python scripts/backfill_history.py --resume
```

The script uses idempotency keys in Redis (`backfill:completed`) to avoid re-fetching data.

## Troubleshooting

### Backend Won't Start

**Symptom**: `./scripts/start-backend.sh` fails or API returns errors.

**Solutions**:
1. Check Docker services are healthy: `docker compose ps`
2. View backend logs: `tail -f logs/backend.log`
3. Verify `.env` has `SA_ALPHA_VANTAGE_API_KEY`
4. Check TimescaleDB connection: `docker compose logs timescaledb`

### Frontend Won't Start

**Symptom**: Vite dev server fails to start or shows port conflict.

**Solutions**:
1. Check if port 3000 is in use: `lsof -i :3000`
2. Kill existing process: `kill -9 <PID>`
3. View frontend logs: `tail -f logs/frontend.log`
4. Re-run `npm install` in `web/` directory

### Docker Services Not Healthy

**Symptom**: `docker compose ps` shows services as unhealthy or restarting.

**Solutions**:
1. Check service logs: `docker compose logs <service_name>`
2. Restart services: `docker compose restart`
3. Remove volumes and recreate: `docker compose down -v && docker compose up -d`

### IBKR Connection Fails

**Symptom**: Backend logs show "IBKR connection timeout" or "port refused".

**Solutions**:
1. Verify IB Gateway or TWS is running
2. Check port in `.env`: `SA_BROKER__IBKR__PORT=4002` (paper) or `4001` (live)
3. Ensure client ID is unique: `SA_BROKER__IBKR__CLIENT_ID=1` (data adapter uses `client_id+1`, feed uses `client_id+2`)
4. For local dev, use simulated broker: `SA_BROKER__PROVIDER=simulated`

## Next Steps

- [Running Tests](running-tests.md) — Verify the installation with the test suite
- [Architecture Overview](../architecture/overview.md) — Understand the system design
- [Module Map](../architecture/module-map.md) — Explore the codebase structure
