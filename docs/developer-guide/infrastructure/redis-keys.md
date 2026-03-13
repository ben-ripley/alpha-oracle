# Redis Keys Reference

[Redis](../glossary.md#redis) is used for caching, rate limiting, PDT tracking, job idempotency, and pub/sub event broadcasting. All keys use a namespace prefix for organization.

## Key Patterns

### PDT Guard

#### `risk:pdt:trades`
**Type:** Sorted set
**Purpose:** Track day trades for PDT rule enforcement
**Score:** Date ordinal (days since epoch)
**Members:** JSON-encoded trade objects with `symbol`, `date`, `recorded_at`, and optional metadata
**TTL:** Entries older than 8 days are automatically trimmed
**Critical:** This key is the source of truth for PDT compliance. Never manually delete while trading.

Example member:
```json
{
  "symbol": "AAPL",
  "date": "2026-03-12",
  "recorded_at": "2026-03-12T14:32:11.123456Z",
  "order_id": "abc123"
}
```

**Query pattern:**
```python
# Count day trades in last 5 business days
start_date = business_days_ago(5)
count = redis.zcount("risk:pdt:trades", start_date.toordinal(), "+inf")
```

---

### Kill Switch

#### `risk:kill_switch`
**Type:** String
**Purpose:** Kill switch activation state
**Values:** `"active"` or `"inactive"`
**TTL:** None (persists until explicit change)

The kill switch halts all trading when active. The database table `kill_switch` is the primary source of truth; this Redis key is a fast-access cache synchronized on activation/deactivation.

---

### Job Idempotency

#### `jobs:daily_bars:{YYYY-MM-DD}:done`
**Type:** Set
**Purpose:** Track completed symbols for daily bar ingestion
**Members:** Stock symbols (e.g., `"AAPL"`, `"MSFT"`)
**TTL:** 25 hours (auto-expires after market close the next day)

Example: `jobs:daily_bars:2026-03-12:done` contains all symbols successfully fetched on March 12, 2026.

**Usage:**
- Job checks if key exists before starting
- Symbols are added to set as they complete
- Interrupted jobs can resume by checking membership

---

#### `jobs:weekly_fundamentals:{YYYY-W##}:done`
**Type:** Set
**Purpose:** Track completed symbols for weekly fundamental data ingestion
**Members:** Stock symbols
**TTL:** 8 days (expires after one week + buffer)

Example: `jobs:weekly_fundamentals:2026-W11:done` for ISO week 11 of 2026.

**Week label format:** ISO 8601 week-numbering year and week (e.g., `2026-W11`)

---

#### `jobs:altdata:last_run`
**Type:** String (ISO-8601 timestamp)
**Purpose:** Track last successful alternative data job run
**Value:** ISO timestamp of last completion (e.g., `"2026-03-12T10:00:00Z"`)
**TTL:** None (persistent)

The biweekly alternative data job (Form 4 insider transactions, FINRA short interest) uses this key to fetch incremental data since the last run.

---

#### `backfill:completed`
**Type:** Set
**Purpose:** Track symbols already backfilled with historical data
**Members:** Stock symbols
**TTL:** None (persistent)

The `backfill_history.py` script uses this set to resume interrupted backfill jobs. Symbols are added as their historical data is successfully stored. Use `--reset` flag to clear this set and start over.

---

### System Status

#### `system:status`
**Type:** String (JSON)
**Purpose:** Cache of system connectivity status
**Value:** JSON object with broker and feed status
**TTL:** None (updated on status change)

Example:
```json
{
  "broker": "connected",
  "feed": "connected"
}
```

Published by the FastAPI startup lifespan handler and consumed by the WebSocket endpoint to broadcast system health to dashboard clients.

---

## Pub/Sub Channels

Redis pub/sub is used for real-time event broadcasting from backend to frontend via WebSocket.

### `portfolio:update`
**Purpose:** Portfolio value or position changes
**Payload:** JSON with portfolio snapshot data

---

### `trade:executed`
**Purpose:** Trade fill confirmations
**Payload:** JSON with trade details (symbol, side, quantity, price, timestamp)

---

### `trade:pending_approval`
**Purpose:** Trades waiting for manual approval (MANUAL_APPROVAL autonomy mode)
**Payload:** JSON with trade proposal and risk assessment

---

### `order:status`
**Purpose:** Order status changes (submitted, filled, cancelled, rejected)
**Payload:** JSON with order ID, status, broker order ID

---

### `risk:alert`
**Purpose:** Risk warnings (position limit breaches, high volatility, etc.)
**Payload:** JSON with alert type, severity, reason, affected symbols

---

### `risk:circuit_breaker`
**Purpose:** Circuit breaker state changes (activated, deactivated)
**Payload:** JSON with breaker type (e.g., 'vix_spike', 'stale_data'), action, reason

---

### `risk:kill_switch`
**Purpose:** Kill switch activation or deactivation events
**Payload:** JSON with action ('activate' or 'deactivate'), reason, operator, timestamp

Example:
```json
{
  "action": "activate",
  "reason": "Manual override - unusual market conditions",
  "operator": "human",
  "timestamp": "2026-03-12T15:45:00Z"
}
```

---

### `signal:generated`
**Purpose:** New trading signals from strategy engine
**Payload:** JSON with symbol, direction, strength, strategy name, timestamp

---

### `system:feed:disconnected`
**Purpose:** Market data feed disconnection events
**Payload:** JSON with timestamp and reason

---

### `system:feed:reconnected`
**Purpose:** Market data feed reconnection events
**Payload:** JSON with timestamp and symbol count

---

## Rate Limiting

Rate limiting is handled by the `RateLimiter` class in `src/data/rate_limiter.py`. Keys follow the pattern:

#### `rate_limit:{name}:tokens`
**Type:** String (float)
**Purpose:** Available tokens for rate limiter
**Value:** Number of tokens available (decremented on acquire, refilled over time)
**TTL:** None (managed by RateLimiter)

#### `rate_limit:{name}:last_refill`
**Type:** String (float)
**Purpose:** Last token refill timestamp
**Value:** Unix timestamp (float)
**TTL:** None (managed by RateLimiter)

Example:
- `rate_limit:alpha_vantage:tokens`
- `rate_limit:ibkr_data:tokens`

---

## Cache Keys

General-purpose caching uses the pattern:

#### `cache:{domain}:{identifier}`
**Type:** String (JSON)
**Purpose:** Application-level cache
**TTL:** Varies by use case (typically 5-60 minutes)

Example:
- `cache:fundamentals:AAPL` — cached fundamental data for AAPL
- `cache:universe:sp500` — cached S&P 500 symbol list

---

## Management

### View all keys
```bash
docker exec -it alpha-oracle-redis-1 redis-cli KEYS "*"
```

### Inspect a key
```bash
# String key
docker exec -it alpha-oracle-redis-1 redis-cli GET "risk:kill_switch"

# Set members
docker exec -it alpha-oracle-redis-1 redis-cli SMEMBERS "jobs:daily_bars:2026-03-12:done"

# Sorted set (PDT trades)
docker exec -it alpha-oracle-redis-1 redis-cli ZRANGE "risk:pdt:trades" 0 -1 WITHSCORES
```

### Clear all keys (development only)
```bash
docker exec -it alpha-oracle-redis-1 redis-cli FLUSHALL
```

### Clear demo data (prepare for real trading)
```bash
./scripts/clear_database.sh
```

This script clears job idempotency keys and cache but preserves PDT tracking and kill switch state.

---

<!-- DIAGRAM: Redis key namespace hierarchy and pub/sub channel flow -->
