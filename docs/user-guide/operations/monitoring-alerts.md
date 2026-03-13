# Monitoring & Alerts

The system provides multiple layers of monitoring to keep you informed about trading activity, system health, and risk events. Even in [BOUNDED_AUTONOMOUS](../concepts/autonomy-modes.md#bounded_autonomous) or [FULL_AUTONOMOUS](../concepts/autonomy-modes.md#full_autonomous) mode, you should monitor the system regularly.

## Monitoring Dashboards

### 1. Stock Analysis Dashboard (Port 3000)

The main React dashboard at `http://localhost:3000`.

**Pages:**

- **Portfolio:** Real-time positions, P&L, sector exposure, equity curve
- **Strategies:** Strategy rankings, backtest results, signal history
- **Risk:** Risk limits, [PDT counter](../concepts/pdt-rule.md), circuit breakers, [kill switch](./kill-switch.md)
- **Trades:** Order history, pending approvals, execution quality metrics
- **Model Health (ML):** Feature importance, accuracy, drift detection, model versions

**Update frequency:** Real-time via WebSocket (sub-second updates for prices and orders)

**Best for:** Day-to-day trading monitoring, portfolio tracking, order review

<!-- DIAGRAM: Dashboard screenshot with labeled sections -->

### 2. Grafana Dashboards (Port 3001)

Advanced monitoring dashboards at `http://localhost:3001`.

**Default dashboards:**

- **System Health:** CPU, memory, API latency, database connections, Redis hits/misses
- **Trading Performance:** Total return, Sharpe ratio, win rate, profit factor, drawdown
- **Risk Metrics:** Position counts, sector exposure, [PDT](../concepts/pdt-rule.md) usage, circuit breaker events
- **Order Metrics:** Orders submitted, filled, cancelled, rejected; fill rates; slippage

**Update frequency:** 1-5 minute intervals (configurable)

**Best for:** Historical analysis, system performance tuning, debugging infrastructure issues

**Default credentials:**
- Username: `admin`
- Password: `admin` (change on first login)

### 3. Prometheus Metrics (Port 9090)

Raw metrics endpoint at `http://localhost:9090`.

**Available metrics:**

- `portfolio_total_equity`: Portfolio value in dollars
- `portfolio_positions_count`: Number of open positions
- `orders_submitted_total`: Counter of submitted orders
- `orders_filled_total`: Counter of filled orders
- `api_request_duration_seconds`: API endpoint latencies
- `pdt_trades_used`: Current [PDT](../concepts/pdt-rule.md) trade count

**Best for:** Custom alerting, integration with external monitoring tools, debugging

## Alert Channels

The system supports three alert channels:

### 1. Logs (Always On)

All events are logged to `logs/backend.log` with structured logging.

**Log levels:**
- `INFO`: Normal operations (orders submitted, positions updated)
- `WARNING`: Non-critical issues ([PDT](../concepts/pdt-rule.md) approaching limit, stale data detected)
- `ERROR`: Errors (API failures, database timeouts)
- `CRITICAL`: Severe issues ([kill switch](./kill-switch.md) activated, max drawdown exceeded)

**Viewing logs:**
```bash
tail -f logs/backend.log                    # Follow live
grep "CRITICAL" logs/backend.log            # Filter by level
grep "pdt" logs/backend.log                 # Filter by keyword
```

### 2. Slack (Optional)

Send alerts to a Slack channel.

**Setup:**
1. Create a Slack webhook URL (https://api.slack.com/messaging/webhooks)
2. Configure webhook in environment:
   ```bash
   export SA_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```
3. Enable Slack in `config/settings.yaml`:
   ```yaml
   notifications:
     enabled: true
     channels: [slack]
   ```
4. Restart backend: `./scripts/restart-backend.sh`

**Alert format:**
```
🚨 [CRITICAL] Kill Switch Activated
Market crash detected, VIX spike to 47
Timestamp: 2026-03-12T15:34:22Z
```

### 3. Telegram (Optional)

Send alerts to a Telegram bot.

**Setup:**
1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot)
3. Configure bot in environment:
   ```bash
   export SA_TELEGRAM_BOT_TOKEN=your_bot_token
   export SA_TELEGRAM_CHAT_ID=your_chat_id
   ```
4. Enable Telegram in `config/settings.yaml`:
   ```yaml
   notifications:
     enabled: true
     channels: [telegram]
   ```
5. Restart backend: `./scripts/restart-backend.sh`

## Alert Conditions

The system sends alerts for these events:

### Critical Alerts (Immediate Action Required)

- **Kill switch activated:** Trading halted manually
- **Max drawdown exceeded:** Portfolio dropped 10% from peak (trading halted)
- **Max daily loss exceeded:** Lost 3% in one day (trading halted)
- **[PDT](../concepts/pdt-rule.md) limit reached:** Used all 3 day trades (can't day trade until window rolls)
- **Position reconciliation failed:** System's positions don't match broker's (data integrity issue)

### Warning Alerts (Monitor Closely)

- **VIX spike:** VIX > 35 (extreme volatility, circuit breaker active)
- **Stale data detected:** Price data > 5 minutes old (feed interruption)
- **[PDT](../concepts/pdt-rule.md) approaching limit:** 2/3 day trades used (1 remaining)
- **High drawdown:** Portfolio down 7-9% from peak (approaching 10% limit)
- **Large position drift:** Position size differs from broker by >1%
- **Model staleness:** ML model hasn't retrained in 14+ days

### Info Alerts (FYI)

- **Circuit breaker cleared:** VIX dropped below 35, trading resumed
- **Data feed reconnected:** Market data feed recovered
- **Model retrained:** New ML model deployed
- **Dead man switch check:** Operator heartbeat required within 48 hours

## Alert Configuration

Alerts are controlled by circuit breaker settings in `config/risk_limits.yaml`:

```yaml
circuit_breakers:
  vix_threshold: 35.0
  stale_data_seconds: 300
  reconciliation_interval_seconds: 300
  max_reconciliation_drift_pct: 1.0
  dead_man_switch_hours: 48
```

See [Risk Limits Reference](../configuration/risk-limits.md) for details.

## Monitoring Best Practices

### Daily Checks (5 minutes)

1. **Portfolio page:** Check total equity, daily P&L, open positions
2. **Risk page:** Verify no circuit breakers active, [PDT](../concepts/pdt-rule.md) counter normal
3. **Trades page:** Review today's executed orders, check for rejections
4. **Logs:** Scan for WARNING or CRITICAL entries

### Weekly Reviews (30 minutes)

1. **Grafana:** Review weekly performance metrics (return, drawdown, Sharpe)
2. **Strategy page:** Compare strategy performance, consider enabling/disabling strategies
3. **Model Health:** Check ML model accuracy, feature drift
4. **Risk limits:** Adjust limits based on observed behavior

### Monthly Audits (2 hours)

1. **Performance analysis:** Compare to benchmarks (S&P 500), calculate returns
2. **Risk analysis:** Review max drawdown, worst days, correlations
3. **Strategy tuning:** Backtest on recent data, adjust parameters
4. **System health:** Review Grafana system metrics, database growth, API latencies

### Autonomous Mode Monitoring

Even in [BOUNDED_AUTONOMOUS](../concepts/autonomy-modes.md#bounded_autonomous) mode:

- **Check dashboard at least once per day**
- **Review weekly performance reports**
- **Monitor Slack/Telegram alerts in real-time**
- **Investigate any WARNING or CRITICAL alerts immediately**

Autonomous doesn't mean unattended. You remain responsible for system oversight.

## Health Check Interval

The system runs health checks every 60 seconds (configurable in `config/settings.yaml`):

```yaml
monitoring:
  health_check_interval_seconds: 60
```

Health checks verify:
- Database connectivity
- Redis connectivity
- IBKR connection status (if provider is `ibkr`)
- Market data feed status
- Position reconciliation

Failed health checks trigger alerts.

## Integration with External Tools

### Export Metrics to External Monitoring

Prometheus metrics can be scraped by:
- **Datadog:** Use Prometheus integration
- **Grafana Cloud:** Add Prometheus data source
- **CloudWatch:** Use Prometheus exporter for AWS

### Custom Alerting

Create custom Prometheus alert rules in `config/prometheus/alerts.yml`:

```yaml
groups:
  - name: trading_alerts
    rules:
      - alert: HighDrawdown
        expr: portfolio_drawdown_pct > 8
        for: 5m
        annotations:
          summary: "Portfolio drawdown exceeds 8%"
```

## Troubleshooting

### Alert Not Received

1. **Check logs:** Verify alert was generated (`grep "alert" logs/backend.log`)
2. **Check notification config:** Ensure `notifications.enabled: true` in `settings.yaml`
3. **Check webhook URL:** Test Slack/Telegram webhook manually
4. **Check environment variables:** Verify `SA_SLACK_WEBHOOK_URL` or `SA_TELEGRAM_BOT_TOKEN` set

### Dashboard Not Updating

1. **Check WebSocket connection:** Browser console should show WebSocket connected
2. **Check Redis:** Ensure Redis is running (`redis-cli ping` should return PONG)
3. **Check backend logs:** Look for WebSocket errors in `logs/backend.log`
4. **Refresh page:** Sometimes WebSocket disconnects, refresh to reconnect

### Grafana Not Showing Data

1. **Check Prometheus:** Visit `http://localhost:9090/targets`, all should be "UP"
2. **Check data source:** Grafana → Configuration → Data Sources → Prometheus should be connected
3. **Check metrics:** Run query in Prometheus UI to verify metrics exist

## Related Topics

- [Risk Management](../concepts/risk-management.md) — Circuit breakers and alert triggers
- [Kill Switch](./kill-switch.md) — Emergency halt procedure
- [Autonomy Modes](../concepts/autonomy-modes.md) — Monitoring requirements for each mode
- [Application Settings](../configuration/settings.md) — Configure health check interval and channels
