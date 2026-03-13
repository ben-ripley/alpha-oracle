# Risk Management

The system protects your capital through four layers of risk controls. Every order passes through all four layers before execution. The philosophy is simple: **when in doubt, don't trade.**

## The 4 Layers

### Layer 1: Position Limits
**Controls individual stock positions.**

Every order is checked against these limits:

- **Max position size:** 5% of portfolio value per symbol
  - A $10,000 portfolio can hold max $500 in any single stock
  - Prevents over-concentration in one name

- **Max sector exposure:** 25% of portfolio per sector
  - Max $2,500 in Technology stocks (for $10,000 portfolio)
  - Prevents sector concentration risk

- **Stop-loss:** 2% stop-loss per position
  - If a position drops 2% from entry, it's automatically sold
  - Limits loss on any single trade

- **Min price filter:** $5 minimum stock price
  - No penny stocks (< $5 per share)
  - Avoids low-liquidity, high-volatility names

- **No leverage:** Margin/leverage disabled
  - Cash account only, no borrowed money
  - Cannot lose more than your capital

**What happens:** Orders that exceed these limits are either reduced in size or rejected entirely.

### Layer 2: Portfolio Limits
**Controls overall portfolio health.**

These limits apply to your entire account:

- **Max drawdown:** 10% from peak equity
  - If your account drops 10% from its highest value, all trading halts
  - Prevents catastrophic losses during losing streaks

- **Max daily loss:** 3% per day
  - If you lose 3% of your portfolio value in one day, trading halts until next day
  - Prevents spiral losses from bad days

- **Max positions:** 20 concurrent positions
  - Limits complexity and ensures adequate diversification
  - Each position gets meaningful capital allocation

- **Max daily trades:** 50 trades per day
  - Prevents runaway trading and excessive costs
  - Protects against algorithmic malfunctions

- **Cash reserve:** 10% minimum in cash
  - Always keeps 10% of portfolio in cash
  - Ensures liquidity for opportunities and withdrawals

**What happens:** If any limit is breached, the system enters a defensive mode and stops opening new positions until conditions improve.

### Layer 3: Circuit Breakers
**Detects abnormal market or system conditions.**

Automatic halts triggered by:

- **VIX spike:** VIX > 35
  - Indicates extreme market volatility
  - Trading pauses until volatility subsides
  - Prevents trading during panics or crashes

- **Stale data:** Price data older than 5 minutes
  - Detects data feed interruptions
  - Prevents trading on outdated information
  - System waits for fresh data before resuming

- **Position reconciliation:** Checks every 5 minutes
  - Compares system's position records to broker's actual positions
  - Alerts if drift exceeds 1%
  - Prevents trading with incorrect position data

- **Dead man switch:** 48-hour heartbeat required
  - Operator must check in every 48 hours
  - Prevents unattended autonomous trading
  - Halts system if no human oversight for 2 days

**What happens:** Circuit breakers pause trading and send alerts. Trading resumes automatically once the condition clears (except dead man switch, which requires manual restart).

### Layer 4: Kill Switch
**Emergency manual override.**

The [kill switch](../operations/kill-switch.md) is your nuclear option:

- Immediately halts ALL trading activity
- Cancels all pending orders
- No new orders accepted
- Requires typed confirmation ("KILL") to activate
- 60-minute cooldown before system can resume

Use when:
- Market crash or flash crash
- System behaving unexpectedly
- Need to stop everything immediately

Accessible from:
- Dashboard Risk page (red button)
- HTTP API: `POST /api/risk/kill-switch`

<!-- DIAGRAM: Flowchart showing order flowing through all 4 layers, with rejection points at each layer -->

## How the Layers Work Together

Every order follows this path:

```
New Order
  ↓
Layer 1: Position Limits Check
  ↓ PASS
Layer 2: Portfolio Limits Check
  ↓ PASS
Layer 3: Circuit Breaker Check
  ↓ PASS
Layer 4: Kill Switch Check
  ↓ PASS
Order Sent to Broker
```

If **any layer rejects**, the order is blocked. The reason is logged and displayed on the dashboard.

## The Conservative Philosophy

The system errs on the side of caution:

- **False rejection > missed opportunity:** Better to skip a trade than take excessive risk
- **Log everything:** Every decision is recorded for audit
- **Multiple redundant checks:** Position limits checked at order generation AND execution
- **Human override available:** [Kill switch](../operations/kill-switch.md) always accessible

This conservative approach means:
- You might miss some profitable trades
- But you'll avoid catastrophic losses
- Your capital is protected first, returns second

## Configuration

Limits are configured in `config/risk_limits.yaml`:

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

circuit_breakers:
  vix_threshold: 35.0
  stale_data_seconds: 300
  reconciliation_interval_seconds: 300
  max_reconciliation_drift_pct: 1.0
  dead_man_switch_hours: 48
```

See [Risk Limits Reference](../configuration/risk-limits.md) for all settings.

## Monitoring

The Risk page shows:
- Current vs. max values for all limits
- Warning indicators when approaching limits
- Circuit breaker status
- [PDT rule](./pdt-rule.md) compliance (day trade counter)
- Recent risk events log

<!-- DIAGRAM: Risk dashboard screenshot highlighting key metrics -->

## Related Topics

- [PDT Rule](./pdt-rule.md) — Pattern Day Trading restrictions (part of Layer 1)
- [Autonomy Modes](./autonomy-modes.md) — How autonomy levels affect risk controls
- [Kill Switch](../operations/kill-switch.md) — Emergency halt procedure
- [Monitoring & Alerts](../operations/monitoring-alerts.md) — How you're notified of risk events
