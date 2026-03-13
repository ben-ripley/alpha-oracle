# Deployment

The system supports three deployment modes: **development**, **paper trading**, and **live trading**. All modes use the same codebase with configuration-driven behavior.

## Development Setup

**Purpose:** Local development with hot-reload and simulated broker

### Start infrastructure

```bash
# Start Docker services (TimescaleDB, Redis, Prometheus, Grafana)
docker compose up -d

# Verify services
docker compose ps
```

### Start backend

```bash
# Option 1: Helper script (recommended)
./scripts/start-backend.sh

# Option 2: Manual uvicorn
cd /path/to/stock-analysis
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Logs:** `logs/backend.log`
**PID file:** `.pids/backend.pid`

### Start frontend

```bash
# Option 1: Helper script (recommended)
./scripts/start-frontend.sh

# Option 2: Manual Vite
cd web
npm install
npm run dev
```

**URL:** http://localhost:3000
**Logs:** `logs/frontend.log`
**PID file:** `.pids/frontend.pid`

### Stop services

```bash
# Stop FastAPI only (keeps Docker running)
./scripts/stop-backend.sh

# Stop FastAPI + Docker infrastructure
./scripts/stop-backend.sh --all

# Stop frontend
./scripts/stop-frontend.sh
```

### Restart services

```bash
# Restart FastAPI only
./scripts/restart-backend.sh

# Restart FastAPI + Docker
./scripts/restart-backend.sh --all

# Restart frontend
./scripts/restart-frontend.sh
```

---

## Paper Trading

**Purpose:** Test strategies with realistic broker simulation before risking capital

### Prerequisites

1. **IBKR account:** Sign up at https://www.interactivebrokers.com
2. **IB Gateway installed:** Download paper trading version
3. **Paper account credentials:** Provided by IBKR (prefix `DU` for individuals)

### Configure paper trading

**Environment variables (`.env` file):**
```bash
SA_BROKER__PROVIDER=ibkr
SA_BROKER__PAPER_TRADING=true
SA_BROKER__IBKR__PORT=4002  # Paper trading port
SA_BROKER__IBKR__HOST=127.0.0.1
SA_BROKER__IBKR__CLIENT_ID=1
SA_BROKER__IBKR__ACCOUNT_ID=DU123456  # Optional
SA_ALPHA_VANTAGE_API_KEY=your_key_here
```

**Or in `config/settings.yaml`:**
```yaml
broker:
  provider: ibkr
  paper_trading: true

  ibkr:
    host: 127.0.0.1
    port: 4002
    client_id: 1
    account_id: ""  # blank = first account

data:
  alpha_vantage:
    api_key: your_key_here
```

### Start IB Gateway

1. Launch IB Gateway (paper trading)
2. Log in with paper account credentials
3. Wait for "Ready" status (green indicator)
4. IB Gateway listens on **port 4002** by default

### Start system

```bash
# 1. Start Docker infrastructure
docker compose up -d

# 2. Backfill historical data (one-time)
python scripts/backfill_history.py --years 2 --symbols sp500

# 3. Start backend
./scripts/start-backend.sh

# 4. Start frontend
./scripts/start-frontend.sh
```

### Verify connectivity

- **Backend logs:** Check for `ibkr_gateway.not_connected` error
- **Dashboard:** Green "Connected" indicator in header
- **API health:** `curl http://localhost:8000/api/system/health`

### Run strategies

1. Navigate to **Strategies** page in dashboard
2. Enable a strategy (e.g., `momentum_crossover`)
3. Monitor signals in **Trades** page
4. Review risk checks in **Risk** page

**Paper trading rules:**
- All PDT rules enforced (max 3 day trades per 5 business days)
- Portfolio limits active (max 10% drawdown, 3% daily loss)
- Circuit breakers enabled (VIX spike, stale data)
- Kill switch available

**Recommended duration:** 30 days minimum before live trading

---

## Live Trading

**Purpose:** Deploy system with real capital

**WARNING:** Only proceed after 30+ days of successful paper trading with positive returns.

### Prerequisites

1. **30+ days paper trading:** Sharpe > 1.0, max drawdown < 10%, consistent profitability
2. **Funded IBKR account:** Transfer capital to live account
3. **Market data subscription:** US Equity/ETF bundle (~$10/mo) for real-time quotes
4. **Risk limits reviewed:** Confirm position/portfolio limits in `config/risk_limits.yaml`
5. **Kill switch tested:** Verify kill switch works in paper mode

### Configure live trading

**Environment variables (`.env` file):**
```bash
SA_BROKER__PROVIDER=ibkr
SA_BROKER__PAPER_TRADING=false  # LIVE TRADING
SA_BROKER__IBKR__PORT=4001      # Live trading port
SA_BROKER__IBKR__ACCOUNT_ID=U123456  # Your live account ID
```

**Or in `config/settings.yaml`:**
```yaml
broker:
  provider: ibkr
  paper_trading: false  # CRITICAL: false = LIVE TRADING

  ibkr:
    port: 4001  # Live trading port
    account_id: U123456  # Live account ID
```

### Risk limits (config/risk_limits.yaml)

```yaml
position_limits:
  max_position_size_pct: 5  # 5% per position
  max_sector_exposure_pct: 25  # 25% per sector
  min_stock_price: 5  # No penny stocks

portfolio_limits:
  max_drawdown_pct: 10  # Halt trading at 10% drawdown
  max_daily_loss_pct: 3  # Halt trading at 3% daily loss
  min_cash_reserve_pct: 10  # Keep 10% in cash
  max_positions: 20  # Max 20 concurrent positions

pdt_guard:
  enabled: true  # NEVER disable
  max_day_trades: 3  # FINRA limit
  rolling_window_days: 5  # Business days
```

**CRITICAL:** Do not weaken PDT guard or circuit breakers without explicit justification.

### Autonomy mode

Start in **PAPER_ONLY** or **MANUAL_APPROVAL** mode:

```yaml
risk:
  autonomy_mode: MANUAL_APPROVAL  # Require approval for every trade
```

**Progression:**
1. `PAPER_ONLY` → Paper trades only, no live execution
2. `MANUAL_APPROVAL` → Every trade requires manual approval via dashboard/Telegram
3. `BOUNDED_AUTONOMOUS` → Auto-execute within strict limits; large/risky trades need approval
4. `FULL_AUTONOMOUS` → Auto-execute all trades within risk limits

**Mode transitions:** Require explicit operator action. Never automated.

### Start IB Gateway (live)

1. Launch IB Gateway (**live trading** version)
2. Log in with **live** account credentials
3. Verify account balance and equity
4. IB Gateway listens on **port 4001** by default

### Start system

```bash
# 1. Double-check environment
echo $SA_BROKER__PAPER_TRADING  # Must be "false"
echo $SA_BROKER__IBKR__PORT     # Must be "4001"

# 2. Start infrastructure
docker compose up -d

# 3. Start backend
./scripts/start-backend.sh

# 4. Start frontend
./scripts/start-frontend.sh
```

### Verify live mode

- **Dashboard:** "LIVE TRADING" banner should be visible (if implemented)
- **Backend logs:** Check for `paper_trading=False` in startup logs
- **IB Gateway:** Verify connection to live account (check account ID in Gateway UI)

### Monitor closely

**First week:**
- Check dashboard multiple times per day
- Monitor all orders in **Trades** page
- Review risk alerts in **Risk** page
- Verify P&L matches IBKR reports

**Ongoing:**
- Daily review of portfolio and P&L
- Weekly review of strategy performance
- Monthly review of risk metrics and autonomy mode

---

## Environment Variables Reference

| Variable | Development | Paper | Live |
|----------|------------|-------|------|
| `SA_BROKER__PROVIDER` | `simulated` | `ibkr` | `ibkr` |
| `SA_BROKER__PAPER_TRADING` | `true` | `true` | `false` |
| `SA_BROKER__IBKR__PORT` | N/A | `4002` | `4001` |
| `SA_BROKER__IBKR__HOST` | N/A | `127.0.0.1` | `127.0.0.1` |
| `SA_BROKER__IBKR__CLIENT_ID` | N/A | `1` | `1` |
| `SA_BROKER__IBKR__ACCOUNT_ID` | N/A | `DU123456` | `U123456` |
| `SA_ALPHA_VANTAGE_API_KEY` | Required | Required | Required |
| `SA_DATABASE__URL` | Auto | Auto | Auto |
| `SA_REDIS__URL` | Auto | Auto | Auto |

**Auto:** Defaults work (uses Docker Compose hostnames)

---

## Script Reference

### Backend Scripts

| Script | Purpose |
|--------|---------|
| `./scripts/start-backend.sh` | Start Docker services + FastAPI |
| `./scripts/stop-backend.sh` | Stop FastAPI only |
| `./scripts/stop-backend.sh --all` | Stop FastAPI + Docker |
| `./scripts/restart-backend.sh` | Restart FastAPI only |
| `./scripts/restart-backend.sh --all` | Restart FastAPI + Docker |

### Frontend Scripts

| Script | Purpose |
|--------|---------|
| `./scripts/start-frontend.sh` | Start Vite dev server |
| `./scripts/stop-frontend.sh` | Stop Vite dev server |
| `./scripts/restart-frontend.sh` | Restart Vite dev server |

### Data Scripts

| Script | Purpose |
|--------|---------|
| `./scripts/backfill_history.py` | One-time historical data backfill |
| `./scripts/clear_database.sh` | Clear demo/seed data from Redis |

---

## PID Management

Process IDs are stored in `.pids/` directory:

- `.pids/backend.pid` — FastAPI process ID
- `.pids/frontend.pid` — Vite dev server process ID

Scripts use these PID files to gracefully stop/restart processes.

---

## Log Files

Logs are written to `logs/` directory:

- `logs/backend.log` — FastAPI application logs
- `logs/frontend.log` — Vite dev server logs

**Rotation:** Not configured by default. Implement log rotation for production:
```bash
# Install logrotate
sudo apt install logrotate

# Configure in /etc/logrotate.d/stock-analysis
/path/to/stock-analysis/logs/*.log {
    daily
    rotate 30
    compress
    missingok
    notifempty
}
```

---

## Production Checklist

Before live trading:

- [ ] 30+ days successful paper trading
- [ ] Sharpe ratio > 1.0
- [ ] Max drawdown < 10%
- [ ] All tests passing: `pytest tests/ -v`
- [ ] Risk limits reviewed and appropriate for account size
- [ ] Kill switch tested and working
- [ ] Monitoring configured (Prometheus + Grafana)
- [ ] Alert channels configured (Slack/Telegram)
- [ ] Backup strategy for IB Gateway failure
- [ ] Emergency contact plan
- [ ] Capital allocation plan (start small)

---

<!-- DIAGRAM: Deployment architecture showing development → paper → live progression with configuration changes -->
