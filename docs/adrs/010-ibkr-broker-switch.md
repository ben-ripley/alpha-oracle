# ADR-010: Broker Switch from Alpaca to Interactive Brokers

**Status:** Accepted

**Context:** The operator is a Canadian resident. Alpaca Markets does not offer brokerage services to Canadian residents, making ADR-001's chosen broker unavailable. Interactive Brokers (IBKR) is widely used in Canada, supports US equities trading, and was already identified as the primary upgrade path in ADR-001.

---

## Decision

Replace Alpaca with Interactive Brokers (IBKR) as the sole broker and real-time market data source.

---

## Why IBKR

| Criteria | Decision |
|---|---|
| Canadian availability | IBKR fully supports Canadian residents for US equities |
| Paper trading | IB Gateway paper port (4002) provides identical API surface to live (4001) |
| Commission | $0 on IBKR Lite; tiered pricing on IBKR Pro |
| API | `ib_async` (async Python wrapper around the TWS API); well-maintained |
| Real-time data | WebSocket-style streaming via `reqMktData` / `tickerUpdateEvent` |
| Historical data | `reqHistoricalDataAsync` — daily bars back 20+ years; intraday back ~6 months |
| Order types | Market, Limit, Stop, Stop-Limit, bracket, OCA, TWAP, VWAP, algos |

---

## Implementation

### Connection model

Two separate processes share the IB Gateway connection via distinct client IDs:

| Client ID | Component | File |
|---|---|---|
| `ibkr.client_id` (default 1) | `IBKRBrokerAdapter` — order placement, positions, portfolio | `src/execution/broker_adapters/ibkr_adapter.py` |
| `ibkr.client_id + 1` (default 2) | `IBKRDataAdapter` — historical bar fetching | `src/data/adapters/ibkr_data_adapter.py` |
| `ibkr.client_id + 2` (default 3) | `IBKRMarketFeed` — real-time quote streaming | `src/data/feeds/ibkr_feed.py` |

### Ports

| Mode | Software | Port |
|---|---|---|
| Paper trading | IB Gateway | 4002 (recommended — lighter weight than TWS) |
| Live trading | IB Gateway | 4001 |
| Paper trading | TWS | 7497 |
| Live trading | TWS | 7496 |

Configure via `.env`:
```
SA_BROKER__PROVIDER=ibkr
SA_BROKER__IBKR__PORT=4002
SA_BROKER__IBKR__HOST=127.0.0.1
SA_BROKER__IBKR__CLIENT_ID=1
SA_BROKER__IBKR__ACCOUNT_ID=DU123456   # optional; blank = first account found
```

### Resilience

- **Reconnect logic:** `_ensure_connected()` retries up to `_MAX_RECONNECT_ATTEMPTS` (3) times with exponential backoff (2s, 4s, 8s). IB Gateway closes connections at market close (4pm ET) and on restart.
- **Feed reconnect:** `IBKRMarketFeed` registers an `ib.disconnectedEvent` handler. On disconnect it sets `_connected = False`, publishes `system:feed:disconnected` to Redis, and runs `_reconnect_loop()` which re-subscribes all tickers after reconnection and publishes `system:feed:reconnected`.
- **Pacing limiter:** `IBKRDataAdapter` uses `RateLimiter(6/min)` — conservative against IBKR's limit of ~60 req/10min (error code 162). A pacing error triggers a 30-second backoff before retry.
- **Graceful shutdown:** `IBKRBrokerAdapter.disconnect()` is called during FastAPI lifespan shutdown via `close_broker()` in `src/api/dependencies.py`.

### Market data subscriptions

IBKR requires a market data subscription for real-time quotes. The feed falls back to delayed (15-min) quotes if no live subscription is active. For paper trading, delayed data is sufficient. For live trading, a US Equity/ETF bundle (~$10/mo) is recommended.

### Fundamental data

IBKR does not expose PE, PB, ROE and other fundamental ratios via `ib_async` in the form this system needs. **Alpha Vantage remains the source of truth for all fundamental data** (`weekly_fundamentals_job` in `src/scheduling/jobs.py`).

---

## Consequences

- `PaperStubBroker` (stub broker returning demo data) is retained as fallback when IB Gateway is not reachable, and as a development convenience when `SA_BROKER__PROVIDER != "ibkr"`.
- All Alpaca imports and references removed from `src/data/manager.py`, `src/data/__init__.py`, and `README.md`.
- `IBKRDataAdapter` handles both historical backfill and latest-bar queries; Alpha Vantage handles fundamentals.
- The `BrokerAdapter` ABC in `src/core/interfaces.py` is unchanged — the IBKR adapter is a drop-in replacement.
