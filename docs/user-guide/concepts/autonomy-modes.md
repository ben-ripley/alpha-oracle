---
title: Autonomy Modes
nav_order: 3
parent: Concepts
---

# Autonomy Modes

The system operates in one of four autonomy modes, controlling how much independence the trading system has when executing trades. You start in the safest mode and can gradually progress as you gain confidence.

## The Four Modes

### PAPER_ONLY (Default)
**Simulated trades only, no real money.**

This is the default mode when you first start the system. All trades are executed against simulated market data, not your actual brokerage account. Use this mode to:
- Test the system's behavior without financial risk
- Understand how strategies generate signals
- Verify risk limits are working correctly
- Build confidence in the system

No real orders reach your broker. All positions and P&L are simulated in memory.

### MANUAL_APPROVAL
**System generates signals, but you approve each trade.**

The system analyzes the market and generates buy/sell signals, but every order requires your explicit approval before execution. Orders appear on the Trades page with status "PENDING APPROVAL."

Use this mode to:
- See what the system wants to trade and why
- Learn how strategies make decisions
- Build trust before going autonomous
- Maintain full control while delegating research

You review each order's details (symbol, quantity, price, strategy, signal strength) and decide whether to approve or reject it. See [Trade Approvals](../operations/trade-approvals.md) for the approval workflow.

### BOUNDED_AUTONOMOUS
**System executes within strict risk limits.**

The system operates independently but is constrained by the [risk limits](../configuration/risk-limits.md) you configure. This includes:
- Position size limits (max 5% per position, 25% per sector)
- Portfolio drawdown limits (10% max drawdown, 3% daily loss)
- [PDT rule](../glossary.md#pdt) enforcement (max 3 day trades per 5 business days)
- Circuit breakers (VIX threshold, stale data detection)

Orders are executed automatically without your approval, but the system cannot violate any configured limits. If an order would exceed a limit, it's either reduced in size or rejected entirely.

**Recommended after:** at least 2 weeks of MANUAL_APPROVAL mode with satisfactory results.

### FULL_AUTONOMOUS
**System operates with full discretion.**

The system has maximum independence. Risk limits still apply, but the system can make strategic decisions about portfolio construction, rebalancing, and risk management without consulting you.

**Recommended after:** at least 1 month of BOUNDED_AUTONOMOUS mode with consistent performance and no violations.

⚠️ **Use with extreme caution.** This mode is suitable only for experienced users who have thoroughly tested the system and understand its behavior.

## Changing Modes

Edit the `autonomy_mode` field in `config/risk_limits.yaml`:

```yaml
autonomy_mode: PAPER_ONLY  # or MANUAL_APPROVAL, BOUNDED_AUTONOMOUS, FULL_AUTONOMOUS
```

Restart the backend for changes to take effect:

```bash
./scripts/restart-backend.sh
```

## Recommended Progression

1. **Start:** PAPER_ONLY (1-2 weeks)
   - Run backtest on historical data
   - Verify strategies meet performance thresholds
   - Confirm risk limits are appropriate for your account size

2. **Progress:** MANUAL_APPROVAL (2-4 weeks)
   - Review and approve every trade
   - Understand why the system generates each signal
   - Verify execution quality and slippage

3. **Advance:** BOUNDED_AUTONOMOUS (1-3 months)
   - System trades autonomously within limits
   - Monitor daily via dashboard
   - Adjust risk limits based on observed behavior

4. **Expert:** FULL_AUTONOMOUS (optional)
   - Only after extensive testing and consistent results
   - Regular monitoring still recommended
   - [Kill switch](../operations/kill-switch.md) available for emergencies

<!-- DIAGRAM: Progression flowchart showing the 4 modes with recommended timeframes and decision criteria -->

## Related Topics

- [Risk Management](./risk-management.md) — The 4 layers of protection
- [PDT Rule](./pdt-rule.md) — Pattern Day Trading restrictions
- [Trade Approvals](../operations/trade-approvals.md) — How to approve orders in MANUAL_APPROVAL mode
- [Kill Switch](../operations/kill-switch.md) — Emergency halt mechanism
