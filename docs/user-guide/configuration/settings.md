---
title: Configuration
nav_order: 4
parent: User Guide
has_children: true
---

# Application Settings Reference

System-wide configuration is stored in `config/settings.yaml`. Settings can be overridden using environment variables with the `SA_` prefix and `__` for nesting (e.g., `SA_BROKER__PROVIDER=simulated`).

## File Location

`config/settings.yaml`

Restart the backend after making changes:

```bash
./scripts/restart-backend.sh
```

## Settings Sections

### app

General application settings.

```yaml
app:
  name: alpha-oracle
  environment: development  # development | paper | live
  log_level: INFO           # DEBUG | INFO | WARNING | ERROR
```

- **environment:** Controls runtime mode. Use `development` or `paper` for testing, `live` for real trading.
- **log_level:** Verbosity of logs (written to `logs/backend.log`).

### broker

Broker connection settings.

```yaml
broker:
  provider: ibkr            # ibkr | simulated | paper_stub
  paper_trading: true       # true = paper account, false = live account

  ibkr:
    host: 127.0.0.1
    port: 4002              # IB Gateway: paper=4002, live=4001
                            # TWS: paper=7497, live=7496
    client_id: 1            # Unique ID per connection (broker=1, data=2, feed=3)
    account_id: ""          # Leave blank for single-account setups
```

**Provider options:**
- `ibkr`: Interactive Brokers via IB Gateway or TWS (requires IBKR account)
- `simulated`: In-memory SimulatedBroker for testing (no real broker connection)
- `paper_stub`: Demo broker with fake data (default if IBKR not configured)

**Environment variable override:**
```bash
export SA_BROKER__PROVIDER=simulated
export SA_BROKER__PAPER_TRADING=true
```

### data

Data source configuration for market data and filings.

```yaml
data:
  alpha_vantage:
    rate_limit_per_minute: 5       # Free tier = 5 calls/min
    cache_ttl_hours: 24            # Cache data for 24 hours

  edgar:
    user_agent: "alpha-oracle bot@example.com"
    rate_limit_per_second: 10      # SEC Edgar rate limit

  feed:
    feed_type: iex                 # iex (free, 15-min delayed) | sip (paid, real-time)
    symbols_per_connection: 200    # Max symbols per WebSocket connection
    reconnect_delay_seconds: 5     # Delay before reconnecting after disconnect
    max_reconnect_attempts: 10     # Max reconnect attempts
```

**Alpha Vantage API key** (required for historical data):
```bash
export SA_ALPHA_VANTAGE_API_KEY=your_key_here
```

Get a free key at [alphavantage.co](https://www.alphavantage.co/support/#api-key).

**IEX vs SIP feeds:**
- **IEX:** Free, 15-minute delayed quotes (sufficient for swing trading)
- **SIP:** Paid, real-time quotes (requires IBKR market data subscription)

### database

TimescaleDB connection settings.

```yaml
database:
  url: postgresql+asyncpg://trader:dev_password@localhost:5432/stock_analysis
  pool_size: 10             # Connection pool size
  max_overflow: 20          # Max additional connections beyond pool_size
```

The database stores:
- Historical OHLCV bars
- Fundamental data
- Trade records
- Strategy backtest results

Started automatically by `./scripts/start-backend.sh`.

### redis

Redis connection settings for caching and pub/sub.

```yaml
redis:
  url: redis://localhost:6379/0
  cache_ttl_seconds: 3600    # 1 hour cache TTL
```

Redis stores:
- Real-time portfolio state
- PDT trade counters
- Kill switch state
- Circuit breaker flags
- WebSocket pub/sub events

Started automatically by `./scripts/start-backend.sh`.

### strategy

Strategy backtesting and ranking configuration.

```yaml
strategy:
  min_sharpe_ratio: 1.0       # Minimum Sharpe ratio for deployment
  min_profit_factor: 1.5      # Minimum profit factor (gross profit / gross loss)
  max_drawdown_pct: 20.0      # Max acceptable drawdown (%)
  min_trades: 100             # Minimum trades for statistical significance

  walk_forward:
    train_months: 24          # Training window (24 months)
    test_months: 6            # Test window (6 months)
    step_months: 3            # Step size (3 months)

  ranking_weights:
    sharpe: 0.30              # 30% weight on Sharpe ratio
    sortino: 0.20             # 20% weight on Sortino ratio
    max_drawdown_inverse: 0.20  # 20% weight on max drawdown (inverted)
    profit_factor: 0.15       # 15% weight on profit factor
    consistency: 0.15         # 15% weight on consistency (% positive months)
```

See [Trading Strategies](../concepts/strategies-explained.md) for how strategies are ranked.

### execution

Order execution settings.

```yaml
execution:
  default_order_type: limit   # market | limit | stop
  limit_offset_pct: 0.05      # Limit order offset (5 bps from current price)
  max_slippage_pct: 0.10      # Max acceptable slippage (10 bps)
  position_sizing: half_kelly # half_kelly | fixed_pct | equal_weight
```

**Position sizing methods:**
- `half_kelly`: Half Kelly criterion (risk-adjusted sizing based on win rate and risk/reward)
- `fixed_pct`: Fixed percentage of portfolio per position
- `equal_weight`: Equal dollar amount per position

### ml

Machine learning model configuration.

```yaml
ml:
  prediction_horizon: 5         # Predict 5-day forward returns
  up_threshold: 0.01            # >1% = UP class
  down_threshold: -0.01         # <-1% = DOWN class
  min_training_samples: 500     # Min samples before model is valid
  retrain_interval_days: 7      # Retrain weekly
  model_staleness_days: 14      # Model expires after 14 days
  confidence_threshold: 0.55    # Min 55% confidence to generate signal
```

See [ML Signal Intelligence](../concepts/ml-signals.md) for details on the ML strategy.

### scheduler

APScheduler cron job schedules.

```yaml
scheduler:
  enabled: true
  daily_bars_cron: "0 17 * * 1-5"          # 5pm ET weekdays (after market close)
  weekly_fundamentals_cron: "0 6 * * 6"    # 6am Saturday
  biweekly_altdata_cron: "0 7 1,15 * *"    # 7am on 1st and 15th of month
  weekly_retrain_cron: "0 2 * * 0"         # 2am Sunday
```

**Cron syntax:** `minute hour day month day_of_week`

Jobs can be triggered manually via API:
```bash
curl -X POST http://localhost:8000/api/system/scheduler/trigger/daily_bars
```

### router

Smart order router settings.

```yaml
router:
  size_threshold_small_pct: 0.1    # <0.1% of ADV = small order (use market)
  size_threshold_large_pct: 1.0    # >1% of ADV = large order (use TWAP)
  twap_num_slices: 5               # Split TWAP into 5 slices
  twap_interval_seconds: 60        # 60 seconds between slices
  wide_spread_threshold_bps: 20.0  # >20bps spread = wide (use limit)
```

**Order routing logic:**
- Small orders (<0.1% ADV, narrow spread): MARKET
- Medium orders (0.1-1% ADV, narrow spread): LIMIT
- Large orders (>1% ADV): TWAP (time-weighted average price)
- Wide spread (>20bps): LIMIT (avoid market impact)

See developer guide for smart router details.

### monitoring

Metrics and health checks.

```yaml
monitoring:
  prometheus_port: 8001                 # Prometheus metrics endpoint
  health_check_interval_seconds: 60     # Health check every 60 seconds
```

- **Prometheus:** Metrics available at `http://localhost:8001/metrics`
- **Grafana:** Dashboards available at `http://localhost:3001` (started by `./scripts/start-backend.sh`)

### notifications

Alert notification channels (optional).

```yaml
notifications:
  enabled: false
  channels: []  # slack, telegram
```

To enable:
1. Set `enabled: true`
2. Add channels: `channels: [slack, telegram]`
3. Configure Slack webhook or Telegram bot token via environment variables

See [Monitoring & Alerts](../operations/monitoring-alerts.md) for setup.

## Environment Variable Overrides

All settings can be overridden using environment variables:

**Format:** `SA_<section>__<subsection>__<key>=value`

**Examples:**
```bash
# Broker settings
export SA_BROKER__PROVIDER=simulated
export SA_BROKER__PAPER_TRADING=true
export SA_BROKER__IBKR__PORT=4002

# Database settings
export SA_DATABASE__URL=postgresql+asyncpg://user:pass@host:5432/db

# ML settings
export SA_ML__CONFIDENCE_THRESHOLD=0.60

# API keys
export SA_ALPHA_VANTAGE_API_KEY=your_key

# LLM provider — choose one:
# Option A: Direct Anthropic API
export ANTHROPIC_API_KEY=your_key

# Option B: AWS Bedrock
export SA_AGENT__PROVIDER=bedrock
export SA_AGENT__AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
# Bedrock requires a cross-region inference model ID, e.g.:
# export SA_AGENT__MODEL=us.anthropic.claude-sonnet-4-5-20251001-v1:0
```

Environment variables take precedence over `settings.yaml`.

## Validation

The system validates settings on startup using Pydantic. Invalid settings will cause the backend to fail with a clear error message:

```
ValidationError: broker.ibkr.port must be an integer
```

Check `logs/backend.log` for validation errors.

## Related Topics

- [Risk Limits Reference](./risk-limits.md) — Risk control settings
- [Autonomy Modes](../concepts/autonomy-modes.md) — How environment affects autonomy
- [Monitoring & Alerts](../operations/monitoring-alerts.md) — Notification setup
