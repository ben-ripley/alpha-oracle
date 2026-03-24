---
title: Execution Engine Module
nav_order: 5
parent: Modules
---

# Execution Engine Module

The `src/execution/` module converts trading signals into executed orders: position sizing via Half-Kelly criterion, smart order routing (market/limit/TWAP), broker adapter integration ([IBKR](../glossary.md#ibkr)/PaperStub/Simulated), and execution quality tracking (slippage, latency).

## Purpose

The execution engine provides:

- **Order generation** from signals with Half-Kelly position sizing
- **Smart order router** selecting order type based on size, spread, and urgency
- **Broker adapters** for real (IBKR), paper (demo data), and simulated trading
- **Execution quality tracker** measuring slippage and fill latency
- **Order lifecycle management** (pending → submitted → filled/cancelled/rejected)

## Key Components

### Order Generator

#### `OrderGenerator` (src/execution/order_generator.py)

Generates orders from trading signals using the Kelly criterion for position sizing.

**Kelly Criterion:**

Optimal fraction of capital to allocate:
```
f* = (p * b - q) / b

where:
  p = win rate (e.g., 0.55)
  b = average win / average loss (e.g., 2.0 / 1.0 = 2.0)
  q = 1 - p = loss rate
  f* = Kelly fraction (e.g., 0.15 = 15% of capital)
```

**Half-Kelly (Conservative):**
```
position_size = portfolio.cash * f* / 2 / current_price
```

Half-Kelly reduces risk of ruin from estimation errors.

**Order Generation Flow:**
1. Extract `win_rate`, `avg_win_pct`, `avg_loss_pct` from signal metadata.
2. Calculate Kelly fraction.
3. Calculate quantity: `cash * kelly_frac / 2 / price`.
4. Apply position limits (max 5% of portfolio per position).
5. Set order type (MARKET or LIMIT based on config).
6. Set stop-loss price (2% below entry for longs, 2% above for shorts).

**Usage:**
```python
from src.execution.order_generator import OrderGenerator
from src.core.models import Signal, PortfolioSnapshot

generator = OrderGenerator()
signal = Signal(
    symbol="AAPL",
    direction=SignalDirection.LONG,
    strength=0.75,
    metadata={"win_rate": 0.55, "avg_win_pct": 2.0, "avg_loss_pct": 1.0}
)
portfolio = PortfolioSnapshot(total_equity=100_000, cash=50_000, ...)

order = generator.generate_order(signal, portfolio)
# order.quantity calculated via Half-Kelly
# order.limit_price set if default_order_type=limit
# order.stop_price set to 2% stop-loss
```

**Configuration** (config/settings.yaml):
```yaml
execution:
  default_order_type: "limit"      # market | limit
  limit_offset_pct: 0.05           # 5 bps offset for limit orders
  max_slippage_pct: 0.10           # 10 bps max acceptable slippage
  position_sizing: "half_kelly"    # half_kelly | fixed | percent_equity
```

### Smart Order Router

#### `SmartOrderRouter` (src/execution/router.py)

Selects order type and slicing strategy based on market conditions.

**Routing Logic:**

| Condition | Order Type | Reasoning |
|-----------|------------|-----------|
| Signal strength > 0.9 | MARKET | High urgency → accept slippage |
| Spread > 20 bps | LIMIT at mid + offset | Wide spread → passive fill |
| Order size > 1.0% ADV | TWAP (5 slices, 60s interval) | Large order → minimize market impact |
| Order size < 0.1% ADV | LIMIT at best bid/ask | Small order → passive fill |
| Default | LIMIT at bid+offset (buy) or ask-offset (sell) | Standard execution |

**Quote Data Source:**
- Router reads `bid_price`, `ask_price`, `volume` from `market:quotes:{symbol}` [Redis](../glossary.md#redis) channel.
- Published by `IBKRMarketFeed` (see [Data Ingestion Module](./data-ingestion.md)).

**TWAP Slicing:**

For large orders (> 1% of average daily volume):
```python
# Split 1000 shares into 5 slices of 200 each
# Submit one slice every 60 seconds
# Reduces market impact vs. single large order

slices = router._create_twap_slices(order, num_slices=5)
# Returns list of 5 Order objects with metadata:
# - twap_slice: 1, 2, 3, 4, 5
# - twap_total_slices: 5
# - twap_interval_seconds: 60
# - parent_order_id: original order ID
```

**Configuration** (config/settings.yaml):
```yaml
router:
  size_threshold_small_pct: 0.1    # < 0.1% ADV → passive limit
  size_threshold_large_pct: 1.0    # > 1.0% ADV → TWAP
  twap_num_slices: 5               # Split large orders into 5 slices
  twap_interval_seconds: 60        # 60s between slices
  wide_spread_threshold_bps: 20.0  # > 20 bps → use limit at mid
```

**Usage:**
```python
from src.execution.router import SmartOrderRouter

router = SmartOrderRouter(feed=market_feed)
orders = await router.route(order)

# Returns list (usually 1 order, but 5 for TWAP)
for routed_order in orders:
    await broker.submit_order(routed_order)
    if "twap_interval_seconds" in routed_order.metadata:
        await asyncio.sleep(routed_order.metadata["twap_interval_seconds"])
```

### Broker Adapters

All broker adapters implement the `BrokerAdapter` interface (see [Core Module](./core.md)).

#### `IBKRBrokerAdapter` (src/execution/broker/ibkr_broker.py)

Real trading via [IBKR](../glossary.md#ibkr) API using `ib-async` library.

**Methods:**
- `submit_order(order: Order) -> Order`: Submits order to IB Gateway / TWS. Returns order with `broker_order_id` and `status=SUBMITTED`.
- `cancel_order(broker_order_id: str) -> bool`: Cancels pending order.
- `get_order_status(broker_order_id: str) -> OrderStatus`: Polls order status (PENDING/SUBMITTED/FILLED/CANCELLED/REJECTED).
- `get_positions() -> list[Position]`: Fetches current open positions.
- `get_portfolio() -> PortfolioSnapshot`: Fetches portfolio summary (equity, cash, positions, P&L).
- `health_check() -> bool`: Validates connection to IB Gateway / TWS.

**Client ID Scheme:**
- Broker adapter: `client_id` (default: 1)
- Data adapter: `client_id + 1` (default: 2)
- Market feed: `client_id + 2` (default: 3)

Never reuse IDs across connections (IBKR rejects duplicate client IDs).

**Configuration:**
```yaml
broker:
  provider: "ibkr"                  # ibkr | simulated | paper_stub
  paper_trading: true               # true = paper account, false = live
  ibkr:
    host: "127.0.0.1"
    port: 4002                      # 4002=Gateway paper, 4001=Gateway live, 7497=TWS paper, 7496=TWS live
    client_id: 1
    account_id: ""                  # blank for single-account setups
```

**Order Lifecycle:**
1. `submit_order()` sends order to IBKR → receives `broker_order_id` (e.g., "12345").
2. Order status transitions: PENDING → SUBMITTED → (PARTIALLY_FILLED) → FILLED.
3. Fills trigger `order_filled` event → published to Redis `execution:fills` channel.
4. Execution engine updates order in DB and portfolio snapshot.

#### `PaperStubBroker` (src/execution/broker/paper_stub.py)

Demo broker with seed data. Does not execute real orders.

**Behavior:**
- `submit_order()`: Immediately marks order as FILLED with simulated fill price (current market price + random slippage).
- `get_portfolio()`: Returns static demo portfolio (cash=$100K, 3 positions: AAPL, MSFT, GOOG).
- `get_positions()`: Returns demo positions with mock P&L.

**Used when:**
- `SA_BROKER__PROVIDER` is not "ibkr" and not "simulated" (e.g., "demo", "stub", or unset).
- IBKR connection fails → system falls back to PaperStubBroker.

#### `SimulatedBroker` (src/execution/broker/simulated_broker.py)

In-memory simulation for backtesting and testing.

**Behavior:**
- `submit_order()`: Validates order against available cash, updates in-memory positions, marks as FILLED.
- `get_portfolio()`: Returns current simulated portfolio state.
- Tracks commission and slippage (0.005% commission, 0.05% slippage).
- Resets state between backtest runs.

**Used when:**
- `SA_BROKER__PROVIDER=simulated`
- Backtesting via `BacktraderEngine` (if configured to use SimulatedBroker instead of Backtrader's internal broker).

### Execution Quality Tracker

#### `ExecutionQualityTracker` (src/execution/quality.py)

Measures order execution performance.

**Metrics:**

| Metric | Definition | Formula |
|--------|------------|---------|
| `slippage_bps` | Fill price vs. limit price | `(filled_price - limit_price) / limit_price * 10000` |
| `arrival_slippage_bps` | Fill price vs. signal price | `(filled_price - signal_price) / signal_price * 10000` |
| `fill_latency_ms` | Time from signal to fill | `(fill_timestamp - signal_timestamp).total_seconds() * 1000` |

**Storage:**
- Metrics logged to `ExecutionQualityMetrics` model.
- Stored in TimescaleDB `execution_quality` table.
- Aggregated daily/weekly for performance reports.

**Usage:**
```python
from src.execution.quality import ExecutionQualityTracker

tracker = ExecutionQualityTracker()
metrics = tracker.compute_metrics(
    order_id="abc123",
    symbol="AAPL",
    side=OrderSide.BUY,
    expected_price=150.00,
    filled_price=150.05,
    signal_timestamp=datetime(...),
    fill_timestamp=datetime(...)
)

# metrics.slippage_bps = 3.33 bps
# metrics.fill_latency_ms = 1250 ms
await tracker.store_metrics(metrics)
```

**Dashboard Integration:**
- `ExecutionQualityChart` component displays average slippage and latency over time.
- Alerts triggered if slippage > 10 bps or latency > 5 seconds.

## Data Flow

<!-- DIAGRAM: Execution flow — signal → order generator → router → broker adapter → fills → quality tracker -->

1. **Signal Generation:**
   - Strategy (or MLSignalStrategy) generates `Signal` objects.
   - Execution engine receives signals via `execution:signals` Redis channel.

2. **Order Generation:**
   - `OrderGenerator.generate_order()` converts signal → order with Kelly sizing.
   - Order includes metadata: `signal_strength`, `strategy_name`, `signal_timestamp`.

3. **Pre-Trade Risk Checks:**
   - `RiskManager.check_pre_trade()` validates order against position/portfolio limits, [PDT](../glossary.md#pdt) guard, circuit breakers.
   - If rejected, order status set to REJECTED, logged, and not submitted.

4. **Smart Routing:**
   - `SmartOrderRouter.route()` selects order type (market/limit/TWAP).
   - Reads real-time quotes from Redis `market:quotes:{symbol}` channel.
   - Returns list of orders (1 for standard, 5 for TWAP).

5. **Order Submission:**
   - `BrokerAdapter.submit_order()` sends order to broker (IBKR, PaperStub, or Simulated).
   - Order status transitions to SUBMITTED.
   - Broker order ID stored in `order.broker_order_id`.

6. **Fill Notification:**
   - Broker publishes fill event to Redis `execution:fills` channel.
   - Execution engine updates order status to FILLED.
   - Portfolio snapshot recalculated.

7. **Quality Tracking:**
   - `ExecutionQualityTracker.compute_metrics()` calculates slippage and latency.
   - Metrics stored in TimescaleDB.
   - Alerts triggered if thresholds exceeded.

## Configuration

**Settings (config/settings.yaml):**
```yaml
broker:
  provider: "ibkr"                  # ibkr | simulated | paper_stub
  paper_trading: true
  ibkr:
    host: "127.0.0.1"
    port: 4002
    client_id: 1
    account_id: ""

execution:
  default_order_type: "limit"
  limit_offset_pct: 0.05            # 5 bps
  max_slippage_pct: 0.10            # 10 bps
  position_sizing: "half_kelly"

router:
  size_threshold_small_pct: 0.1
  size_threshold_large_pct: 1.0
  twap_num_slices: 5
  twap_interval_seconds: 60
  wide_spread_threshold_bps: 20.0
```

**Environment Variable Overrides:**
```bash
# Switch to live IBKR
export SA_BROKER__PROVIDER=ibkr
export SA_BROKER__PAPER_TRADING=false
export SA_BROKER__IBKR__PORT=4001  # Gateway live

# Use simulated broker for testing
export SA_BROKER__PROVIDER=simulated

# Adjust router thresholds
export SA_ROUTER__SIZE_THRESHOLD_LARGE_PCT=0.5
export SA_ROUTER__TWAP_NUM_SLICES=10
```

## Integration with Other Modules

- **Strategy Engine** (`src/strategy/`): Strategies generate signals → execution engine.
- **Risk Management** (`src/risk/`): Pre-trade checks gate all orders before submission.
- **Data Ingestion** (`src/data/`): Market feed provides real-time quotes for router.
- **Scheduler** (`src/scheduling/`): TWAP slices executed at scheduled intervals.
- **API** (`src/api/routes/trades.py`): Endpoints for order history, execution metrics.
- **Dashboard** (`web/src/pages/Trades.tsx`): Displays orders, fills, execution quality.

## Critical Patterns

1. **Half-Kelly sizing:** Conservative position sizing reduces risk of ruin.
2. **Smart routing:** Order type selection minimizes slippage and market impact.
3. **TWAP for large orders:** Splits orders > 1% ADV into 5 slices over 5 minutes.
4. **Client ID isolation:** Broker (+0), data (+1), feed (+2) use separate IDs.
5. **Execution quality tracking:** All fills measured for slippage and latency.
6. **Broker fallback:** If IBKR connection fails, system falls back to PaperStubBroker.
7. **Order lifecycle:** Pending → Submitted → Filled/Cancelled/Rejected (never directly to Filled without Submitted).

## Glossary Links

- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [PDT](../glossary.md#pdt) — Pattern Day Trader rule
- [OHLCV](../glossary.md#ohlcv) — Open/High/Low/Close/Volume bar data
- [Redis](../glossary.md#redis) — In-memory data store
- [Kelly Criterion](../glossary.md#kelly-criterion) — Optimal position sizing formula

<!-- DIAGRAM: Smart router decision tree — signal strength, spread, order size → market/limit/TWAP -->
