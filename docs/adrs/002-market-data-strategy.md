# ADR-002: Market Data Strategy - Free Tier Start

**Status:** Updated (Alpaca replaced by IBKR for real-time; see [ADR-010](010-ibkr-broker-switch.md))

**Decision:** IBKR (real-time via IB Gateway) + Alpha Vantage (historical/fundamentals backfill) + SEC EDGAR (filings) = $0/month to start (IBKR market data subscription required for live quotes; delayed data is free).

| Source | Data | Cost | Limitation |
|---|---|---|---|
| IBKR (IB Gateway) | Real-time trades/quotes via WebSocket; historical bars via `reqHistoricalDataAsync` | Free (delayed) / ~$10/mo (real-time subscription) | Requires IB Gateway or TWS running locally; pacing limit ~60 req/10min |
| Alpha Vantage | 20+ yr daily OHLCV, 100K+ symbols, fundamentals, 50+ technical indicators | Free (5 req/min) | Rate-limited; premium available |
| SEC EDGAR | 10-K, 10-Q, 8-K, Form 4 filings | Free | Requires XML parsing |

**Original source (Alpaca):** Removed — not available to Canadian residents. See ADR-010.

**Upgrade path:** EODHD ($20/mo) or Twelve Data ($79/mo) when intraday backtesting is needed. Intrinio ($250+/mo) for institutional-grade data.
