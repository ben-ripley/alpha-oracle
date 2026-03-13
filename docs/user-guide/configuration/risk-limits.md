# Risk Limits Reference

Risk limits are configured in `config/risk_limits.yaml`. These settings control the four layers of [risk management](../concepts/risk-management.md) that protect your capital.

## File Location

`config/risk_limits.yaml`

Restart the backend after making changes:

```bash
./scripts/restart-backend.sh
```

## Settings

### autonomy_mode

Controls system autonomy level. See [Autonomy Modes](../concepts/autonomy-modes.md).

```yaml
autonomy_mode: PAPER_ONLY  # PAPER_ONLY | MANUAL_APPROVAL | BOUNDED_AUTONOMOUS | FULL_AUTONOMOUS
```

**Options:**
- `PAPER_ONLY`: Simulated trades only, no real money
- `MANUAL_APPROVAL`: System generates signals, you approve each trade
- `BOUNDED_AUTONOMOUS`: System executes within strict limits
- `FULL_AUTONOMOUS`: System operates with full discretion

**Default:** `PAPER_ONLY`

### position_limits

Layer 1 risk controls for individual positions.

```yaml
position_limits:
  max_position_pct: 5.0        # Max 5% of portfolio per position
  max_sector_pct: 25.0         # Max 25% per sector
  stop_loss_pct: 2.0           # 2% stop-loss per position
  min_price: 5.0               # No penny stocks (< $5)
  no_leverage: true            # No margin/leverage
```

**Settings:**

- **max_position_pct** (default: `5.0`): Maximum percentage of portfolio value in a single position. A $10,000 portfolio can hold max $500 in any one stock.

- **max_sector_pct** (default: `25.0`): Maximum percentage of portfolio value in a single sector. Prevents sector concentration risk.

- **stop_loss_pct** (default: `2.0`): Automatic stop-loss percentage per position. If a position drops 2% from entry price, it's automatically sold.

- **min_price** (default: `5.0`): Minimum stock price in dollars. Stocks below this price are filtered out (no penny stocks).

- **no_leverage** (default: `true`): Disables margin and leverage. Set to `false` to enable margin trading (not recommended).

### portfolio_limits

Layer 2 risk controls for overall portfolio health.

```yaml
portfolio_limits:
  max_drawdown_pct: 10.0       # Halt trading if drawdown exceeds 10%
  max_daily_loss_pct: 3.0      # Max 3% daily loss
  max_positions: 20            # Max 20 concurrent positions
  max_daily_trades: 50         # Max 50 trades per day
  min_cash_reserve_pct: 10.0   # Keep 10% in cash
```

**Settings:**

- **max_drawdown_pct** (default: `10.0`): Maximum drawdown from peak equity. If your account drops 10% from its highest value, all trading halts until you manually restart.

- **max_daily_loss_pct** (default: `3.0`): Maximum loss in a single trading day. If you lose 3% of portfolio value in one day, trading halts until the next day.

- **max_positions** (default: `20`): Maximum number of concurrent open positions. Limits complexity and ensures diversification.

- **max_daily_trades** (default: `50`): Maximum number of trades per day. Prevents runaway trading and excessive transaction costs.

- **min_cash_reserve_pct** (default: `10.0`): Minimum percentage of portfolio kept in cash. Ensures liquidity for opportunities and withdrawals.

### pdt_guard

Layer 1 component: [Pattern Day Trading](../concepts/pdt-rule.md) rule enforcement.

```yaml
pdt_guard:
  enabled: true
  max_day_trades: 3            # Max 3 day trades per 5 business days (FINRA PDT rule)
  rolling_window_days: 5       # Rolling 5 business day window
  account_threshold: 25000.0   # PDT rule applies under $25K
```

**Settings:**

- **enabled** (default: `true`): Enable/disable PDT guard. ⚠️ **Do not disable** unless you have a PDT-exempt account (≥$25K equity) or are in PAPER_ONLY mode.

- **max_day_trades** (default: `3`): Maximum day trades per rolling window (FINRA regulation).

- **rolling_window_days** (default: `5`): Rolling window in business days (FINRA regulation).

- **account_threshold** (default: `25000.0`): Account equity threshold in dollars. Accounts below this are subject to PDT restrictions.

### circuit_breakers

Layer 3 risk controls for abnormal market or system conditions.

```yaml
circuit_breakers:
  vix_threshold: 35.0          # Halt trading if VIX > 35
  stale_data_seconds: 300      # Alert if data older than 5 minutes
  reconciliation_interval_seconds: 300  # Check positions every 5 minutes
  max_reconciliation_drift_pct: 1.0    # Alert if positions drift > 1%
  dead_man_switch_hours: 48    # Require operator heartbeat every 48 hours
```

**Settings:**

- **vix_threshold** (default: `35.0`): VIX level that triggers trading halt. VIX >35 indicates extreme market volatility (panic/crash conditions).

- **stale_data_seconds** (default: `300`): Maximum age of price data in seconds. If data is older than 5 minutes, trading pauses (detects feed interruptions).

- **reconciliation_interval_seconds** (default: `300`): How often to reconcile positions with broker (every 5 minutes).

- **max_reconciliation_drift_pct** (default: `1.0`): Maximum allowed drift between system's position records and broker's actual positions. Alerts if drift exceeds 1%.

- **dead_man_switch_hours** (default: `48`): Maximum time without operator check-in. If no human oversight for 48 hours, trading halts automatically.

### kill_switch

Layer 4: Emergency manual override settings.

```yaml
kill_switch:
  http_enabled: true
  telegram_enabled: false
  cooldown_minutes: 60         # After kill switch, wait 60 min before restart
```

**Settings:**

- **http_enabled** (default: `true`): Enable HTTP API endpoint for kill switch (`POST /api/risk/kill-switch`).

- **telegram_enabled** (default: `false`): Enable Telegram bot commands for kill switch (requires Telegram bot setup).

- **cooldown_minutes** (default: `60`): Cooldown period after kill switch activation. After activating kill switch, you must wait 60 minutes before resuming trading (prevents panic flip-flopping).

## Environment Variable Overrides

Risk limits can be overridden using environment variables:

```bash
# Change autonomy mode
export SA_RISK__AUTONOMY_MODE=MANUAL_APPROVAL

# Adjust position limits
export SA_RISK__POSITION_LIMITS__MAX_POSITION_PCT=3.0

# Adjust PDT threshold
export SA_RISK__PDT_GUARD__ACCOUNT_THRESHOLD=30000.0
```

Format: `SA_RISK__<section>__<key>=value`

## Conservative Defaults

The default limits are intentionally conservative:

- **Small positions:** 5% max per position (20 positions needed for full diversification)
- **Tight stops:** 2% stop-loss per position (limits downside)
- **Low daily loss:** 3% max daily loss (prevents spiral losses)
- **Moderate drawdown:** 10% max drawdown (protects against prolonged losing streaks)

**Recommended:** Start with defaults, then gradually relax limits after gaining confidence in the system.

## Risk Limit Violations

When a limit is breached:

1. **Order rejected:** New orders that would violate limits are blocked
2. **Dashboard alert:** Risk page shows warning with violated limit
3. **Log entry:** Violation logged to `logs/backend.log`
4. **Notification:** Alert sent via configured channels (Slack/Telegram)

Some violations halt trading entirely (max drawdown, max daily loss, circuit breakers). Others just block specific orders (position size, PDT).

## Monitoring

The Risk page displays:
- Current vs. max values for all limits
- Warning indicators when approaching limits (e.g., 80% of max drawdown)
- Circuit breaker status (active/inactive)
- PDT counter (X/3 day trades used)
- Recent risk events log

## Related Topics

- [Risk Management](../concepts/risk-management.md) — Explanation of the 4 layers
- [PDT Rule](../concepts/pdt-rule.md) — Pattern Day Trading details
- [Autonomy Modes](../concepts/autonomy-modes.md) — How autonomy affects risk controls
- [Kill Switch](../operations/kill-switch.md) — Emergency halt procedure
- [Application Settings](./settings.md) — Other configuration options
