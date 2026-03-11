# ADR-001: Trading Platform - Alpaca

**Status:** Accepted

**Decision:** Alpaca as primary broker, Interactive Brokers as upgrade path.

| Criteria | Alpaca (chosen) | Interactive Brokers (alternative) |
|---|---|---|
| API quality | Excellent Python SDK, REST + WebSocket | Powerful but complex TWS API |
| Commission | $0 US equities | $0 on IBKR Lite |
| Paper trading | Built-in, identical API surface | Available but different workflow |
| Latency | ~1.5ms, 99.99% uptime | ~1-2ms |
| Learning curve | Low | High |
| Order types | Market, limit, stop, bracket, OCO | 100+ types, algos |

**Why Alpaca:** Zero commissions, identical paper/live API (same code runs in both modes), excellent docs, FINRA/SIPC regulated. The system abstracts the broker behind a `BrokerAdapter` interface so we can swap to IBKR later if needed.

**Why not others:** Robinhood, TD/Schwab, E*TRADE, Webull all have limited or undocumented APIs unsuitable for automated trading.
