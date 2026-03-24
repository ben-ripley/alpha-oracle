---
title: Kill Switch
nav_order: 3
parent: Operations
---

# Kill Switch

The kill switch is your emergency "stop everything" button. It immediately halts all trading activity and cancels pending orders.

## What It Does

When activated:

1. **Stops all trading:** No new orders are accepted
2. **Cancels pending orders:** All open orders are cancelled with the broker
3. **Preserves positions:** Existing positions remain open (not liquidated)
4. **Logs the event:** Activation is recorded in Redis and database for audit
5. **Broadcasts alert:** WebSocket alert sent to dashboard, notifications to configured channels

The system remains in "kill switch active" state until you explicitly deactivate it.

## When to Use It

Activate the kill switch when:

- **Market crash:** Flash crash or extreme volatility requires immediate halt
- **System malfunction:** Unexpected behavior, runaway orders, bugs
- **Emergency situation:** Any situation requiring immediate trading cessation
- **Planned maintenance:** Before shutting down the system or IBKR connection
- **Loss of confidence:** You lose trust in the system's decisions

**Do not hesitate to use it.** The kill switch is designed for emergencies. It's better to halt and investigate than to let a bad situation continue.

## How to Activate

### From Dashboard

1. Navigate to the **Risk** page
2. Click the red **Kill Switch** button in the top-right corner
3. A confirmation modal appears
4. Type `KILL` (uppercase) in the text box
5. Click **Activate Kill Switch**

The modal requires typed confirmation to prevent accidental activation.

<!-- DIAGRAM: Screenshot of Kill Switch button and confirmation modal -->

### From HTTP API

```bash
curl -X POST http://localhost:8000/api/risk/kill-switch \
  -H "Content-Type: application/json" \
  -d '{"action": "activate", "reason": "Market crash"}'
```

**Response:**
```json
{
  "status": "kill_switch_activated",
  "reason": "Market crash",
  "activated_at": "2026-03-12T15:34:22Z"
}
```

## What Happens After Activation

Once activated:

- ❌ **No new orders:** All order generation stops
- ❌ **Signal processing:** Strategies continue generating signals but orders are not created
- ✅ **Data collection:** Market data feeds continue running
- ✅ **Position tracking:** Portfolio positions continue updating with real-time prices
- ✅ **Dashboard:** All pages remain functional, just no trading

The system is "frozen" in terms of trading but continues monitoring the market.

## How to Deactivate (Resume Trading)

### Cooldown Period

After activating the kill switch, you **must wait 60 minutes** before resuming trading. This cooldown prevents:
- Panic flip-flopping (activate → deactivate → activate repeatedly)
- Hasty resumption without investigating the issue
- Accidental reactivation during debugging

If you try to deactivate before the cooldown expires, you'll see:
```
Kill switch cooldown active. 37 minutes remaining (cooldown: 60 minutes).
```

### From Dashboard

1. Wait for the 60-minute cooldown to expire
2. Navigate to the **Risk** page
3. Click the **Resume Trading** button (appears when kill switch is active)
4. Type `RESUME` (uppercase) in the text box
5. Click **Confirm Resume**

### From HTTP API

```bash
curl -X POST http://localhost:8000/api/risk/kill-switch \
  -H "Content-Type: application/json" \
  -d '{"action": "deactivate"}'
```

**Response (if cooldown active):**
```json
{
  "error": "Kill switch cooldown active. 37 minutes remaining."
}
```

**Response (after cooldown):**
```json
{
  "status": "kill_switch_deactivated",
  "deactivated_at": "2026-03-12T16:34:22Z"
}
```

## Audit Log

All kill switch events are logged:

- **Activation:** Who, when, why
- **Deactivation:** When trading resumed
- **Cooldown violations:** Attempts to deactivate before cooldown expired

View the audit log:
- **Dashboard:** Risk page → Kill Switch section → View History
- **HTTP API:** `GET /api/risk/kill-switch/history`
- **Redis:** `risk:kill_switch:log` key

Example log entry:
```json
{
  "action": "activate",
  "reason": "Market crash detected, VIX spike to 47",
  "timestamp": "2026-03-12T15:34:22Z"
}
```

## Configuration

Kill switch settings in `config/risk_limits.yaml`:

```yaml
kill_switch:
  http_enabled: true           # Enable HTTP API endpoint
  telegram_enabled: false      # Enable Telegram bot commands (optional)
  cooldown_minutes: 60         # Cooldown period after activation
```

To change cooldown period:
```yaml
kill_switch:
  cooldown_minutes: 30   # Reduce to 30 minutes (not recommended)
```

Restart the backend after changing settings.

## Best Practices

1. **Keep it accessible:** Bookmark the Risk page, know where the button is
2. **Don't hesitate:** If in doubt, hit the kill switch first, investigate later
3. **Investigate before resuming:** Use the cooldown period to understand what went wrong
4. **Test it:** Activate the kill switch in PAPER_ONLY mode to verify it works
5. **Monitor logs:** After resuming, watch the dashboard closely for abnormal behavior

## Common Scenarios

### Scenario 1: Market Flash Crash
- **Symptom:** Extreme price movements, VIX spike, widespread losses
- **Action:** Activate kill switch immediately
- **Investigation:** Check market news, assess portfolio damage, adjust risk limits
- **Resume:** After market stabilizes and you understand the situation

### Scenario 2: System Bug
- **Symptom:** Orders executing incorrectly, unexpected signals, duplicate trades
- **Action:** Activate kill switch immediately
- **Investigation:** Check logs (`logs/backend.log`), identify bug, fix code
- **Resume:** After verifying fix in PAPER_ONLY mode

### Scenario 3: IBKR Connection Lost
- **Symptom:** "Connection refused" errors, stale data alert
- **Action:** Activate kill switch (prevents trading on stale data)
- **Investigation:** Restart IBKR Gateway/TWS, verify connection
- **Resume:** After connection is stable and positions reconciled

### Scenario 4: Planned Maintenance
- **Symptom:** You need to restart the system or upgrade IBKR
- **Action:** Activate kill switch before shutting down
- **Investigation:** Perform maintenance
- **Resume:** After system is back online and health checks pass

## Related Topics

- [Risk Management](../concepts/risk-management.md) — Layer 4 (kill switch) in the 4-layer system
- [Autonomy Modes](../concepts/autonomy-modes.md) — Kill switch works in all modes
- [Circuit Breakers](../concepts/risk-management.md#layer-3-circuit-breakers) — Automatic halts (different from manual kill switch)
- [Monitoring & Alerts](./monitoring-alerts.md) — How you're notified of kill switch events
