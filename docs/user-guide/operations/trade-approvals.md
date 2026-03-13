# Trade Approvals

In [MANUAL_APPROVAL mode](../concepts/autonomy-modes.md#manual_approval), the system generates buy/sell signals and creates proposed orders, but every order requires your explicit approval before execution. This gives you full control while delegating research and analysis to the system.

## How It Works

1. **System analyzes market:** Strategies run on schedule and generate signals based on technical indicators, fundamentals, or ML predictions
2. **Orders proposed:** System creates orders for top signals with status "PENDING APPROVAL"
3. **You review:** Orders appear on the Trades page with full details
4. **You decide:** Approve or reject each order
5. **Execution:** Approved orders are submitted to the broker; rejected orders are logged but not executed

## Viewing Pending Orders

Navigate to the **Trades** page in the dashboard.

Pending orders are displayed at the top of the page with:
- ⏳ **Status badge:** "PENDING APPROVAL" in yellow/amber
- 📊 **Order details:** Symbol, side (BUY/SELL), quantity, price, order type
- 🎯 **Strategy info:** Which strategy generated the signal, signal strength (0.0-1.0)
- 💡 **Signal metadata:** Key indicators or features that drove the decision
- ⏰ **Created timestamp:** When the order was generated

**Example pending order:**
```
Symbol: AAPL
Side: BUY
Quantity: 15 shares
Order Type: LIMIT
Limit Price: $178.45
Strategy: ml_xgboost_signal
Signal Strength: 0.72
Features: RSI=42, MA_cross=bullish, earnings_growth=12%
Created: 2026-03-12 09:34:22 ET
```

<!-- DIAGRAM: Trades page screenshot showing pending orders with Approve/Reject buttons -->

## Approving an Order

To approve an order:

1. Review the order details carefully
2. Click the green **Approve** button next to the order
3. The order status changes to "SUBMITTED"
4. The order is sent to the broker for execution
5. You'll see real-time updates as the order fills

**What happens after approval:**
- Order passes through [risk checks](../concepts/risk-management.md) (position limits, portfolio limits, [PDT guard](../concepts/pdt-rule.md), circuit breakers)
- If risk checks pass, order is sent to broker via IBKR API
- Order executes at market or limit price (depending on order type)
- Position appears on Portfolio page once filled
- Trade record created for performance tracking

**If risk checks fail:**
- Order is rejected with reason (e.g., "Would exceed 5% position limit")
- Status changes to "REJECTED"
- You see the rejection reason on the Trades page
- No order is sent to the broker

## Rejecting an Order

To reject an order:

1. Click the red **Reject** button next to the order
2. Optionally, add a rejection reason (logged for future analysis)
3. The order status changes to "REJECTED"
4. The order is **not** sent to the broker

**Why reject orders:**
- You disagree with the signal (e.g., news not captured by the system)
- You want to reduce exposure to a particular sector
- Market conditions changed since signal was generated
- You're preserving capital for a higher-conviction opportunity

Rejected orders are logged but do not affect your account.

## Approval Best Practices

### 1. Review Signal Strength
- **High confidence (≥0.70):** Strong signals, consider approving
- **Medium confidence (0.55-0.69):** Moderate signals, use judgment
- **Low confidence (<0.55):** System shouldn't generate these, but reject if you see them

### 2. Check Signal Metadata
For ML signals, review top features:
- Do the features make sense for the current market environment?
- Are there contradictory indicators (e.g., RSI overbought but system says BUY)?

For rule-based strategies:
- Swing Momentum: Check MA crossover and RSI values
- Mean Reversion: Verify Bollinger Band position and RSI oversold
- Value Factor: Review PE/PB/EV-EBITDA ratios

### 3. Cross-Reference Market News
- Check recent news for the stock (earnings, FDA approvals, lawsuits, etc.)
- System may not have the latest news, especially for breaking events

### 4. Monitor Position Limits
- Review Portfolio page to see current positions and sector exposure
- Ensure new order won't over-concentrate your portfolio
- System enforces limits, but you may want tighter personal limits

### 5. Check Market Conditions
- High VIX (>25): Consider reducing position sizes or rejecting high-risk orders
- Market close approaching: Be cautious of orders that may not fill before close
- Stale data warnings: Reject orders if data feed is interrupted

## Approval Workflow Tips

### Batch Review
- Review all pending orders once or twice per day (morning and mid-day)
- Don't feel pressured to approve immediately—pending orders remain until you act
- Sort by signal strength to prioritize highest-conviction trades

### Approval Rate
- Don't approve every order—be selective
- A 50-70% approval rate is reasonable (rejecting 30-50% shows critical thinking)
- If you're approving >90%, consider moving to [BOUNDED_AUTONOMOUS mode](../concepts/autonomy-modes.md#bounded_autonomous)

### Tracking Performance
- Compare performance of approved vs. rejected orders over time
- If rejected orders would have been profitable, adjust your criteria
- If approved orders are underperforming, tighten approval standards

## Order Expiration

Pending orders **do not expire automatically**. They remain pending until you approve or reject them.

**Implications:**
- Old orders may become stale (market conditions changed)
- You should review pending orders at least daily
- System may generate duplicate signals if you don't act on pending orders

**Recommended:** Set a personal policy (e.g., "reject all orders older than 4 hours").

## Transitioning to Autonomous Trading

MANUAL_APPROVAL mode is ideal for:
- **Learning:** Understand how strategies generate signals
- **Building trust:** Verify the system makes good decisions before going autonomous
- **Testing:** Try strategies in live market conditions with human oversight

**When to transition to BOUNDED_AUTONOMOUS:**
- You've approved 2+ weeks of trades with satisfactory results
- Your approval rate is >70% (you agree with most signals)
- You're confident in the system's decision-making
- You understand what drives signals and when to override

See [Autonomy Modes](../concepts/autonomy-modes.md) for the recommended progression path.

## Configuration

Set autonomy mode in `config/risk_limits.yaml`:

```yaml
autonomy_mode: MANUAL_APPROVAL
```

Restart the backend:
```bash
./scripts/restart-backend.sh
```

## HTTP API (Advanced)

Approve/reject orders programmatically:

**Approve an order:**
```bash
curl -X POST http://localhost:8000/api/trades/{order_id}/approve
```

**Reject an order:**
```bash
curl -X POST http://localhost:8000/api/trades/{order_id}/reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Disagree with signal"}'
```

## Related Topics

- [Autonomy Modes](../concepts/autonomy-modes.md) — The four autonomy levels
- [Risk Management](../concepts/risk-management.md) — Risk checks that orders pass through
- [Trading Strategies](../concepts/strategies-explained.md) — How strategies generate signals
- [ML Signals](../concepts/ml-signals.md) — Understanding ML signal metadata
