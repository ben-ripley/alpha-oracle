# ADR-009: Risk Management - Defense in Depth

**Status:** Accepted

**Decision:** Four independent layers, any of which can halt trading.

**Layer 1 - Position Limits:** Max 5% per position, 25% per sector, 2% stop-loss, no penny stocks (<$5), no leverage by default.

**Layer 2 - Portfolio Limits:** Max 10% drawdown (halts trading), 3% max daily loss, 20 max positions, 50 max daily trades, 10% min cash reserve. **PDT guard: max 3 day trades per 5 business days** (hard-enforced, cannot be overridden while account is under $25K).

**Layer 3 - Circuit Breakers:** Kill switch (CLI/Telegram/API), VIX threshold (>35 halts trading), stale data detection, position reconciliation every 5 min, dead man's switch (48hr operator heartbeat).

**Layer 4 - Autonomy Modes:**

| Mode | Behavior | Transition Requirement |
|---|---|---|
| `PAPER_ONLY` | All trades on paper account | Default starting mode |
| `MANUAL_APPROVAL` | Every trade needs human OK via Telegram | 30 days paper + Sharpe > 1.0 |
| `BOUNDED_AUTONOMOUS` | Auto-trades within limits; large/risky trades need approval | 30 days manual + positive returns |
| `FULL_AUTONOMOUS` | All trades auto within Layers 1-3 | 60 days bounded + profitable |

Mode transitions require explicit operator action and cannot be changed programmatically.
