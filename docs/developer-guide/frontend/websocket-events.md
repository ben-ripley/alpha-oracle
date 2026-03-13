# WebSocket Events

The system uses WebSocket for real-time updates from backend to frontend. The WebSocket endpoint subscribes to Redis pub/sub channels and forwards events to connected dashboard clients.

## Endpoint

**URL:** `/ws`
**Protocol:** WebSocket (ws:// for development, wss:// for production)
**Proxy:** Vite dev server proxies `/ws` to `ws://localhost:8000`

---

## Connection Flow

1. Client connects to `/ws`
2. Server accepts connection and adds to `ConnectionManager`
3. Server subscribes to Redis pub/sub channels
4. Client sends `ping` every 30 seconds for keepalive
5. Server broadcasts Redis messages to all connected clients
6. On disconnect, client auto-reconnects after 3 seconds

---

## Client-side (React)

### useWebSocket Hook

The `useWebSocket` hook in `web/src/hooks/useWebSocket.ts` manages the WebSocket connection:

```typescript
import { useWebSocket } from '../hooks/useWebSocket';

function MyComponent() {
  const { lastMessage, connected } = useWebSocket();

  useEffect(() => {
    if (lastMessage?.channel === 'portfolio:update') {
      console.log('Portfolio updated:', lastMessage.data);
    }
  }, [lastMessage]);

  return <div>{connected ? 'Live' : 'Reconnecting...'}</div>;
}
```

**Return values:**
- `lastMessage`: Most recent WebSocket message (type `WSMessage | null`)
- `connected`: Connection status (boolean)

**Behavior:**
- Auto-connects on mount
- Sends `{"type": "ping"}` every 30 seconds
- Ignores `{"type": "pong"}` responses from server
- Auto-reconnects on close/error (3-second delay)
- Cleans up on unmount

---

## Server-side (FastAPI)

### WebSocket Route

Defined in `src/api/routes/websocket.py`:

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    subscriber_task = asyncio.create_task(redis_subscriber())

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    finally:
        subscriber_task.cancel()
```

### Redis Subscriber

The `redis_subscriber()` coroutine subscribes to Redis pub/sub channels and broadcasts messages:

```python
async def redis_subscriber():
    redis = await get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(*CHANNELS)

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            event = {
                "channel": message["channel"],
                "data": data,
            }
            await manager.broadcast(event)
```

---

## Event Types

All events follow this structure:

```typescript
interface WSMessage {
  channel: string;  // Redis pub/sub channel
  data: any;        // Event payload (varies by channel)
}
```

---

### portfolio:update

**Purpose:** Portfolio value or position changes
**Frequency:** On position entry/exit, market data update
**Payload:**

```typescript
{
  channel: "portfolio:update",
  data: {
    total_equity: 25000.00,
    cash: 5000.00,
    positions_value: 20000.00,
    daily_pnl: 250.00,
    daily_pnl_pct: 1.02,
    total_pnl: 1500.00,
    total_pnl_pct: 6.38,
    max_drawdown_pct: -2.5,
    positions: [...],
    sector_exposure: {...}
  }
}
```

---

### trade:executed

**Purpose:** Trade fill confirmation
**Frequency:** On order fill
**Payload:**

```typescript
{
  channel: "trade:executed",
  data: {
    id: "trade-123",
    symbol: "AAPL",
    side: "BUY",
    quantity: 10,
    entry_price: 178.42,
    entry_time: "2026-03-12T14:30:00Z",
    strategy_name: "mean_reversion"
  }
}
```

---

### trade:pending_approval

**Purpose:** Trade awaiting manual approval (MANUAL_APPROVAL autonomy mode)
**Frequency:** When strategy generates signal in manual mode
**Payload:**

```typescript
{
  channel: "trade:pending_approval",
  data: {
    symbol: "AAPL",
    side: "BUY",
    quantity: 10,
    signal_strength: 0.82,
    strategy_name: "ml_signal",
    risk_assessment: {
      position_limit_ok: true,
      portfolio_limit_ok: true,
      pdt_ok: true
    },
    requires_approval_by: "2026-03-12T14:45:00Z"
  }
}
```

**Dashboard action:** Show modal with Approve/Reject buttons.

---

### order:status

**Purpose:** Order status change
**Frequency:** On submission, fill, cancellation, rejection
**Payload:**

```typescript
{
  channel: "order:status",
  data: {
    id: "order-456",
    broker_order_id: "12345678",
    symbol: "MSFT",
    status: "FILLED",  // PENDING, SUBMITTED, FILLED, CANCELLED, REJECTED
    filled_at: "2026-03-12T14:32:11Z",
    filled_price: 415.67,
    filled_quantity: 5
  }
}
```

---

### signal:generated

**Purpose:** New trading signal from strategy
**Frequency:** When strategy generates a signal
**Payload:**

```typescript
{
  channel: "signal:generated",
  data: {
    symbol: "TSLA",
    direction: "BUY",  // BUY, SELL, HOLD
    strength: 0.75,    // 0.0 to 1.0
    strategy_name: "momentum_crossover",
    timestamp: "2026-03-12T14:35:00Z",
    metadata: {
      indicators: {
        rsi: 42.5,
        macd: 2.3
      }
    }
  }
}
```

---

### risk:alert

**Purpose:** Risk warning (limit breach, high volatility, etc.)
**Frequency:** When risk check triggers a warning
**Payload:**

```typescript
{
  channel: "risk:alert",
  data: {
    type: "position_limit",  // position_limit, sector_limit, drawdown, etc.
    severity: "warning",     // info, warning, critical
    reason: "AAPL position size 6.2% exceeds 5% limit",
    symbol: "AAPL",
    current_value: 6.2,
    limit_value: 5.0,
    timestamp: "2026-03-12T14:40:00Z"
  }
}
```

**Dashboard action:** Show toast notification with amber/red color based on severity.

---

### risk:circuit_breaker

**Purpose:** Circuit breaker state change
**Frequency:** On activation/deactivation
**Payload:**

```typescript
{
  channel: "risk:circuit_breaker",
  data: {
    breaker: "vix_spike",  // vix_spike, stale_data, reconciliation_failed
    action: "activated",   // activated, deactivated
    reason: "VIX crossed threshold: 37.2 > 35",
    timestamp: "2026-03-12T14:50:00Z"
  }
}
```

**Dashboard action:** Show banner at top of screen. Disable trading UI when active.

---

### risk:kill_switch

**Purpose:** Kill switch activation/deactivation
**Frequency:** On kill switch state change
**Payload:**

```typescript
{
  channel: "risk:kill_switch",
  data: {
    action: "activate",  // activate, deactivate
    reason: "Manual override - unusual market conditions",
    operator: "human",   // human, system
    timestamp: "2026-03-12T15:00:00Z"
  }
}
```

**Dashboard action:** Show full-screen modal requiring typed confirmation ("KILL" or "RESUME").

---

### system:feed:disconnected

**Purpose:** Market data feed disconnection
**Frequency:** When IBKR feed disconnects
**Payload:**

```typescript
{
  channel: "system:feed:disconnected",
  data: {
    timestamp: "2026-03-12T16:00:00Z",
    reason: "IB Gateway connection closed (market close)"
  }
}
```

**Dashboard action:** Show "Feed Disconnected" indicator in header.

---

### system:feed:reconnected

**Purpose:** Market data feed reconnection
**Frequency:** When IBKR feed reconnects
**Payload:**

```typescript
{
  channel: "system:feed:reconnected",
  data: {
    timestamp: "2026-03-13T09:30:00Z",
    symbol_count: 503
  }
}
```

**Dashboard action:** Show "Feed Connected" indicator in header.

---

## Keepalive (Ping/Pong)

**Client → Server:**
```json
{"type": "ping"}
```

**Server → Client:**
```json
{"type": "pong"}
```

**Frequency:** Client sends ping every 30 seconds.
**Purpose:** Prevent idle connection timeout, detect broken connections.

The `useWebSocket` hook filters out `pong` messages so they don't trigger re-renders.

---

## Testing WebSocket Events

### Publish test event via Redis CLI

```bash
# Connect to Redis container
docker exec -it alpha-oracle-redis-1 redis-cli

# Publish test portfolio update
PUBLISH portfolio:update '{"total_equity": 26000, "cash": 6000, "positions_value": 20000}'

# Publish test signal
PUBLISH signal:generated '{"symbol": "AAPL", "direction": "BUY", "strength": 0.8, "strategy_name": "test"}'
```

The dashboard should receive and display the event immediately.

### WebSocket debugging in browser

```javascript
// Browser console
const ws = new WebSocket('ws://localhost:3000/ws');
ws.onmessage = (event) => console.log(JSON.parse(event.data));
ws.send(JSON.stringify({ type: 'ping' }));
```

---

## Error Handling

**Connection failure:**
- `useWebSocket` hook retries after 3 seconds
- Dashboard shows "Disconnected" status
- User actions queue locally until reconnection (if implemented)

**Malformed message:**
- Server catches `json.JSONDecodeError` and wraps in `{"raw": "..."}` object
- Client ignores or logs malformed messages

**Broadcast failure:**
- If a client's `send_json()` throws, it's removed from `active_connections`
- Other clients continue to receive events

---

<!-- DIAGRAM: WebSocket flow from Redis pub/sub through FastAPI to React dashboard -->
