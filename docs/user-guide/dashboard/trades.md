# Trades Page

The Trades page shows trade history, pending approvals (in MANUAL_APPROVAL mode), execution quality metrics, and daily trade summary.

## Overview

This page answers:
1. **What trades happened?** — Recent trade history with P&L
2. **What trades need approval?** — Pending orders awaiting your decision (MANUAL_APPROVAL mode only)
3. **How well are trades executing?** — Fill rates, slippage, and quality metrics

## Pending Approvals (MANUAL_APPROVAL Mode Only)

When the system operates in MANUAL_APPROVAL mode, every order must be reviewed and approved before submission to the broker.

### Approval Section

If there are pending orders, a prominent amber-bordered section appears at the top:

```
⏱ PENDING APPROVALS (3)
────────────────────────────────────────────────────────────────
[BUY] AAPL  100 shares @ $182.50  MLSignalStrategy  Signal: 73%
  [Approve]  [Reject]

[SELL] MSFT  50 shares @ MKT  MeanReversionStrategy  Signal: 82%
  [Approve]  [Reject]

[BUY] GOOGL  25 shares @ $140.00  MomentumStrategy  Signal: 65%
  [Approve]  [Reject]
────────────────────────────────────────────────────────────────
```

### Order Details

Each pending order shows:
- **Side badge**: BUY (green, ↗) or SELL (red, ↘)
- **Symbol**: Stock ticker
- **Quantity**: Number of shares
- **Price**: Limit price (e.g., $182.50) or "MKT" for market orders
- **Strategy**: Which strategy generated this signal
- **Signal Strength**: Model's confidence (0-100%)

### Approval Actions

Click **Approve** to:
- Submit the order to the broker (IBKR)
- Move the order from "pending" to "submitted" status
- Begin monitoring for fill

Click **Reject** to:
- Cancel the order without submitting
- Log the rejection reason (for auditing)
- Remove from pending list

**Best practices**:
- Approve high-confidence signals (>70%) from proven strategies
- Reject signals that conflict with your market view
- Check Portfolio and Risk pages before approving to ensure limits aren't violated

<!-- DIAGRAM: Pending approval workflow (strategy generates signal → pending → user approves/rejects → broker) -->

## Trade Stats Cards

Four key metrics summarize today's trading activity:

### Today's Trades
Total number of trades executed today (both opened and closed positions).

### Today's P&L
Net profit/loss for all trades closed today.
- **Green**: Positive P&L (winning day)
- **Red**: Negative P&L (losing day)
- **Excludes**: Unrealized P&L from open positions (see Portfolio page)

### Fill Rate
Percentage of submitted orders that were filled by the broker:
```
Fill Rate = (Filled Orders / Total Submitted Orders) × 100%
```

- **100%**: All orders filled (excellent)
- **90-100%**: Most orders filled (good)
- **<90%**: Many orders rejected or cancelled (investigate)

**Common reasons for unfilled orders**:
- Limit price too aggressive (not reached)
- Low liquidity (no counterparty)
- Market closed
- Broker rejected (insufficient funds, margin)

### Total Orders
Total orders submitted in the last 30 days (includes pending, filled, cancelled).

<!-- DIAGRAM: Trade stats cards with color coding and visual icons -->

## Trade History Table

The main table lists all trades with detailed metrics:

### Filter Tabs

Three filter options:
- **All**: Show all trades (open + closed)
- **Open**: Only positions still held
- **Closed**: Only exited positions (realized P&L)

Click a tab to filter. The active tab is highlighted in cyan.

### Table Columns

| Column | Description |
|--------|-------------|
| **Side** | BUY (green, ↗) or SELL (red, ↘) pill |
| **Symbol** | Stock ticker |
| **Qty** | Number of shares |
| **Entry** | Average entry price (for multi-fill orders) |
| **Exit** | Exit price (or "—" if still open) |
| **P&L** | Realized profit/loss in dollars |
| **P&L %** | Percentage gain/loss (color-coded pill) |
| **Hold** | Hold duration in days (e.g., "3.2d") |
| **Strategy** | Which strategy opened this position |
| **Status** | "Open" (cyan, pulsing) or "Closed" (green check) |

### P&L Calculation

For closed trades:
```
P&L = (Exit Price - Entry Price) × Quantity

Example:
Entry: $100.00 × 50 shares = $5,000
Exit:  $105.00 × 50 shares = $5,250
P&L:   $250 (+5.0%)
```

For open trades:
- P&L shows "—" (unrealized P&L is on Portfolio page)
- Exit price shows "—"
- Status shows "Open" with pulsing indicator

### Color Coding

- **Green P&L**: Profitable trade
- **Red P&L**: Losing trade
- **Bright white symbol**: High visibility
- **Dimmed strategy tag**: Less critical info

### Sorting

Click column headers to sort (if implemented):
- **Symbol**: Alphabetical
- **P&L**: Largest gain → largest loss
- **Hold**: Longest → shortest duration
- **Entry**: Most recent → oldest

### Row Hover

Hovering over a row highlights it with a subtle background color for easier reading.

<!-- DIAGRAM: Trade history table with annotated columns and color coding -->

## Order Types

The system uses three order types:

### 1. Market Order
- **Price**: Current market price (shown as "MKT")
- **Execution**: Immediate fill (usually)
- **Risk**: Price slippage on low-liquidity stocks
- **Best for**: High-liquidity stocks (AAPL, MSFT) where speed matters

### 2. Limit Order
- **Price**: User-specified limit (e.g., $182.50)
- **Execution**: Only fills at limit price or better
- **Risk**: May not fill if market moves away
- **Best for**: Low-liquidity stocks or when controlling entry price is critical

### 3. TWAP (Time-Weighted Average Price)
- **Price**: Broken into smaller orders over time
- **Execution**: Reduces market impact for large orders
- **Risk**: Partial fills if market moves significantly
- **Best for**: Large positions in mid-cap stocks

### Smart Order Router

The system automatically selects the order type based on:
- **ADV (Average Daily Volume)**: Higher volume → market orders
- **Spread**: Tight spread → market orders, wide spread → limit orders
- **Urgency**: Exit signals → market orders, entry signals → limit orders

Users don't need to choose order types manually; the router optimizes for best execution.

<!-- DIAGRAM: Order type decision tree (ADV, spread, urgency → market/limit/TWAP) -->

## Execution Quality Metrics

The system tracks order execution quality:

### Fill Rate
Percentage of orders filled (see Trade Stats Cards above).

### Average Slippage
Difference between expected price and actual fill price:
```
Slippage = |Actual Fill Price - Reference Price| / Reference Price

Example:
Expected: $100.00 (midpoint of bid/ask)
Filled:   $100.15
Slippage: $0.15 (0.15% = 15 basis points)
```

- **Low slippage** (<10 bps): Excellent execution
- **Moderate slippage** (10-30 bps): Acceptable
- **High slippage** (>30 bps): Poor liquidity or aggressive orders

### Time to Fill
Average time from order submission to fill:
- **<1 second**: Market orders on high-liquidity stocks
- **1-10 seconds**: Limit orders near market price
- **>60 seconds**: Limit orders far from market, low liquidity

### Partial Fills
Percentage of orders filled in multiple chunks:
- **0%**: All orders fill completely (ideal)
- **<10%**: Occasional partial fills (acceptable)
- **>20%**: Frequent partial fills (investigate liquidity issues)

**Note**: Execution quality metrics are displayed in the Trade Stats Cards or a dedicated section (if implemented).

<!-- DIAGRAM: Execution quality metrics with thresholds (good, acceptable, poor) -->

## Manual Approval Workflow

In MANUAL_APPROVAL mode, trades follow this flow:

1. **Strategy generates signal** — Based on technical/fundamental indicators
2. **Pre-trade checks** — System validates risk limits, PDT rule, position sizing
3. **Order created** — Appears in "Pending Approvals" section
4. **User reviews order** — Checks signal strength, strategy, price
5. **User approves** — Order submitted to broker
6. **Broker fills order** — Order executed, appears in Trade History
7. **Position opened** — Appears on Portfolio page

**Rejection flow**:
- User clicks "Reject"
- Order is cancelled (never submitted)
- Signal is logged as "rejected by user"

**Timeout**:
- Pending orders expire after 15 minutes (configurable)
- Expired orders are auto-rejected to prevent stale signals

<!-- DIAGRAM: Manual approval workflow with decision points -->

## When to Use This Page

Check the Trades page:
- **In MANUAL_APPROVAL mode**: Multiple times per day to approve/reject orders
- **After market close**: Review today's trades and P&L
- **Weekly**: Analyze trade performance by strategy (which strategies are profitable?)
- **After losses**: Investigate losing trades (entry price too high? held too long?)
- **Before rebalancing**: Check hold duration (avoid day trades, respect PDT rule)

## Key Metrics to Watch

### Today's P&L
- **Positive**: Good day, strategies are working
- **Negative**: Review losing trades, identify patterns

### Fill Rate
- **>95%**: Excellent, orders are executing smoothly
- **<90%**: Investigate order rejections or liquidity issues

### Pending Approvals (MANUAL_APPROVAL mode)
- **0 pending**: No action needed
- **3+ pending**: Review and approve/reject promptly (don't let orders expire)

### Hold Duration
- **<2 days**: Possible PDT violation (check Risk page)
- **2-5 days**: Swing trades (normal for this system)
- **>10 days**: Position trades (ensure exit signals aren't being missed)

### P&L by Strategy
Look for patterns:
- **MLSignalStrategy** consistently profitable → trust it more
- **MeanReversionStrategy** losing money → consider disabling or retraining
- **MomentumStrategy** high win rate but small gains → increase position sizes?

## Related Pages

- **[Portfolio](portfolio.md)**: See open positions (trades not yet exited)
- **[Strategies](strategies.md)**: Understand which strategies generated these trades
- **[Risk](risk.md)**: Check PDT count and ensure trades didn't violate limits

## Troubleshooting

**Q: Order stuck in "Pending" status**
A: Check backend logs for broker connection issues. Verify IBKR Gateway is running. May need to restart backend.

**Q: Fill rate is low (<80%)**
A: Orders may be using limit prices too far from market. Check smart router settings. Consider using market orders for high-liquidity stocks.

**Q: Trade shows wrong P&L**
A: Verify entry/exit prices match broker's records. Run reconciliation job: `POST /api/system/scheduler/trigger/reconciliation`

**Q: Can't approve pending orders**
A: Check that you're not at PDT limit (3/3). Verify risk limits haven't been exceeded. Check browser console for errors.

**Q: Trade history is empty**
A: Run seed script to load demo data: `python scripts/seed_demo_data.py` (if in PAPER_ONLY mode). In live mode, wait for strategies to generate signals.

## Best Practices

1. **Approve high-confidence signals** — >70% confidence has proven reliability
2. **Reject low-confidence signals** — <50% is essentially a coin flip
3. **Monitor fill rates** — Low fill rates indicate strategy or routing issues
4. **Review losing trades** — Learn from mistakes (entry too aggressive? exit too late?)
5. **Check hold duration** — Ensure no day trades (PDT violations)
6. **Track P&L by strategy** — Disable underperforming strategies
7. **Set approval reminders** — Don't let pending orders expire (15-minute timeout)
