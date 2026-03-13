# User Guide

Welcome to the Stock Analysis System user guide. This guide is designed for investors and users who want to understand how to use the system effectively, monitor their portfolio, and manage risk.

## What This Guide Covers

This user guide provides comprehensive documentation for:

- **Getting Started** — First-time orientation and initial configuration
- **Dashboard** — Understanding and navigating the web interface
- **Trading Concepts** — Key financial terms and system concepts (see [Glossary](../glossary.md))
- **Configuration** — Customizing strategies, risk limits, and autonomy modes
- **Operations** — Day-to-day usage, monitoring, and troubleshooting

## Quick Navigation

### Dashboard Pages
- [Portfolio](dashboard/portfolio.md) — View equity, positions, P&L, and allocation
- [Strategies](dashboard/strategies.md) — Strategy rankings, ML signals, and model health
- [Risk](dashboard/risk.md) — PDT guard, limits, circuit breakers, and kill switch
- [Trades](dashboard/trades.md) — Trade history, pending approvals, and execution quality

### Getting Started
- [First-Time Setup](getting-started.md) — What to expect when you first open the dashboard
- [Dashboard Overview](dashboard/index.md) — Introduction to the interface and real-time updates

## Safety First

The system starts in **PAPER_ONLY** mode by default. This means:
- No real money is at risk
- All trades are simulated
- You can explore the dashboard and test strategies safely
- Real trading requires explicit configuration changes

## Key Features

- **Real-time monitoring** — WebSocket updates for portfolio, signals, and risk metrics
- **Multi-strategy system** — Backtest-ranked strategies with composite scoring
- **ML-driven signals** — XGBoost model with 50+ point-in-time features
- **Automated risk management** — PDT guard, position limits, circuit breakers
- **Manual approval mode** — Review and approve every trade before execution
- **Kill switch** — Emergency stop for all trading activity

## Regulatory Compliance

This system is designed for **retail investors with accounts under $25,000**. It enforces the FINRA [PDT rule](../glossary.md#pdt) (Pattern Day Trader) to prevent regulatory violations:
- Maximum 3 day trades per rolling 5 business days
- Swing/position trading only (hold times 2+ days)
- Conservative decision-making (rejects trades when in doubt)

## Support

For technical support or to report issues, visit: https://github.com/anthropics/claude-code/issues

## Next Steps

- New users: Start with [Getting Started](getting-started.md)
- Existing users: Jump to the [Dashboard Overview](dashboard/index.md)
- Technical details: See the [Developer Documentation](../dev-guide/index.md)
