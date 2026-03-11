# ADR-002: Market Data Strategy - Free Tier Start

**Status:** Accepted

**Decision:** Alpaca (real-time) + Alpha Vantage (historical/fundamentals) + SEC EDGAR (filings) = $0/month to start.

| Source | Data | Cost | Limitation |
|---|---|---|---|
| Alpaca (built-in) | Real-time trades/quotes, historical bars | Free | IEX-based on free tier |
| Alpha Vantage | 20+ yr daily OHLCV, 100K+ symbols, fundamentals, 50+ technical indicators | Free (5 req/min) | Rate-limited; premium available |
| SEC EDGAR | 10-K, 10-Q, 8-K, Form 4 filings | Free | Requires XML parsing |

**Upgrade path:** EODHD ($20/mo) or Twelve Data ($79/mo) when intraday backtesting is needed. Intrinio ($250+/mo) for institutional-grade data.
