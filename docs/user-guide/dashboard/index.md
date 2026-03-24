---
title: Dashboard
nav_order: 3
parent: User Guide
has_children: true
---

# Dashboard Overview

The AlphaOracle System dashboard is a web-based interface for monitoring your portfolio, strategies, risk, and trades in real time.

## Design Philosophy

The dashboard uses a dark, terminal-inspired aesthetic ("Bloomberg meets Blade Runner"):

- **Purpose-built for traders** — Dense information display, minimal chrome
- **High contrast** — Easy to read key metrics at a glance
- **Real-time** — WebSocket updates without page refreshes
- **Professional typography** — JetBrains Mono (monospace) for data, Outfit for headings

### Color System
- **Cyan (`#00e5ff`)** — Highlights, accents, primary actions
- **Gain Green (`#00e676`)** — Positive P&L, passed checks
- **Loss Red (`#ff1744`)** — Negative P&L, warnings, violations
- **Amber (`#ffab00`)** — Caution, approaching limits
- **Void/Abyss/Surface** — Background layers (darkest to lightest)

## The Four Pages

### 1. Portfolio
**Focus**: Account health and position overview

Shows total equity, daily P&L, cash balance, open positions, sector allocation, and 30-day equity curve. This is your primary view for understanding overall account performance.

**Key metrics**:
- Total equity (sum of cash + positions)
- Daily and total [P&L](../../glossary.md#pnl)
- Position count and unrealized gains/losses
- Sector exposure breakdown

[Full Portfolio documentation](portfolio.md)

### 2. Strategies
**Focus**: Strategy performance and ML signals

Ranks strategies by composite score (weighted average of [Sharpe ratio](../../glossary.md#sharpe-ratio), [Sortino ratio](../../glossary.md#sortino-ratio), [max drawdown](../../glossary.md#max-drawdown), [profit factor](../../glossary.md#profit-factor), and win rate). Shows real-time ML signal feed, feature importance, model performance metrics, and drift detection.

**Key metrics**:
- Composite score (0-100, higher is better)
- Sharpe ratio (risk-adjusted return)
- Max drawdown (largest peak-to-trough decline)
- ML model accuracy and drift (PSI)

[Full Strategies documentation](strategies.md)

### 3. Risk
**Focus**: Compliance and safety monitoring

Monitors the [PDT rule](../../glossary.md#pdt) (day trade counter), position/portfolio limits, circuit breakers, and provides the kill switch for emergency stops.

**Key metrics**:
- Day trades used (X/3 per 5 business days)
- Drawdown (percentage decline from peak equity)
- Position/portfolio limit utilization
- Circuit breaker status

[Full Risk documentation](risk.md)

### 4. Trades
**Focus**: Trade history and execution quality

Shows all trades (open and closed), pending approvals (in MANUAL_APPROVAL mode), daily trade summary, and execution quality metrics (fill rate, slippage).

**Key metrics**:
- Today's trade count and P&L
- Fill rate (percentage of orders filled)
- Trade P&L and hold duration
- Order status (pending, filled, cancelled)

[Full Trades documentation](trades.md)

<!-- DIAGRAM: Dashboard navigation flow between four pages -->

## Real-Time Updates

The dashboard maintains a persistent WebSocket connection to the backend at `/ws`. Updates are pushed automatically when:

- **Market data changes** — New prices, quotes, or bars arrive
- **Positions change** — Trades execute, positions are opened/closed
- **Signals are generated** — ML model produces new buy/sell recommendations
- **Risk status changes** — Limits are approached, circuit breakers trip
- **Orders are created** — New orders enter the pending approval queue

You'll see live animations and pulsing indicators for active data (e.g., "Open" trades have a pulsing dot).

## Navigation

Use the main navigation bar at the top of the dashboard to switch between pages. The current page is highlighted in cyan.

Keyboard shortcuts (if implemented):
- `P` — Portfolio
- `S` — Strategies
- `R` — Risk
- `T` — Trades

## Responsive Layout

The dashboard is optimized for desktop screens (1920x1080+). Smaller screens may require horizontal scrolling on tables. Mobile support is limited.

## Data Freshness

Data freshness varies by source:

| Data Type | Update Frequency |
|-----------|------------------|
| Market prices (live) | Real-time (WebSocket) |
| Portfolio positions | Every trade execution |
| ML signals | Every bar close (daily) |
| Strategy rankings | Daily (after market close) |
| Fundamental data | Weekly (Saturday 6:00 AM) |
| Model training | Weekly (Sunday 2:00 AM) |

## Performance

The dashboard is designed for low-latency updates:
- WebSocket messages are processed in <50ms
- Charts use efficient rendering (Recharts with memoization)
- Tables are virtualized for large datasets (if needed)

## Troubleshooting

**Dashboard not updating?**
- Check WebSocket connection status (browser dev tools → Network → WS)
- Verify backend is running: `curl http://localhost:8000/health`
- Check browser console for errors

**Charts showing no data?**
- Run the backfill script to load historical data
- Verify the backend has ingested recent bars

**Colors not matching this guide?**
- Clear browser cache and reload
- Check TailwindCSS is compiled: `cd web && npm run build`

## Next Steps

Dive into detailed documentation for each page:
- [Portfolio Page](portfolio.md) — Account overview and positions
- [Strategies Page](strategies.md) — Strategy rankings and ML signals
- [Risk Page](risk.md) — PDT guard and circuit breakers
- [Trades Page](trades.md) — Trade history and approvals
