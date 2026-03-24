---
title: Home
nav_order: 1
---

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

## Disclaimer

This software is for educational and research purposes only. Automated trading involves substantial risk of loss. Past performance (including backtests) does not guarantee future results. The author is not responsible for any financial losses incurred through use of this system. Always start with paper trading and never risk money you cannot afford to lose.

Alpha-Oracle is an experimental system built to explore algorithmic trading concepts, machine learning signal generation, and automated risk management. It is not financial advice, investment advice, or a recommendation to buy or sell any security.

USE AT YOUR OWN RISK. Trading stocks involves substantial risk of loss. Automated trading systems can and do lose money, malfunction, generate incorrect signals, fail to execute orders correctly, or behave in unexpected ways — including during periods of high market volatility or infrastructure failure. Past simulated or backtested performance is not indicative of future results.

By using this software, you acknowledge and agree that:
- You are solely responsible for any trades executed through or informed by this system
- The author(s) of this software accept no liability for any financial losses, missed opportunities, regulatory violations, brokerage penalties, or other damages arising from your use of this software                                                                          
- This software is not registered with, endorsed by, or affiliated with any financial regulatory authority (SEC, FINRA, CFTC, or otherwise)
- You are responsible for ensuring your use of this software complies with all applicable laws and regulations in your jurisdiction         
- The PDT guard and other risk controls are provided as a convenience and are not guaranteed to prevent regulatory violations or financial loss

The author(s) provide this software "as is," without warranty of any kind, express or implied. In no event shall the author(s) be liable for any claim, damages, or other liability arising from the use of this software.

If you are not comfortable with these risks, do not use this software with a live brokerage account.