# Risk Page

The Risk page monitors compliance with the [PDT rule](../../glossary.md#pdt), position/portfolio limits, circuit breakers, and provides the kill switch for emergency stops.

## Overview

Risk management is the most critical aspect of automated trading. This page ensures:
1. **Regulatory compliance** — No PDT violations (FINRA penalties)
2. **Loss prevention** — Drawdown and daily loss limits enforced
3. **System safety** — Circuit breakers halt trading when conditions are dangerous
4. **Emergency control** — Kill switch provides instant manual override

## PDT Day Trade Guard

The most prominent section tracks your [Pattern Day Trade](../../glossary.md#pdt) usage:

### What is the PDT Rule?

FINRA (Financial Industry Regulatory Authority) enforces the Pattern Day Trader rule for accounts under $25,000:
- **Maximum 3 day trades** per rolling 5-business-day window
- **Day trade definition**: Buy and sell (or sell and buy) the same stock on the same day
- **Penalty**: Account is flagged as PDT and restricted from day trading for 90 days

**Why this matters**: Violating the PDT rule locks you out of day trading, severely limiting your strategy options.

### PDT Counter Display

The counter shows:
- **Large number** (e.g., "2/3") — Day trades used out of maximum allowed
- **Color coding**:
  - Green (0-1 used) — Safe, plenty of day trades available
  - Amber (2 used) — Caution, one away from limit
  - Red (3 used) — Maxed out, cannot day trade until oldest trade exits the 5-day window
- **Progress bars** — Visual indicator of usage (filled bars = used trades)
- **Reset message** — "Window resets as oldest trade exits 5-day lookback"

**Example**:
```
2 / 3
██████  ██████  ░░░░░░
2 day trades remaining · Window resets as oldest trade exits 5-day lookback
```

You've used 2 day trades. If you use the 3rd, you cannot day trade again until the oldest trade (from 5 business days ago) rolls off the window.

### How the System Protects You

The PDT guard is **conservative by design**:
- **Rejects potential day trades** when count is at 3/3
- **Enforces minimum hold periods** (strategies use `min_hold_days >= 2`)
- **Logs every decision** for audit trail
- **Counts sells on same day as a buy** even if separated by hours

The guard is the system's **most critical safety component**. Never disable or bypass it without fully understanding the consequences.

<!-- DIAGRAM: PDT counter with color states (green, amber, red) and rollover timeline -->

## Drawdown Chart

A 60-day area chart showing your account's [drawdown](../../glossary.md#drawdown) over time:

- **X-axis**: Date (last 60 days)
- **Y-axis**: Drawdown percentage (0% to -20%)
- **Red dashed line**: Maximum drawdown limit (default: -10%)
- **Red area fill**: Current drawdown zone

### Understanding Drawdown

Drawdown measures how far your equity has fallen from its peak:

```
Peak Equity: $25,000 (Jan 1)
Current Equity: $23,500 (Jan 15)
Drawdown: ($23,500 - $25,000) / $25,000 = -6.0%
```

**Why it matters**:
- Large drawdowns are hard to recover from (-50% requires +100% to break even)
- The system halts trading if drawdown exceeds -10% (default limit)

**Interpreting the chart**:
- **Flat at 0%** — Account at all-time high (no drawdown)
- **Shallow dips (-2% to -5%)** — Normal market volatility
- **Moderate drawdown (-5% to -10%)** — Strategy underperformance, review needed
- **Near/at limit (-10%+)** — Circuit breaker triggers, trading halted

<!-- DIAGRAM: Drawdown chart with annotated zones (safe, caution, danger) -->

## Limit Utilization

Four progress bars show how close you are to portfolio limits:

### 1. Drawdown
- **Current**: Your current drawdown percentage
- **Limit**: Maximum allowed drawdown (default: 10%)
- **Color**: Cyan (safe), amber (>70% utilized), red (>90% or exceeded)

### 2. Daily Loss
- **Current**: Today's loss as a percentage (absolute value)
- **Limit**: Maximum daily loss (default: 3%)
- **Calculation**: `|min(Daily P&L %, 0)|`

If you've lost 2.5% today and the limit is 3%, the bar shows 83% utilization (2.5 / 3.0).

### 3. Positions
- **Current**: Number of open positions
- **Limit**: Maximum positions allowed (default: 20)
- **Why it matters**: Too many positions dilute focus and increase margin risk

### 4. Cash Reserve
- **Current**: Cash as percentage of equity
- **Limit**: Minimum required cash reserve (default: 10%)
- **Note**: This bar is **inverted** — color is green when cash is *above* the limit

**Example**:
```
Drawdown:     ████████░░  80% (8.0% / 10%)  [AMBER]
Daily Loss:   ██████░░░░  60% (1.8% / 3%)   [CYAN]
Positions:    ████░░░░░░  40% (8 / 20)      [CYAN]
Cash Reserve: ██████████  100% (12% / 10%)  [CYAN] ✓
```

This portfolio is nearing max drawdown (amber warning) but has healthy cash reserves.

<!-- DIAGRAM: Limit utilization bars with color thresholds (70%, 90%) -->

## Circuit Breakers

Circuit breakers automatically halt trading when dangerous conditions are detected:

### Status Indicator (top right)
- **All Clear** (green check) — No breakers tripped, trading allowed
- **Breaker Tripped** (red X) — At least one breaker is active, trading halted

### Breaker Cards

Each breaker shows:
- **Icon**: Green check (inactive) or red X (tripped)
- **Name**: Breaker type (e.g., "VIX Spike", "Stale Data")
- **Reason**: Brief explanation of status

#### 1. VIX Spike
**Triggers when**: [VIX](../../glossary.md#vix) (volatility index) exceeds 35
**Why**: Extreme market volatility increases risk of large losses
**Action**: Trading halts until VIX drops below 35

#### 2. Stale Data
**Triggers when**: Market data hasn't updated in 15+ minutes
**Why**: Stale prices lead to bad decisions (can't trust signals)
**Action**: Trading halts until fresh data arrives

#### 3. Reconciliation Mismatch
**Triggers when**: System's position records don't match broker's records
**Why**: Accounting errors can cause duplicate trades or missed exits
**Action**: Trading halts until positions are reconciled (manual intervention required)

#### 4. Dead Man Switch
**Triggers when**: Backend hasn't received a heartbeat in 10+ minutes
**Why**: System may have crashed or lost broker connection
**Action**: Trading halts until backend reconnects

### When Breakers Trip

1. **System immediately cancels** all open orders
2. **No new orders** can be submitted
3. **Dashboard shows warning** (red banner at top of all pages)
4. **Alert notifications** sent (Slack/Telegram if configured)
5. **Manual review required** to understand the cause

**Resetting breakers**:
- Most breakers **auto-reset** when conditions normalize (e.g., VIX drops, data refreshes)
- **Reconciliation breaker** requires manual intervention (check logs, fix accounting)
- **Dead man switch** resets when backend reconnects

<!-- DIAGRAM: Circuit breaker state machine (inactive → tripped → auto-reset/manual-reset) -->

## Kill Switch

The kill switch is your **emergency stop button**. It instantly:
1. Cancels all open orders
2. Halts all trading activity
3. Prevents new orders from being submitted
4. Requires manual deactivation to resume

### When to Use the Kill Switch

- **Market crash**: Avoid further losses during extreme volatility
- **Strategy gone rogue**: System is making irrational trades
- **Broker issues**: IBKR connection is unreliable or orders aren't filling correctly
- **Personal emergency**: You need to step away and ensure no trades happen
- **End of trading day**: Prevent overnight positions if you prefer not to hold

### How to Activate

1. Click the **"Kill Switch"** button on the Risk page
2. A modal appears with a confirmation prompt
3. Type **"KILL"** (all caps) in the text field
4. Click **"Activate Kill Switch"**

The modal has a red pulsing background to emphasize the severity of the action.

### Confirmation Modal

```
┌─────────────────────────────────────────┐
│ 🛑 Activate Kill Switch                 │
│ This will cancel all open orders and    │
│ halt all trading.                       │
│                                         │
│ ⚠️  Warning:                            │
│ All open orders will be cancelled       │
│ immediately. No new trades will be      │
│ submitted until the kill switch is      │
│ deactivated and the cooldown period     │
│ has elapsed.                            │
│                                         │
│ Type "KILL" to confirm:                 │
│ [________________]                      │
│                                         │
│ [Cancel]  [Activate Kill Switch]       │
└─────────────────────────────────────────┘
```

### How to Deactivate

1. Click the **"Resume Trading"** button (appears when kill switch is active)
2. A modal appears (similar to activation)
3. Type **"RESUME"** (all caps) in the text field
4. Click **"Resume Trading"**

**Cooldown period**: After deactivating, the system waits 60 seconds before allowing new trades. This prevents accidental reactivation during volatile conditions.

### Kill Switch Status

When active:
- **Red banner** appears at top of all dashboard pages: "⚠️ KILL SWITCH ACTIVE — Trading halted"
- **All order submissions** are rejected with an error message
- **Status persists** across backend restarts (stored in database)

<!-- DIAGRAM: Kill switch activation flow (button → modal → confirmation → active state) -->

## When to Use This Page

Check the Risk page:
- **Daily**: Review PDT count and drawdown status
- **Before trading**: Ensure no circuit breakers are tripped
- **After large losses**: Check if you're approaching daily loss limit
- **In market volatility**: Monitor VIX breaker (check if it's close to triggering)
- **Emergency**: Activate kill switch if conditions warrant

## Key Metrics to Watch

### PDT Count
- **0-1 used**: Safe to day trade if needed
- **2 used**: Be cautious, save last trade for genuine opportunities
- **3 used**: Cannot day trade; only swing trades allowed

### Drawdown
- **<5%**: Normal volatility
- **5-8%**: Monitor closely, review underperforming positions
- **8-10%**: Danger zone, consider reducing risk
- **>10%**: Circuit breaker trips, manual intervention required

### Daily Loss
- **<1%**: Minor fluctuation
- **1-2%**: Notable loss, review trades
- **2-3%**: Approaching limit, avoid new positions
- **>3%**: Circuit breaker trips, trading halted

### Cash Reserve
- **>15%**: Healthy buffer
- **10-15%**: Minimum acceptable
- **<10%**: Limit violation, cannot open new positions until you sell something

## Related Pages

- **[Portfolio](portfolio.md)**: See how positions contribute to drawdown
- **[Strategies](strategies.md)**: Identify which strategies are causing losses
- **[Trades](trades.md)**: Review recent trades to understand loss sources

## Troubleshooting

**Q: PDT counter shows 3/3 but I haven't day traded**
A: Check trade history for same-day buy/sell pairs. System may have counted a trade you didn't notice. Review logs for audit trail.

**Q: Circuit breaker won't reset**
A: Check backend logs for underlying issue. For reconciliation breaker, manually verify positions in IBKR TWS match system records.

**Q: Kill switch activated accidentally**
A: Deactivate it by typing "RESUME". There's a 60-second cooldown before trading resumes.

**Q: Drawdown limit seems too strict**
A: Limits are configurable in `config/risk_limits.yaml`. Default -10% is conservative; adjust only if you understand the risks.

## Best Practices

1. **Never disable PDT guard** — The penalties are severe (90-day day trading ban)
2. **Respect drawdown limits** — Deep drawdowns are hard to recover from
3. **Use kill switch liberally** — Better safe than sorry; reactivating is easy
4. **Monitor VIX during volatility** — If VIX is near 35, consider reducing exposure preemptively
5. **Keep cash reserves** — 10-15% minimum ensures you can act on opportunities and meet margin requirements
6. **Review breaker logs** — Understand *why* breakers trip to prevent recurrence
