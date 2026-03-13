# IBKR Gateway Setup

The system connects to Interactive Brokers via IB Gateway (or Trader Workstation) for order execution, market data, and portfolio management. See [ADR-010](../../specs/adrs/010-ibkr-broker-switch.md) for the full rationale behind the IBKR switch.

## IB Gateway vs TWS

**IB Gateway** is recommended over TWS for automated trading:
- Lighter resource footprint (no GUI)
- Faster startup
- Same API surface
- Less prone to UI-related issues

**Ports:**

| Mode | Software | Port |
|------|----------|------|
| Paper trading | IB Gateway | **4002** (recommended) |
| Live trading | IB Gateway | **4001** |
| Paper trading | TWS | 7497 |
| Live trading | TWS | 7496 |

**Download:**
- IB Gateway: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
- TWS: https://www.interactivebrokers.com/en/trading/tws.php

---

## Client ID Scheme

IBKR connections require unique client IDs. The system uses three separate connections with sequential IDs:

| Component | Client ID | Purpose | File |
|-----------|-----------|---------|------|
| Broker Adapter | `client_id` (default: **1**) | Order submission, positions, portfolio | `src/execution/broker_adapters/ibkr_adapter.py` |
| Data Adapter | `client_id + 1` (default: **2**) | Historical bar fetching | `src/data/adapters/ibkr_data_adapter.py` |
| Market Feed | `client_id + 2` (default: **3**) | Real-time quote streaming | `src/data/feeds/ibkr_feed.py` |

**Critical:** Never reuse client IDs across simultaneous connections. IBKR will reject the second connection with "already connected" error.

**Configuration:**
```yaml
# config/settings.yaml
broker:
  ibkr:
    client_id: 1  # Base ID; data adapter uses 2, feed uses 3
```

---

## Configuration

Settings are defined in `config/settings.yaml` and overridden via environment variables:

```yaml
broker:
  provider: "ibkr"              # or "simulated" for testing
  paper_trading: true           # true = paper (port 4002), false = live (port 4001)

  ibkr:
    host: "127.0.0.1"           # IB Gateway host
    port: 4002                  # 4002 (paper) or 4001 (live)
    client_id: 1                # Base client ID
    account_id: ""              # Optional; blank = first account
```

**Environment variable overrides:**
```bash
SA_BROKER__PROVIDER=ibkr
SA_BROKER__PAPER_TRADING=true
SA_BROKER__IBKR__PORT=4002
SA_BROKER__IBKR__CLIENT_ID=1
SA_BROKER__IBKR__ACCOUNT_ID=DU123456  # optional
```

---

## Paper vs Live Trading

**Paper trading mode:**
- Connects to IB Gateway paper port (4002)
- Uses paper account (prefix `DU` for individuals)
- Identical API behavior to live
- Delayed market data (15 minutes) unless you have a subscription
- **Recommended for development and strategy validation**

**Live trading mode:**
- Connects to IB Gateway live port (4001)
- Uses real account with real money
- Requires funded account
- Market data subscription recommended (~$10/mo for US equities)
- **Only enable after 30+ days of successful paper trading**

**Toggle:**
```bash
# Paper trading
SA_BROKER__PAPER_TRADING=true
SA_BROKER__IBKR__PORT=4002

# Live trading
SA_BROKER__PAPER_TRADING=false
SA_BROKER__IBKR__PORT=4001
```

The same codebase runs in both modes with zero changes.

---

## Connection Management

### Startup

IB Gateway or TWS must be running **before** starting the system. The FastAPI lifespan handler attempts to connect on startup:

1. IBKRBrokerAdapter connects (client ID 1)
2. IBKRDataAdapter connects (client ID 2)
3. IBKRMarketFeed connects (client ID 3) and subscribes to S&P 500 symbols

If IB Gateway is not reachable, the system enters **degraded mode**:
- API starts successfully
- Broker adapter health check fails
- WebSocket broadcasts `broker: disconnected` status
- Dashboard shows connectivity warning
- Orders will be rejected until connection is restored

**Log visibility:**
```python
logger.error(
    "ibkr_gateway.not_connected",
    msg="IB Gateway / TWS is not reachable — system is running in degraded mode",
)
```

### Reconnection

**Broker adapter** (`IBKRBrokerAdapter`):
- `_ensure_connected()` called before every operation
- Retries up to 3 times with exponential backoff (2s, 4s, 8s)
- Raises `ConnectionError` after exhausting retries

**Market feed** (`IBKRMarketFeed`):
- Registers `ib.disconnectedEvent` handler
- On disconnect: publishes `system:feed:disconnected` to Redis
- Runs `_reconnect_loop()` with 5-second retry interval
- Re-subscribes to all symbols after reconnection
- Publishes `system:feed:reconnected` to Redis

**Known disconnect triggers:**
- Market close (4pm ET) — IBKR automatically closes connections
- IB Gateway restart
- Network interruption

### Health Check

The broker adapter exposes a `health_check()` method:

```python
from src.api.dependencies import get_broker

broker = await get_broker()
is_healthy = await broker.health_check()
```

Health check is performed:
- On API startup (via lifespan handler)
- On demand via `GET /api/system/health`

**Implementation:**
```python
async def health_check(self) -> bool:
    try:
        await self._ensure_connected()
        return self._ib.isConnected()
    except Exception:
        return False
```

---

## Market Data Subscriptions

IBKR requires a market data subscription for real-time quotes. Without a subscription:
- Quotes are delayed by 15 minutes
- Historical data is still available
- Order execution works normally

**For paper trading:** Delayed data is sufficient for strategy development.

**For live trading:** Real-time data subscription recommended (~$10/mo for US Equity/ETF bundle).

**Subscribe:**
1. Log in to IBKR Account Management
2. Navigate to Settings > Account Settings > Market Data Subscriptions
3. Subscribe to "US Equity and Options Add-On Streaming Bundle"

---

## ib-async Library

The system uses the `ib-async` library (formerly `ib_insync`) as a Pythonic async wrapper around the IBKR TWS API.

**Installation:**
```bash
pip install ib-async
```

**Lazy imports:** The `ib_async` library is imported lazily inside adapter methods to make it an optional dependency. If IB Gateway is not available or you're using the simulated broker, the import never occurs.

**Example:**
```python
from ib_async import IB, Stock  # Inside __init__ or method, not at module level
```

---

## Troubleshooting

### "Connection refused" on port 4002/4001
- IB Gateway / TWS is not running
- Start IB Gateway and wait for "Ready" status
- Check port configuration matches paper vs live mode

### "Client ID already in use"
- Another connection is using the same client ID
- Check for orphaned processes: `ps aux | grep python`
- Ensure broker adapter (1), data adapter (2), and feed (3) use distinct IDs
- Restart IB Gateway to clear stuck connections

### "No security definition found" for a symbol
- Symbol not recognized by IBKR
- Check ticker spelling (IBKR uses primary exchange symbols)
- Verify symbol is a US equity on NYSE/NASDAQ

### Delayed market data in paper trading
- Expected behavior without real-time subscription
- Paper trading accounts default to delayed quotes
- Subscribe to market data in Account Management if needed

### Connection drops at 4pm ET
- Normal — IBKR closes connections at market close
- System will auto-reconnect when market reopens
- Use `_reconnect_loop()` to handle gracefully

### Health check fails on startup
- IB Gateway not running or not ready
- Port mismatch (paper=4002, live=4001)
- Firewall blocking localhost connection
- Check FastAPI logs: `logs/backend.log`

---

## Simulated Broker Fallback

When `SA_BROKER__PROVIDER != "ibkr"`, the system uses `SimulatedBroker` or `PaperStubBroker` (in-memory brokers with demo data). This allows development and testing without IB Gateway.

**Enable simulated broker:**
```bash
SA_BROKER__PROVIDER=simulated
```

**Use cases:**
- Frontend development without IB Gateway
- CI/CD testing
- Demonstrating the system without broker connectivity

---

<!-- DIAGRAM: IBKR Gateway connection architecture showing three client IDs and reconnection flow -->
