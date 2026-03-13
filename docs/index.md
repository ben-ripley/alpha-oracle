# AlphaOracle System

An AI-driven automated stock trading system designed for retail investors with accounts under $25,000. Built for swing and position trading strategies, the system combines traditional technical analysis with machine learning signals to identify opportunities in US equities markets.

## For Investors

If you're using this system to manage your portfolio, start with the **[User Guide](user-guide/index.md)** to learn how to:

- Configure trading strategies and risk parameters
- Monitor your portfolio and active positions
- Understand the ML-generated signals and recommendations
- Use the real-time dashboard
- Work within Pattern Day Trader (PDT) regulations

## For Developers

If you're building, extending, or maintaining this system, the **[Developer Guide](developer-guide/index.md)** covers:

- System architecture and design decisions
- Data pipeline and feature engineering
- Strategy development and backtesting
- API reference and integration patterns
- Deployment and operations

## Key Features

- **Automated Strategy Execution**: Multiple built-in strategies (momentum, mean reversion, ML-driven) with configurable parameters
- **Machine Learning Signals**: XGBoost model trained on 50+ point-in-time features with walk-forward validation
- **Comprehensive Risk Management**: Position limits, portfolio circuit breakers, and PDT protection for sub-$25K accounts
- **Real-Time Dashboard**: Dark-themed interface with live WebSocket updates, portfolio analytics, and model health monitoring
- **Professional-Grade Infrastructure**: TimescaleDB for time-series data, Redis pub/sub for events, Prometheus/Grafana for observability
- **Interactive Brokers Integration**: Direct connectivity to IBKR via IB Gateway or Trader Workstation

## Getting Started

- **New Users**: [Quick Start Guide](user-guide/quick-start.md)
- **Developers**: [Development Setup](developer-guide/setup.md)
- **Architecture**: [System Overview](developer-guide/architecture/overview.md)
