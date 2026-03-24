---
title: Portfolio
nav_order: 1
parent: Dashboard
---

# Portfolio Page

The Portfolio page provides a comprehensive view of your account health, open positions, and allocation.

## Overview

This is typically your starting point when opening the dashboard. It answers three key questions:
1. **How much am I worth?** — Total equity (cash + positions)
2. **How am I doing today?** — Daily P&L and percentage change
3. **What do I own?** — Open positions with unrealized gains/losses

## Top Stat Cards

Four key metrics are displayed prominently at the top:

### Total Equity
- **What it is**: Your total account value (cash + market value of all positions)
- **Calculation**: `Cash + Sum(Position Quantity × Current Price)`
- **Subtitle**: Number of open positions (e.g., "5 positions")

### Daily P&L
- **What it is**: Today's profit or loss in dollars and percentage
- **Calculation**: `(Current Equity - Previous Day's Close Equity)`
- **Color**: Green if positive, red if negative
- **Icon**: Trending up (↗) for gains, trending down (↘) for losses

### Cash
- **What it is**: Uninvested cash available for new positions
- **Subtitle**: Cash as percentage of total equity
- **Why it matters**: You need cash reserves for new trades and to meet the 10% minimum cash reserve requirement

### Positions Value
- **What it is**: Total market value of all open positions
- **Calculation**: `Sum(Position Quantity × Current Price)`
- **Subtitle**: Percentage of equity invested (e.g., "85.3% invested")

<!-- DIAGRAM: Top four stat cards with labeled sections -->

## Account Value Chart

A 30-day equity curve shows your account's value over time:

- **X-axis**: Date (last 30 days)
- **Y-axis**: Total equity in dollars
- **Line color**: Cyan with gradient fill
- **Purpose**: Visualize account growth/decline and volatility

**Interpreting the curve**:
- **Upward slope** — Account is growing
- **Flat line** — No net change (possibly all cash, no positions)
- **Downward slope** — Losing money
- **Jagged/volatile** — High-risk strategies or market turbulence
- **Smooth curve** — Conservative strategies, diversified positions

<!-- DIAGRAM: Equity curve with annotated regions (growth, drawdown, recovery) -->

## Allocation Donut Chart

A donut chart shows sector and cash allocation:

- **Inner ring**: Shows proportional allocation by color
- **Legend**: Lists each sector/cash with percentage
- **Colors**: Each sector has a unique color (Technology = cyan, Financials = purple, etc.)
- **Cash wedge**: Gray, shows uninvested cash

**Why allocation matters**:
- Diversification reduces risk (don't put all eggs in one basket)
- Sector concentration limits prevent over-exposure (max 25% per sector)
- High cash allocation means you're not fully deployed (may miss opportunities)

**Example allocation**:
```
Technology: 35.2%
Financials: 18.7%
Healthcare: 15.9%
Energy: 10.4%
Cash: 19.8%
```

This portfolio is heavily weighted to Technology, which could be risky if tech stocks decline.

<!-- DIAGRAM: Annotated donut chart showing sector wedges and percentages -->

## Open Positions Table

A detailed table lists all open positions with key metrics:

| Column | Description |
|--------|-------------|
| **Symbol** | Stock ticker (e.g., AAPL, MSFT) |
| **Qty** | Number of shares owned (always positive) |
| **Avg Entry** | Average price paid per share (cost basis) |
| **Current** | Current market price per share |
| **Mkt Value** | Current total value (`Qty × Current Price`) |
| **P&L** | Unrealized profit/loss (`Mkt Value - Qty × Avg Entry`) |
| **P&L %** | Percentage gain/loss (color-coded pill: green = gain, red = loss) |
| **Sector** | Industry classification (e.g., Technology, Healthcare) |
| **Strategy** | Which strategy opened this position |

**Sorting**: Click column headers to sort (if implemented).

**Color coding**:
- **Bright white text** — Symbol (high visibility)
- **Green P&L** — Position is profitable
- **Red P&L** — Position is losing money
- **Dimmed text** — Less critical info (sector, strategy)

### Position Example

```
Symbol: AAPL
Qty: 50
Avg Entry: $175.00
Current: $182.50
Mkt Value: $9,125.00
P&L: +$375.00
P&L %: +4.3%
Sector: Technology
Strategy: MLSignalStrategy
```

This position is up $375 (4.3% gain) since entry. It represents `$9,125 / Total Equity` of your portfolio.

## When to Use This Page

Check the Portfolio page:
- **Daily**: To review overall performance and P&L
- **After trades**: To see how new positions affect allocation
- **Before trading**: To check available cash and sector concentration
- **During market hours**: To monitor real-time position values (if live data is enabled)

## Key Metrics to Watch

### Total Equity
Track this daily. Consistent growth is the goal. Sharp drops warrant investigation (check Trades page for losing positions).

### Daily P&L
Volatile daily P&L is normal, but consistent daily losses indicate strategy problems. Compare against the broader market (SPY as benchmark).

### Cash Percentage
- **Too high** (>30%): You're not fully deployed; may miss opportunities
- **Too low** (<10%): Risk violating the minimum cash reserve limit; can't open new positions

### Sector Concentration
- **Balanced** (no sector >25%): Good diversification
- **Concentrated** (one sector >40%): High risk if that sector declines

### Unrealized P&L per Position
Identify winners and losers. Consider closing losing positions if they don't recover (cut losses). Let winners run unless strategy signals exit.

## Related Pages

- **[Strategies](strategies.md)**: See which strategies generated your positions
- **[Risk](risk.md)**: Check if any positions violate limits
- **[Trades](trades.md)**: Review entry/exit history for closed positions

## Troubleshooting

**Q: Position shows "—" for sector or strategy**
A: Metadata may not be loaded. Check backend logs. Run seed script if in demo mode.

**Q: Equity curve is flat/empty**
A: No historical data. Run: `python scripts/backfill_history.py --years 2 --symbols sp500`

**Q: Positions show stale prices**
A: Market data feed may be disconnected. Check backend logs for IBKR or Alpha Vantage errors.

**Q: Daily P&L doesn't match my math**
A: P&L includes both realized (closed trades) and unrealized (open positions) changes. Check Trades page for closed positions.

## Best Practices

1. **Check portfolio first thing in the morning** — Review overnight changes, pre-market movers
2. **Compare to benchmark** — Is your equity curve outperforming SPY?
3. **Monitor cash levels** — Keep at least 10-15% cash for new opportunities
4. **Rebalance sectors** — If one sector grows too large, consider taking profits
5. **Review underperformers** — Don't let losers erode gains; cut losses if strategy is wrong
