# Getting Started

This guide will help you get oriented when you first open the AlphaOracle System dashboard.

## First-Time Orientation

When you first access the dashboard, you'll see a dark, terminal-style interface inspired by professional trading platforms ("Bloomberg meets Blade Runner"). The system is designed for clarity and efficiency, with:

- **Dark theme** — Void/abyss/surface backgrounds to reduce eye strain
- **High-contrast colors** — Cyan for highlights, green for gains, red for losses, amber for warnings
- **Monospace fonts** — JetBrains Mono for numbers/data, Outfit for headings
- **Real-time updates** — WebSocket connection provides live data without page refreshes

## The Four Main Pages

The dashboard is organized into four primary views, accessible via the navigation bar:

### 1. Portfolio
Your account overview: total equity, cash, positions, P&L, sector allocation, and equity curve.
- **Use this to**: Monitor overall performance and position health
- [Full documentation](dashboard/portfolio.md)

### 2. Strategies
Strategy performance rankings, ML signal feed, feature importance, and model monitoring.
- **Use this to**: Understand which strategies are performing well and why
- [Full documentation](dashboard/strategies.md)

### 3. Risk
[PDT guard](../glossary.md#pdt), position/portfolio limits, circuit breakers, and the kill switch.
- **Use this to**: Monitor risk exposure and enforce safety constraints
- [Full documentation](dashboard/risk.md)

### 4. Trades
Trade history, pending approvals, execution quality, and daily summary.
- **Use this to**: Review past trades and approve new orders (in MANUAL_APPROVAL mode)
- [Full documentation](dashboard/trades.md)

<!-- DIAGRAM: Four-panel dashboard layout showing Portfolio, Strategies, Risk, and Trades pages -->

## Paper Trading vs. Live Trading

The system operates in one of four **autonomy modes**:

### PAPER_ONLY (Default)
- All trades are simulated (no real broker connection)
- No real money at risk
- Perfect for testing strategies and learning the system
- Demo data is pre-loaded for exploration

### MANUAL_APPROVAL
- Real broker connection (Interactive Brokers)
- Every trade requires your explicit approval
- Orders appear in the **Trades** page under "Pending Approvals"
- You can approve or reject each order individually

### BOUNDED_AUTONOMOUS
- Real broker connection
- Trades execute automatically within pre-configured risk limits
- Circuit breakers and [PDT guard](../glossary.md#pdt) remain active
- Kill switch available for emergency stops

### FULL_AUTONOMOUS
- Real broker connection
- Fully automated trading with maximum flexibility
- Use only after thorough testing and validation
- **Not recommended** for most users

> **Note**: Changing autonomy modes requires backend configuration changes. See [Configuration Guide](../operations/configuration.md) for details.

## Initial Configuration Checklist

Before using the system with real money, complete these steps:

### 1. Verify Paper Trading
- [ ] Confirm the dashboard loads successfully
- [ ] Check that demo data appears on all pages
- [ ] Verify real-time updates work (watch for data changes)

### 2. Review Risk Limits
- [ ] Understand the [PDT rule](../glossary.md#pdt) (max 3 day trades per 5 business days)
- [ ] Review position limits on the [Risk](dashboard/risk.md) page
- [ ] Familiarize yourself with circuit breaker conditions

### 3. Study Strategies
- [ ] Read about each strategy on the [Strategies](dashboard/strategies.md) page
- [ ] Click "How it works" buttons to see detailed explanations
- [ ] Review backtest results (equity curves, [Sharpe ratio](../glossary.md#sharpe-ratio), [max drawdown](../glossary.md#max-drawdown))

### 4. Practice Manual Approval
- [ ] Switch to MANUAL_APPROVAL mode (requires backend config)
- [ ] Let the system generate signals
- [ ] Practice approving/rejecting orders on the [Trades](dashboard/trades.md) page
- [ ] Review execution quality metrics

### 5. Test the Kill Switch
- [ ] Locate the kill switch on the [Risk](dashboard/risk.md) page
- [ ] Understand the confirmation process (type "KILL" to activate)
- [ ] Practice activating and deactivating it

### 6. Configure Broker Connection
- [ ] Set up Interactive Brokers (IBKR) account
- [ ] Configure IB Gateway or TWS (paper trading port: 4002, live: 4001)
- [ ] Verify broker connection health in the backend logs

## What to Expect

### Real-Time Updates
The dashboard uses WebSockets to push updates from the backend:
- Portfolio values refresh as market prices change
- New signals appear in the ML signal feed as they're generated
- Risk metrics update when trades execute or positions change

### Scheduled Jobs
The system runs several background jobs:
- **Daily (5:00 PM ET, weekdays)**: Ingest latest market data (OHLCV bars)
- **Weekly (Saturday 6:00 AM)**: Update fundamental data (earnings, financials)
- **Biweekly (1st & 15th, 7:00 AM)**: Refresh alternative data (short interest, insider trades)
- **Weekly (Sunday 2:00 AM)**: Retrain ML models with latest data

### Demo Data
In PAPER_ONLY mode, the system uses pre-seeded demo data:
- Simulated portfolio with $25,000 starting capital
- Historical backtest results for all strategies
- Sample trades and positions
- Synthetic risk metrics

To clear demo data and start fresh: `./scripts/clear_database.sh`

## Common First-Time Questions

**Q: Why do I see "No data available" on some charts?**
A: Demo data may not cover all time periods. Run the backfill script to load historical data: `python scripts/backfill_history.py --years 2 --symbols sp500`

**Q: How do I know if the system is working?**
A: Check the WebSocket status in your browser's network inspector. Look for an active connection to `/ws`. The dashboard should show the current time in the header (if implemented).

**Q: Can I switch strategies on/off?**
A: Strategy selection is managed in the backend configuration. The dashboard shows which strategies are active and their performance rankings.

**Q: What if I don't understand a term?**
A: Check the [Glossary](../glossary.md) for definitions of financial and technical terms. Terms are linked throughout the documentation.

**Q: How do I get help?**
A: See the [Troubleshooting Guide](../operations/troubleshooting.md) or report issues at https://github.com/anthropics/claude-code/issues

## Next Steps

Once you're comfortable with the basics:
1. Read the detailed [Dashboard Overview](dashboard/index.md)
2. Explore each page: [Portfolio](dashboard/portfolio.md), [Strategies](dashboard/strategies.md), [Risk](dashboard/risk.md), [Trades](dashboard/trades.md)
3. Review the [Configuration Guide](../operations/configuration.md) to customize behavior
4. When ready for live trading, carefully follow the [Live Trading Checklist](../operations/live-trading.md)
