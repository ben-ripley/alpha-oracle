# Monitoring Module

The `src/monitoring/` module implements observability for the alpha-oracle system via Prometheus metrics (counters, gauges, histograms), AlertManager for Slack/Telegram notifications, and Grafana dashboards. All components emit structured logs via structlog for centralized analysis.

## Purpose

Monitoring provides:

- **Prometheus metrics** on port 8001 for trading activity, portfolio state, risk events, and system health
- **AlertManager** with Slack and Telegram channels for critical alerts
- **Grafana dashboards** pre-configured via provisioning
- **Structured logging** via structlog with JSON output for parsing
- **Health check metrics** for broker, feed, database, and [Redis](../glossary.md#redis) connectivity

## Key Components

### Prometheus Metrics

#### `TradingMetrics` (src/monitoring/metrics.py)

Centralized Prometheus metrics registry.

**Metric Types:**

| Type | Purpose | Example |
|------|---------|---------|
| Counter | Monotonically increasing count | `trading_orders_total` |
| Gauge | Current value (can go up/down) | `trading_portfolio_equity_dollars` |
| Histogram | Distribution of values | `trading_trade_pnl_dollars` |
| Info | Static metadata | `trading_system_info` (version, environment) |

**System Metrics:**
```python
system_info = Info("trading_system", "Trading system information")
system_info.info({
    "version": "1.0.0",
    "environment": "production",
    "broker": "ibkr"
})
```

**Trading Metrics:**
```python
# Order counters (labels: side, order_type, strategy, status)
orders_total = Counter("trading_orders_total", "Total orders submitted", ["side", "order_type", "strategy", "status"])
orders_total.labels(side="BUY", order_type="LIMIT", strategy="SwingMomentum", status="FILLED").inc()

# Trade counters (labels: side, strategy)
trades_total = Counter("trading_trades_total", "Total trades executed", ["side", "strategy"])
trades_total.labels(side="BUY", strategy="SwingMomentum").inc()

# Trade P&L histogram (labels: strategy)
trade_pnl = Histogram("trading_trade_pnl_dollars", "Trade P&L in dollars", ["strategy"], buckets=[-1000, -500, -200, -100, -50, -20, 0, 20, 50, 100, 200, 500, 1000])
trade_pnl.labels(strategy="SwingMomentum").observe(150.50)
```

**Portfolio Metrics:**
```python
# Gauges (values updated on each portfolio snapshot)
portfolio_equity = Gauge("trading_portfolio_equity_dollars", "Total portfolio equity")
portfolio_equity.set(105432.50)

portfolio_cash = Gauge("trading_portfolio_cash_dollars", "Available cash")
portfolio_cash.set(52716.25)

portfolio_positions_count = Gauge("trading_portfolio_positions_count", "Number of open positions")
portfolio_positions_count.set(8)

portfolio_daily_pnl = Gauge("trading_portfolio_daily_pnl_dollars", "Daily P&L in dollars")
portfolio_daily_pnl.set(543.20)

portfolio_daily_pnl_pct = Gauge("trading_portfolio_daily_pnl_pct", "Daily P&L percentage")
portfolio_daily_pnl_pct.set(0.52)

portfolio_drawdown_pct = Gauge("trading_portfolio_drawdown_pct", "Current drawdown percentage")
portfolio_drawdown_pct.set(3.2)
```

**Risk Metrics:**
```python
# Risk check counters (labels: result = approve/reject/require_approval/reduce_size)
risk_checks_total = Counter("trading_risk_checks_total", "Total risk checks performed", ["result"])
risk_checks_total.labels(result="approve").inc()

# PDT guard gauge
pdt_trades_used = Gauge("trading_pdt_trades_used", "Day trades used in rolling 5-day window (max 3)")
pdt_trades_used.set(2)

# Circuit breakers gauge
circuit_breakers_tripped = Gauge("trading_circuit_breakers_tripped", "Number of circuit breakers currently tripped")
circuit_breakers_tripped.set(0)

# Kill switch gauge (1=active, 0=inactive)
kill_switch_active = Gauge("trading_kill_switch_active", "Kill switch status")
kill_switch_active.set(0)
```

**Execution Metrics:**
```python
# Fill latency histogram
fill_latency_ms = Histogram("trading_fill_latency_ms", "Time from signal to fill in milliseconds", buckets=[100, 500, 1000, 2000, 5000, 10000])
fill_latency_ms.observe(1250)

# Slippage histogram
slippage_bps = Histogram("trading_slippage_bps", "Execution slippage in basis points", buckets=[0, 1, 2, 5, 10, 20, 50])
slippage_bps.observe(3.3)
```

**ML Metrics:**
```python
# Model accuracy gauge
ml_model_accuracy = Gauge("trading_ml_model_accuracy", "Current ML model accuracy")
ml_model_accuracy.set(0.58)

# PSI drift gauge
ml_psi_drift = Gauge("trading_ml_psi_drift", "Population Stability Index (model drift)")
ml_psi_drift.set(0.12)
```

**Metrics Endpoint:**

Prometheus scrapes metrics from `http://localhost:8001/metrics`.

**Configuration (config/settings.yaml):**
```yaml
monitoring:
  prometheus_port: 8001
  health_check_interval_seconds: 60
```

**Start Metrics Server:**
```python
from prometheus_client import start_http_server

start_http_server(8001)  # Called on API startup
```

### AlertManager

#### `AlertManager` (src/monitoring/alerts.py)

Routes alerts to multiple channels: log, Slack, Telegram.

**Severity Levels:**
- `CRITICAL`: System failures, kill switch activation, account violations
- `WARNING`: Risk thresholds breached (drawdown > 5%, PDT approaching limit)
- `INFO`: Routine events (job completions, model retraining)

**Channels:**
- `log`: Always enabled (structlog)
- `slack`: Webhook URL required
- `telegram`: Bot token + chat ID required

**Configuration:**
```python
from src.monitoring.alerts import AlertManager, AlertSeverity

alert_manager = AlertManager(channels=["log", "slack"])
alert_manager.configure_slack(webhook_url="https://hooks.slack.com/services/...")

await alert_manager.send_alert(
    severity=AlertSeverity.CRITICAL,
    title="Kill Switch Activated",
    message="Trading halted due to circuit breaker: VIX > 35",
    metadata={"vix": 38.5, "timestamp": datetime.utcnow().isoformat()}
)
```

**Slack Webhook Payload:**
```json
{
  "text": "⚠️ CRITICAL: Kill Switch Activated",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Kill Switch Activated*\n\nTrading halted due to circuit breaker: VIX > 35\n\n*Metadata:*\n• VIX: 38.5\n• Timestamp: 2024-03-15T14:32:00Z"
      }
    }
  ]
}
```

**Telegram Message:**
```
🔴 CRITICAL: Kill Switch Activated

Trading halted due to circuit breaker: VIX > 35

Metadata:
• VIX: 38.5
• Timestamp: 2024-03-15T14:32:00Z
```

**Alert Triggers:**

1. **PDT Warning:** 2 day trades used (1 remaining).
2. **PDT Critical:** 3 day trades used (limit reached).
3. **Drawdown Warning:** Drawdown > 5%.
4. **Drawdown Critical:** Drawdown > 8% (circuit breaker trips at 10%).
5. **Daily Loss Warning:** Daily P&L < -2%.
6. **Daily Loss Critical:** Daily P&L < -2.5% (circuit breaker trips at -3%).
7. **Model Drift Warning:** PSI > 0.1.
8. **Model Drift Critical:** PSI > 0.2 (retraining required).
9. **Kill Switch Activation:** Any kill switch trigger.
10. **Broker Disconnect:** IBKR connection lost.
11. **Feed Disconnect:** Market feed connection lost.

### Grafana Dashboards

Grafana (port 3001) pre-configured with dashboards via provisioning.

**Dashboards:**

1. **Trading Overview:**
   - Portfolio equity over time
   - Daily P&L (bar chart)
   - Open positions count
   - Order success rate

2. **Risk Metrics:**
   - PDT trades used (gauge)
   - Circuit breaker states (status panel)
   - Kill switch status (indicator)
   - Drawdown chart

3. **Execution Quality:**
   - Slippage distribution (histogram)
   - Fill latency distribution (histogram)
   - Order type breakdown (pie chart)

4. **ML Model Performance:**
   - Model accuracy over time
   - PSI drift over time
   - Feature importance (bar chart)
   - Prediction confidence distribution

**Provisioning (config/grafana/provisioning/dashboards/):**
```yaml
# dashboard.yml
apiVersion: 1
providers:
  - name: 'default'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
```

**Data Source (config/grafana/provisioning/datasources/prometheus.yml):**
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

### Structured Logging

#### structlog Configuration

All modules use structlog for structured JSON logging.

**Configuration (src/api/main.py):**
```python
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)
```

**Usage:**
```python
import structlog

logger = structlog.get_logger(__name__)

logger.info("order_submitted", symbol="AAPL", order_id="abc123", quantity=100, price=150.00)
logger.warning("pdt_day_trade_recorded", symbol="AAPL", day_trades_used=3)
logger.error("order_rejected", symbol="AAPL", reason="max_positions_exceeded", max_positions=20)
```

**Output (JSON):**
```json
{"event": "order_submitted", "symbol": "AAPL", "order_id": "abc123", "quantity": 100, "price": 150.0, "timestamp": "2024-03-15T14:32:15.123456Z", "level": "info"}
{"event": "pdt_day_trade_recorded", "symbol": "AAPL", "day_trades_used": 3, "timestamp": "2024-03-15T14:35:20.987654Z", "level": "warning"}
{"event": "order_rejected", "symbol": "AAPL", "reason": "max_positions_exceeded", "max_positions": 20, "timestamp": "2024-03-15T14:40:10.456789Z", "level": "error"}
```

**Log Files:**
- Backend: `logs/backend.log`
- Frontend: `logs/frontend.log`

**Log Rotation:**
- Size-based: 100 MB per file
- Retention: 10 files
- Compression: gzip

### Prometheus Configuration

#### config/prometheus.yml

Prometheus scrape configuration.

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'alpha-oracle-api'
    static_configs:
      - targets: ['host.docker.internal:8000']  # FastAPI main app
        labels:
          service: 'api'

  - job_name: 'alpha-oracle-metrics'
    static_configs:
      - targets: ['host.docker.internal:8001']  # Prometheus metrics endpoint
        labels:
          service: 'metrics'

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
        labels:
          service: 'redis'

  - job_name: 'timescaledb'
    static_configs:
      - targets: ['timescaledb:5432']
        labels:
          service: 'database'
```

**Targets:**
- API: `localhost:8000` (health check endpoint)
- Metrics: `localhost:8001/metrics` (Prometheus client)
- Redis: `localhost:6379` (Redis exporter)
- TimescaleDB: `localhost:5432` (Postgres exporter)

## Configuration

**Settings (config/settings.yaml):**
```yaml
monitoring:
  prometheus_port: 8001
  health_check_interval_seconds: 60
```

**Environment Variable Overrides:**
```bash
export SA_MONITORING__PROMETHEUS_PORT=8002
export SA_MONITORING__HEALTH_CHECK_INTERVAL_SECONDS=30
```

**Slack Webhook:**
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

**Telegram Bot:**
```bash
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
export TELEGRAM_CHAT_ID="-1001234567890"
```

## Integration with Other Modules

- **Execution Engine** (`src/execution/`): Increments `orders_total`, `trades_total`, observes `fill_latency_ms`, `slippage_bps`.
- **Risk Management** (`src/risk/`): Updates `pdt_trades_used`, `circuit_breakers_tripped`, `kill_switch_active`.
- **Portfolio Monitor** (`src/risk/portfolio_monitor.py`): Updates `portfolio_equity`, `portfolio_daily_pnl`, `portfolio_drawdown_pct`.
- **ML Pipeline** (`src/signals/`): Updates `ml_model_accuracy`, `ml_psi_drift`.
- **API** (`src/api/`): Exposes health check endpoint for Prometheus scraping.

## Critical Patterns

1. **Metrics as code:** All metrics defined centrally in `TradingMetrics` class.
2. **Labels for grouping:** Use labels (e.g., `strategy`, `side`) for filtering in Grafana.
3. **Histogram buckets:** Pre-defined buckets for latency, slippage, P&L distributions.
4. **Structured logs for audit:** All trading decisions logged with context (symbol, order_id, timestamp).
5. **Alert severity escalation:** INFO → WARNING → CRITICAL based on threshold breaches.
6. **Prometheus scrape interval:** 15s (balance between timeliness and load).

## Glossary Links

- [Redis](../glossary.md#redis) — In-memory data store
- [PDT](../glossary.md#pdt) — Pattern Day Trader rule
- [IBKR](../glossary.md#ibkr) — Interactive Brokers
- [Prometheus](../glossary.md#prometheus) — Metrics and monitoring system
- [Grafana](../glossary.md#grafana) — Visualization and alerting platform

<!-- DIAGRAM: Monitoring architecture — modules → Prometheus → Grafana dashboards + AlertManager → Slack/Telegram -->
