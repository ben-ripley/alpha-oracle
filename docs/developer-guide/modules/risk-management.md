# Risk Management Module

The `src/risk/` module implements multi-layered risk controls: [PDT](../glossary.md#pdt) guard (CRITICAL), pre-trade checks (position/portfolio limits), circuit breakers (VIX, stale data, drawdown), kill switch (emergency stop), and portfolio monitoring. All risk checks are conservative and exhaustively logged for audit.

## Purpose

Risk management provides:

- **PDT Guard** — Tracks day trades and enforces FINRA 3-in-5 rule (CRITICAL safety component)
- **Pre-trade checks** — Position limits, portfolio limits, minimum price, sector concentration
- **Circuit breakers** — Halt trading on extreme conditions (VIX spike, stale data, excessive drawdown)
- **Kill switch** — Emergency stop with typed confirmation and 60-min cooldown
- **Portfolio monitor** — Real-time drawdown tracking and alerts
- **Risk check cascade** — Layered validation before every order submission

## Key Components

### PDT Guard (CRITICAL)

#### `PDTGuardImpl` (src/risk/pdt_guard.py)

**The most critical safety component in the entire system.** A bug here could trigger FINRA Pattern Day Trader restrictions on the account (90-day trading suspension for violations).

**FINRA PDT Rule:**
- A **day trade** = buying AND selling the same security on the same calendar day.
- Accounts under $25K equity are limited to **3 day trades per 5 rolling business days**.
- If an account crosses below $25K, the PDT rule applies immediately.
- Violating the rule → account flagged as PDT → 90-day restriction on opening new positions.

**Implementation:**

**Day Trade Tracking:**
```python
# Record a completed day trade
await pdt_guard.record_day_trade(
    symbol="AAPL",
    trade_date=date.today(),
    metadata={"entry_time": "09:35", "exit_time": "14:20", "strategy": "SwingMomentum"}
)

# Stored in Redis sorted set: risk:pdt:trades
# Score = date.toordinal() for efficient range queries
```

**Counting Day Trades:**
```python
count = await pdt_guard.count_day_trades(rolling_window=5)
# Returns number of day trades in last 5 BUSINESS days (excludes weekends)
```

**Pre-Trade Validation:**
```python
result = await pdt_guard.check_order(
    order=sell_order,
    portfolio=portfolio,
    existing_position=position
)

# Returns RiskCheckResult with:
# - action: APPROVE | REJECT | REQUIRE_HUMAN_APPROVAL
# - reasons: ["Would create day trade 4 of max 3"]
# - metadata: {"day_trades_used": 3, "would_be_day_trade": True}
```

**Conservative Policy:**
- If portfolio equity < $25K threshold: Enforce PDT rule.
- If portfolio equity >= $25K: Allow unlimited day trades BUT still track (in case equity drops).
- If position entry and exit are same day: Count as day trade.
- If entry time is unknown: Conservatively assume it's a day trade (reject).
- If Redis is unavailable: Reject order (fail-safe).

**Logging:**
- Every PDT decision logged with `logger.warning()` for audit trail.
- Includes: symbol, order ID, day_trades_used, decision (approve/reject), timestamp.

**Configuration (config/risk_limits.yaml):**
```yaml
pdt_guard:
  enabled: true
  max_day_trades: 3
  rolling_window_days: 5
  account_threshold: 25000.0
```

**Critical Patterns:**
1. **Never weaken PDT checks** without explicit user instruction and thorough testing.
2. **Always log PDT decisions** for regulatory audit.
3. **Fail-safe:** If uncertain (e.g., Redis down), reject the order.
4. **Business day calculation:** Excludes weekends when counting rolling 5-day window.

### Pre-Trade Checks

#### `PreTradeChecks` (src/risk/pre_trade.py)

Validates orders against position and portfolio limits before submission.

**Position Limits** (per-symbol):

| Limit | Default | Purpose |
|-------|---------|---------|
| `max_position_pct` | 5.0% | Max portfolio allocation per symbol |
| `max_sector_pct` | 25.0% | Max portfolio allocation per sector |
| `stop_loss_pct` | 2.0% | Auto stop-loss distance |
| `min_price` | $5.00 | Avoid penny stocks (low liquidity, high volatility) |
| `no_leverage` | true | No margin, cash-only trades |

**Portfolio Limits** (aggregate):

| Limit | Default | Purpose |
|-------|---------|---------|
| `max_drawdown_pct` | 10.0% | Max drawdown from peak equity |
| `max_daily_loss_pct` | 3.0% | Max daily loss |
| `max_positions` | 20 | Max open positions |
| `max_daily_trades` | 50 | Max trades per day (prevent runaway strategies) |
| `min_cash_reserve_pct` | 10.0% | Min cash reserve (avoid margin calls) |

**Check Order:**
```python
from src.risk.pre_trade import PreTradeChecks

checks = PreTradeChecks()
result = await checks.check_order(order, portfolio)

if result.action == RiskAction.REJECT:
    logger.error("order_rejected", symbol=order.symbol, reasons=result.reasons)
    return  # Do not submit

if result.action == RiskAction.REDUCE_SIZE:
    order.quantity = result.adjusted_quantity
    logger.warning("order_size_reduced", original=order.quantity, adjusted=result.adjusted_quantity)

# result.action == RiskAction.APPROVE → submit order
```

**Validation Logic:**

1. **Minimum price:** Reject if `current_price < $5.00`.
2. **Position size:** Reject if `order_value / portfolio.total_equity > 5%`.
3. **Sector concentration:** Reject if adding position would exceed 25% sector allocation.
4. **Max positions:** Reject if portfolio already has 20 open positions and order opens a new one.
5. **Cash reserve:** Reject if trade would leave < 10% cash.
6. **Daily loss:** Reject if portfolio.daily_pnl_pct < -3%.
7. **Max drawdown:** Reject if portfolio.max_drawdown_pct > 10%.

**Configuration (config/risk_limits.yaml):**
```yaml
position_limits:
  max_position_pct: 5.0
  max_sector_pct: 25.0
  stop_loss_pct: 2.0
  min_price: 5.0
  no_leverage: true

portfolio_limits:
  max_drawdown_pct: 10.0
  max_daily_loss_pct: 3.0
  max_positions: 20
  max_daily_trades: 50
  min_cash_reserve_pct: 10.0
```

### Circuit Breakers

#### `CircuitBreakerManager` (src/risk/circuit_breaker.py)

Independent safety switches that halt trading on extreme market conditions.

**Breakers:**

1. **VIXBreaker:** Trips if VIX > 35 (extreme market fear).
2. **StaleDataBreaker:** Trips if last data update > 5 minutes old (connectivity issue).
3. **DrawdownBreaker:** Trips if portfolio drawdown > 10%.
4. **DailyLossBreaker:** Trips if daily P&L < -3%.
5. **ReconciliationBreaker:** Trips if broker portfolio diverges > 1% from internal state (data integrity issue).
6. **DeadManSwitchBreaker:** Trips if no health check received in 48 hours (system crash).

**Check Logic:**
```python
from src.risk.circuit_breaker import CircuitBreakerManager

cb_manager = CircuitBreakerManager()
context = {
    "vix_level": 38.5,
    "last_data_timestamp": datetime.now(timezone.utc) - timedelta(minutes=10),
    "max_drawdown_pct": 8.0,
    "daily_pnl_pct": -2.5,
    "reconciliation_drift_pct": 0.3,
    "last_health_check": datetime.now(timezone.utc) - timedelta(hours=1)
}

tripped = await cb_manager.check_all(context)
# Returns list of (breaker_name, reason) tuples for tripped breakers

if tripped:
    logger.critical("circuit_breakers_tripped", breakers=tripped)
    await kill_switch.activate("Circuit breakers tripped: " + str(tripped))
```

**State Persistence:**
- Breaker states stored in Redis: `risk:circuit_breaker:{name}:tripped`.
- TTL = 1 hour (auto-reset after conditions normalize).

**Configuration (config/risk_limits.yaml):**
```yaml
circuit_breakers:
  vix_threshold: 35.0
  stale_data_seconds: 300
  reconciliation_interval_seconds: 300
  max_reconciliation_drift_pct: 1.0
  dead_man_switch_hours: 48
```

### Kill Switch

#### `KillSwitch` (src/risk/kill_switch.py)

Emergency stop mechanism with manual activation and typed confirmation.

**Activation:**
```python
from src.risk.kill_switch import KillSwitch

kill_switch = KillSwitch()
await kill_switch.activate(reason="Manual stop: market crash detected")

# State stored in:
# - Redis: risk:kill_switch:active = "true"
# - Database: kill_switch_events table
```

**Confirmation Required:**

For safety, activation requires typed confirmation "KILL" or "KILL SWITCH" in the UI.

**Deactivation:**
```python
await kill_switch.deactivate()

# Cooldown: Cannot re-activate for 60 minutes after deactivation
# Prevents accidental rapid on/off toggling
```

**Check Before Order Submission:**
```python
if await kill_switch.is_active():
    logger.error("order_rejected_kill_switch", symbol=order.symbol)
    return RiskCheckResult(action=RiskAction.REJECT, reasons=["Kill switch active"])
```

**Telegram Integration:**
```yaml
kill_switch:
  http_enabled: true
  telegram_enabled: false  # Set to true + configure bot token
  cooldown_minutes: 60
```

Telegram bot allows remote kill switch activation via message command.

### Portfolio Monitor

#### `PortfolioMonitor` (src/risk/portfolio_monitor.py)

Real-time tracking of portfolio metrics and drawdown.

**Metrics Tracked:**
- Total equity (cash + positions value)
- Daily P&L (absolute and percentage)
- Unrealized P&L per position
- Sector exposure (% of portfolio per sector)
- Max drawdown from peak equity

**Drawdown Calculation:**
```python
peak_equity = max(equity_history)
current_equity = portfolio.total_equity
drawdown_pct = ((current_equity - peak_equity) / peak_equity) * 100
```

**Alerts:**
- Drawdown > 5%: WARNING (Slack notification)
- Drawdown > 8%: CRITICAL (Slack + Telegram)
- Drawdown > 10%: Circuit breaker trips, kill switch activated

**Update Frequency:**
- Real-time: On every portfolio snapshot (triggered by fills, position updates).
- Scheduled: Every 5 minutes during market hours.

### Risk Check Cascade

All orders pass through a **layered risk check cascade** before submission:

```
Order → Kill Switch → Circuit Breakers → PDT Guard → Position Limits → Portfolio Limits → Autonomy Gate → Submit
```

1. **Kill Switch:** If active, reject immediately.
2. **Circuit Breakers:** If any tripped, reject with reason.
3. **PDT Guard:** Check if order would create day trade #4+ in 5 days.
4. **Position Limits:** Check symbol price, position size, sector concentration.
5. **Portfolio Limits:** Check cash reserve, max positions, daily loss, drawdown.
6. **Autonomy Gate:** If mode is MANUAL_APPROVAL, pause for human review.
7. **Submit:** Order passes all checks → sent to broker adapter.

**Risk Manager Orchestration:**
```python
from src.risk.manager import RiskManager

risk_manager = RiskManager()
result = await risk_manager.check_pre_trade(order, portfolio)

if result.action == RiskAction.REJECT:
    # Log rejection + reasons
    # Do not submit order
elif result.action == RiskAction.REQUIRE_HUMAN_APPROVAL:
    # Queue order for manual review
    # Send notification to dashboard + Slack
elif result.action == RiskAction.REDUCE_SIZE:
    # Adjust order quantity
    # Re-run risk checks
else:  # RiskAction.APPROVE
    # Submit order to broker
```

## Configuration

**Risk Limits (config/risk_limits.yaml):**
```yaml
autonomy_mode: "PAPER_ONLY"        # PAPER_ONLY | MANUAL_APPROVAL | BOUNDED_AUTONOMOUS | FULL_AUTONOMOUS

position_limits:
  max_position_pct: 5.0
  max_sector_pct: 25.0
  stop_loss_pct: 2.0
  min_price: 5.0
  no_leverage: true

portfolio_limits:
  max_drawdown_pct: 10.0
  max_daily_loss_pct: 3.0
  max_positions: 20
  max_daily_trades: 50
  min_cash_reserve_pct: 10.0

pdt_guard:
  enabled: true
  max_day_trades: 3
  rolling_window_days: 5
  account_threshold: 25000.0

circuit_breakers:
  vix_threshold: 35.0
  stale_data_seconds: 300
  max_reconciliation_drift_pct: 1.0
  dead_man_switch_hours: 48

kill_switch:
  http_enabled: true
  telegram_enabled: false
  cooldown_minutes: 60
```

**Environment Variable Overrides:**
```bash
export SA_RISK__AUTONOMY_MODE=BOUNDED_AUTONOMOUS
export SA_RISK__POSITION_LIMITS__MAX_POSITION_PCT=3.0
export SA_RISK__PORTFOLIO_LIMITS__MAX_DRAWDOWN_PCT=5.0
export SA_RISK__PDT_GUARD__ENABLED=false  # DANGER: Only for testing!
```

## Integration with Other Modules

- **Execution Engine** (`src/execution/`): All orders pass through `RiskManager.check_pre_trade()` before submission.
- **API** (`src/api/routes/risk.py`): Endpoints for kill switch, circuit breaker status, risk metrics.
- **Dashboard** (`web/src/pages/Risk.tsx`): Displays risk limits, PDT status, circuit breaker states, kill switch control.
- **Monitoring** (`src/monitoring/`): Prometheus metrics for PDT trades used, circuit breakers tripped, kill switch active.
- **Scheduler** (`src/scheduling/`): Runs reconciliation job every 5 minutes to detect drift.

## Critical Patterns

1. **PDT Guard is sacred:** Never weaken without explicit instruction. Always log every decision.
2. **Conservative fail-safe:** If uncertain (Redis down, missing data), reject the order.
3. **Layered checks:** Order must pass ALL layers before submission.
4. **Circuit breaker auto-reset:** Breakers clear after 1 hour if conditions normalize.
5. **Kill switch confirmation:** Requires typed "KILL" to prevent accidental activation.
6. **Audit trail:** All risk decisions logged to database + structlog for regulatory compliance.
7. **Autonomy mode gating:** PAPER_ONLY → no live trades. MANUAL_APPROVAL → queue for human review.

## Glossary Links

- [PDT](../glossary.md#pdt) — Pattern Day Trader rule (FINRA)
- [FINRA](../glossary.md#finra) — Financial Industry Regulatory Authority
- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [Redis](../glossary.md#redis) — In-memory data store
- [VIX](../glossary.md#vix) — CBOE Volatility Index (market fear gauge)

<!-- DIAGRAM: Risk check cascade — kill switch → circuit breakers → PDT → position limits → portfolio limits → autonomy gate → submit -->
