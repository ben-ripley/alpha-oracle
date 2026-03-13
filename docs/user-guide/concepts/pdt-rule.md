# Pattern Day Trading (PDT) Rule

The PDT rule is a FINRA regulation that limits day trading activity for accounts under $25,000. The system enforces this rule automatically to protect your account from regulatory restrictions.

## What is a Day Trade?

A **day trade** occurs when you buy AND sell the same security on the same calendar day. Both the buy and sell must happen on the same day for it to count.

**Examples:**
- ✅ Day trade: Buy AAPL at 10am, sell AAPL at 2pm same day
- ❌ Not a day trade: Buy AAPL Monday, sell AAPL Tuesday
- ❌ Not a day trade: Buy AAPL Monday, hold for a week, sell next Monday

## The Rule

**For accounts under $25,000 equity:**
- Maximum of **3 day trades** per rolling **5 business days**
- If you exceed this limit, your broker may restrict your account to closing trades only (90-day restriction)

**For accounts at or above $25,000 equity:**
- No PDT restrictions apply
- You can day trade freely

The threshold is $25,000 in total account equity (cash + positions), not just cash balance.

## How the System Protects You

The system includes a **PDT Guard** that checks every order before execution:

1. **Tracks day trades:** Records every completed day trade in Redis
2. **Counts trades:** Maintains a rolling 5-business-day window count
3. **Predicts day trades:** Analyzes whether a new order would create a day trade
4. **Rejects violations:** Blocks orders that would exceed the 3-trade limit
5. **Conservative approach:** When in doubt, rejects the order (false rejection is safer than a FINRA restriction)

All decisions are logged for audit.

## PDT Counter on Dashboard

The Risk page shows your current PDT status:
- Trades used: X / 3
- Rolling window: last 5 business days
- Days until oldest trade expires

<!-- DIAGRAM: Timeline showing rolling 5-business-day window with example day trades -->

## How Strategies Avoid Day Trades

All built-in strategies use `min_hold_days >= 2`, which means they naturally avoid day trades by design:

- **Swing Momentum:** min_hold_days = 2
- **Mean Reversion:** min_hold_days = 2
- **Value Factor:** min_hold_days = 5
- **ML Signal Strategy:** min_hold_days = 3

The system will not sell a position on the same day it was opened (unless manually overridden in MANUAL_APPROVAL mode, which the PDT guard will still block if you're at the limit).

## What Happens When You Hit the Limit?

If you've already used 3 day trades and try to place an order that would be a 4th day trade:

1. ❌ **Order is rejected** before reaching the broker
2. 📝 **Log entry created:** "PDT LIMIT REACHED" with full details
3. 🚨 **Dashboard alert:** Risk page shows PDT warning
4. ⏳ **Wait period:** You must wait until the oldest day trade expires from the 5-business-day window

**Example:**
- Monday: Day trade #1
- Tuesday: Day trade #2
- Wednesday: Day trade #3
- Thursday: ❌ Cannot day trade (already at limit)
- Friday: ❌ Cannot day trade
- Next Tuesday: ✅ Monday's trade expired, you have 1 day trade available again

## PDT-Exempt Accounts

If your account equity is >= $25,000:
- The PDT guard automatically exempts you
- You can day trade without restrictions
- The system still tracks day trades for monitoring purposes

However, if your account drops below $25,000 (e.g., due to losses), the PDT rule applies immediately.

## Best Practices

1. **Start with swing trading:** Use strategies with min_hold_days >= 2
2. **Monitor your count:** Check the Risk dashboard before trading
3. **Save day trades:** Reserve them for high-conviction opportunities
4. **Account size:** If you plan to day trade frequently, consider funding your account to $25,000+

## Configuration

PDT guard settings in `config/risk_limits.yaml`:

```yaml
pdt_guard:
  enabled: true
  max_day_trades: 3
  rolling_window_days: 5
  account_threshold: 25000.0
```

⚠️ **Do not disable the PDT guard** unless you have a PDT-exempt account or are in PAPER_ONLY mode.

## Related Topics

- [Risk Management](./risk-management.md) — The complete 4-layer risk system
- [Autonomy Modes](./autonomy-modes.md) — How the system operates
- [Trading Strategies](./strategies-explained.md) — Built-in strategies and their holding periods
