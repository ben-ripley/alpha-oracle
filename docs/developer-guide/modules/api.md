---
title: API Layer Module
nav_order: 8
parent: Modules
---

# API Layer Module

The `src/api/` module implements the FastAPI REST API and WebSocket endpoint for the alpha-oracle system. Provides routes for portfolio, strategies, risk, trades, and system management, plus real-time WebSocket broadcasting via [Redis](../glossary.md#redis) pub/sub.

## Purpose

The API provides:

- **FastAPI app** with CORS middleware, dependency injection, and lifespan hooks
- **REST endpoints** for portfolio, strategies, risk, trades, and system operations
- **WebSocket endpoint** (`/ws`) broadcasting Redis pub/sub events to dashboard
- **Health checks** for broker connectivity, feed status, and database
- **Manual scheduler triggers** for on-demand job execution
- **Kill switch control** with typed confirmation

## Key Components

### App Factory

#### `create_app` (src/api/main.py)

FastAPI application factory with lifespan management.

**Lifespan Hooks:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting alpha-oracle API")

    # 1. Start market data feed (IBKR or fallback)
    if settings.broker.provider == "ibkr":
        feed = IBKRMarketFeed(settings)
        await feed.start()
        symbols = await SymbolUniverse().get_symbols()
        await feed.subscribe(symbols)
        app.state.market_feed = feed
        logger.info("feed.subscribed_universe", count=len(symbols))
    else:
        app.state.market_feed = None

    # 2. Validate IBKR broker connectivity
    broker = await get_broker()
    app.state.ibkr_gateway_connected = await broker.health_check()
    if not app.state.ibkr_gateway_connected:
        logger.error("ibkr_gateway.not_connected", msg="System running in degraded mode")

    # 3. Publish connectivity status to Redis
    redis = await get_redis()
    await redis.set("system:status", json.dumps({
        "broker": "connected" if app.state.ibkr_gateway_connected else "disconnected",
        "feed": "connected" if app.state.market_feed else "disconnected"
    }))

    # 4. Start scheduler
    scheduler = TradingScheduler()
    scheduler.setup()
    scheduler.start()
    app.state.scheduler = scheduler

    yield  # Application runs

    # Shutdown: stop scheduler, feed, close Redis
    if app.state.scheduler:
        app.state.scheduler.stop()
    if app.state.market_feed:
        await app.state.market_feed.stop()
    await close_redis()
```

**CORS Middleware:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Route Registration:**
```python
app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(websocket.router, prefix="", tags=["websocket"])
```

### Route Groups

#### 1. Portfolio Routes (`src/api/routes/portfolio.py`)

**Endpoints:**

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/portfolio` | GET | Current portfolio snapshot | `PortfolioSnapshot` |
| `/api/portfolio/positions` | GET | Open positions | `list[Position]` |
| `/api/portfolio/history` | GET | Portfolio snapshots over time (query params: `start`, `end`) | `list[PortfolioSnapshot]` |
| `/api/portfolio/sector_exposure` | GET | Sector allocation breakdown | `dict[str, float]` |

**Example:**
```bash
curl http://localhost:8000/api/portfolio

{
  "timestamp": "2024-03-15T14:30:00Z",
  "total_equity": 105432.50,
  "cash": 52716.25,
  "positions_value": 52716.25,
  "daily_pnl": 543.20,
  "daily_pnl_pct": 0.52,
  "max_drawdown_pct": 3.2,
  "positions": [
    {"symbol": "AAPL", "quantity": 100, "unrealized_pnl": 320.00, ...},
    ...
  ],
  "sector_exposure": {"Technology": 35.0, "Healthcare": 20.0, ...}
}
```

#### 2. Strategies Routes (`src/api/routes/strategies.py`)

**Endpoints:**

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/strategies` | GET | List registered strategies | `list[dict]` (name, description, params) |
| `/api/strategies/{name}` | GET | Strategy details | `dict` (name, description, min_hold_days, params, required_data) |
| `/api/strategies/{name}/signals` | GET | Recent signals (query: `limit`, `start`, `end`) | `list[Signal]` |
| `/api/strategies/{name}/backtest` | POST | Run backtest (body: `start`, `end`, `initial_capital`) | `BacktestResult` |
| `/api/strategies/rankings` | GET | Strategy rankings by composite score | `list[StrategyRanking]` |

**Example:**
```bash
curl http://localhost:8000/api/strategies

[
  {"name": "SwingMomentum", "description": "RSI + SMA momentum strategy", "min_hold_days": 3},
  {"name": "MLSignalStrategy", "description": "XGBoost 3-class predictions", "min_hold_days": 3},
  ...
]

curl -X POST http://localhost:8000/api/strategies/SwingMomentum/backtest \
  -H "Content-Type: application/json" \
  -d '{"start": "2023-01-01", "end": "2024-01-01", "initial_capital": 100000}'

{
  "strategy_name": "SwingMomentum",
  "total_return_pct": 15.3,
  "sharpe_ratio": 1.42,
  "max_drawdown_pct": 8.7,
  "total_trades": 142,
  "win_rate": 0.58,
  ...
}
```

#### 3. Risk Routes (`src/api/routes/risk.py`)

**Endpoints:**

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/risk/limits` | GET | Current risk limits | `dict` (position_limits, portfolio_limits, pdt_guard, circuit_breakers) |
| `/api/risk/pdt-status` | GET | [PDT](../glossary.md#pdt) guard status | `dict` (day_trades_used, max_day_trades, account_threshold) |
| `/api/risk/circuit-breakers` | GET | Circuit breaker states | `list[dict]` (name, tripped, reason) |
| `/api/risk/kill-switch` | GET | Kill switch status | `dict` (active, reason, activated_at) |
| `/api/risk/kill-switch` | POST | Activate/deactivate kill switch (body: `action=activate/deactivate`, `confirmation`) | `dict` (status, message) |

**Kill Switch Activation:**
```bash
curl -X POST http://localhost:8000/api/risk/kill-switch \
  -H "Content-Type: application/json" \
  -d '{"action": "activate", "confirmation": "KILL", "reason": "Manual stop: market crash"}'

{
  "status": "activated",
  "message": "Kill switch activated. All trading halted."
}
```

**Deactivation (requires cooldown expired):**
```bash
curl -X POST http://localhost:8000/api/risk/kill-switch \
  -H "Content-Type: application/json" \
  -d '{"action": "deactivate", "confirmation": "RESUME"}'
```

#### 4. Trades Routes (`src/api/routes/trades.py`)

**Endpoints:**

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/trades/orders` | GET | Order history (query: `start`, `end`, `status`, `symbol`) | `list[Order]` |
| `/api/trades/orders/{order_id}` | GET | Order details | `Order` |
| `/api/trades/trades` | GET | Closed trade records (query: `start`, `end`) | `list[TradeRecord]` |
| `/api/trades/execution-quality` | GET | Execution metrics (query: `start`, `end`) | `list[ExecutionQualityMetrics]` |

**Example:**
```bash
curl "http://localhost:8000/api/trades/orders?status=FILLED&limit=10"

[
  {
    "id": "abc123",
    "symbol": "AAPL",
    "side": "BUY",
    "order_type": "LIMIT",
    "quantity": 100,
    "limit_price": 150.00,
    "status": "FILLED",
    "filled_price": 149.95,
    "filled_at": "2024-03-15T10:32:15Z",
    ...
  },
  ...
]
```

#### 5. System Routes (`src/api/routes/system.py`)

**Endpoints:**

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/system/health` | GET | Health check | `dict` (broker, feed, database, redis) |
| `/api/system/status` | GET | System connectivity status | `dict` (broker, feed, ibkr_gateway_connected) |
| `/api/system/scheduler/jobs` | GET | List scheduled jobs | `list[dict]` (id, next_run_time) |
| `/api/system/scheduler/trigger/{job_name}` | POST | Manually trigger job | `dict` (status, job) |

**Health Check:**
```bash
curl http://localhost:8000/api/system/health

{
  "broker": "connected",
  "feed": "connected",
  "database": "connected",
  "redis": "connected",
  "ibkr_gateway_connected": true
}
```

**Manual Job Trigger:**
```bash
curl -X POST http://localhost:8000/api/system/scheduler/trigger/daily_bars

{
  "status": "triggered",
  "job": "daily_bars"
}
```

### WebSocket Broadcasting

#### WebSocket Endpoint (`src/api/routes/websocket.py`)

Real-time event streaming to dashboard via WebSocket.

**Endpoint:** `ws://localhost:8000/ws`

**Implementation:**
```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    redis = await get_redis()
    pubsub = redis.pubsub()

    # Subscribe to all relevant channels
    await pubsub.subscribe(
        "execution:fills",
        "execution:signals",
        "market:quotes:*",
        "risk:alerts",
        "system:feed:*",
        "ml:drift:*"
    )

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                # Forward Redis pub/sub message to WebSocket client
                await websocket.send_json({
                    "channel": message["channel"],
                    "data": json.loads(message["data"])
                })
    except WebSocketDisconnect:
        logger.info("websocket.client_disconnected")
    finally:
        await pubsub.unsubscribe()
```

**Dashboard Integration:**
```typescript
// web/src/hooks/useWebSocket.ts
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);

  if (msg.channel === "execution:fills") {
    // Update trades table
  } else if (msg.channel.startsWith("market:quotes:")) {
    // Update real-time price
  } else if (msg.channel === "risk:alerts") {
    // Show alert banner
  }
};
```

**Published Channels:**
- `execution:fills` — Order fills (symbol, side, quantity, price, timestamp)
- `execution:signals` — New trading signals from strategies
- `market:quotes:{symbol}` — Real-time bid/ask updates
- `risk:alerts` — Risk threshold breaches (PDT, drawdown, circuit breakers)
- `system:feed:connected` / `system:feed:disconnected` — Feed status changes
- `ml:drift:alerts` — Model drift warnings

### Dependency Injection

#### `dependencies.py` (src/api/dependencies.py)

FastAPI dependencies for broker, data adapter, storage, etc.

**Example:**
```python
async def get_broker() -> BrokerAdapter:
    settings = get_settings()
    provider = settings.broker.provider.lower()

    if provider == "ibkr":
        from src.execution.broker.ibkr_broker import IBKRBrokerAdapter
        return IBKRBrokerAdapter(settings)
    elif provider == "simulated":
        from src.execution.broker.simulated_broker import SimulatedBroker
        return SimulatedBroker()
    else:
        from src.execution.broker.paper_stub import PaperStubBroker
        return PaperStubBroker()

# Usage in route:
@router.get("/portfolio")
async def get_portfolio(broker: BrokerAdapter = Depends(get_broker)):
    portfolio = await broker.get_portfolio()
    return portfolio
```

## Configuration

**Settings (config/settings.yaml):**
```yaml
monitoring:
  prometheus_port: 8001
  health_check_interval_seconds: 60
```

**CORS Origins:**
- Default: `["http://localhost:3000"]` (Vite dev server)
- Production: Add `https://your-domain.com` to allowed origins

## Integration with Other Modules

- **Execution Engine** (`src/execution/`): `/api/trades/orders` endpoint queries broker adapter.
- **Strategy Engine** (`src/strategy/`): `/api/strategies` endpoints list and backtest strategies.
- **Risk Management** (`src/risk/`): `/api/risk` endpoints control kill switch and fetch limits.
- **Scheduler** (`src/scheduling/`): `/api/system/scheduler` endpoints trigger jobs.
- **Dashboard** (`web/`): Frontend consumes REST API + WebSocket for real-time updates.

## Critical Patterns

1. **Lifespan management:** Feed, scheduler, and Redis connections initialized on startup, cleaned up on shutdown.
2. **Dependency injection:** Broker, storage, adapters injected via `Depends()`.
3. **WebSocket multiplexing:** Single `/ws` endpoint broadcasts all Redis channels.
4. **Health checks on startup:** IBKR connectivity validated; degraded state surfaced to dashboard.
5. **Kill switch confirmation:** Requires typed "KILL" or "RESUME" to prevent accidental activation.
6. **CORS for local dev:** Allows requests from Vite dev server (port 3000).

## Glossary Links

- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [PDT](../glossary.md#pdt) — Pattern Day Trader rule
- [Redis](../glossary.md#redis) — In-memory data store
- [WebSocket](../glossary.md#websocket) — Full-duplex communication protocol

<!-- DIAGRAM: API architecture — FastAPI routes → dependencies → modules → database/redis → WebSocket broadcast -->
