# Architecture Decision Records (ADRs)

Architecture Decision Records document significant technical decisions made during the design and implementation of the stock-analysis system. Each ADR captures the context, decision, and consequences of a choice that shapes the system's architecture.

## What are ADRs?

ADRs are lightweight documents that record "architecturally significant" decisions — choices that affect:
- System structure and modularity
- Technology selection
- Performance and scalability
- Security and risk management
- Developer workflow

**Format:** Each ADR includes:
- **Status:** Accepted, Superseded, Deprecated
- **Context:** The problem or opportunity
- **Decision:** The chosen solution
- **Consequences:** Trade-offs and implications

---

## ADR Index

| # | Title | Status | Summary |
|---|-------|--------|---------|
| [001](../../specs/adrs/001-trading-platform.md) | Trading Platform - Alpaca | **Superseded** | Original broker selection (Alpaca). Superseded by ADR-010 due to Canadian residency requirement. |
| [002](../../specs/adrs/002-market-data-strategy.md) | Market Data Strategy | **Updated** | IBKR for real-time/historical, Alpha Vantage for fundamentals, SEC EDGAR for filings. Free tier start with upgrade path. |
| [003](../../specs/adrs/003-ml-model-architecture.md) | ML Model Architecture | **Accepted** | Layered approach: Phase 1 rule-based, Phase 2 XGBoost, Phase 3 FinBERT. XGBoost beats deep learning on tabular financial data. |
| [004](../../specs/adrs/004-alternative-data.md) | Alternative Data | **Accepted** | Prioritize free high-value signals (Form 4 insider trades, FINRA short interest) over expensive institutional data. |
| [005](../../specs/adrs/005-backtesting.md) | Backtesting Framework | **Accepted** | Backtrader for event-driven backtesting, VectorBT for rapid optimization. Walk-forward validation and out-of-sample holdout required. |
| [006](../../specs/adrs/006-technology-stack.md) | Technology Stack | **Accepted** | Python 3.11+, FastAPI, React, TimescaleDB, Redis, XGBoost, Docker Compose. Python-native ML/data stack for solo developer velocity. |
| [007](../../specs/adrs/007-architecture.md) | Modular Monolith Architecture | **Accepted** | Modular monolith with Redis pub/sub event bus. Avoids microservices operational overhead while maintaining clean module boundaries. |
| [008](../../specs/adrs/008-llm-agent-integration.md) | LLM/Agent Integration | **Accepted** | LLM as analyst (Phase 2) and advisor (Phase 3). Never has direct execution authority. Claude API with structured output. |
| [009](../../specs/adrs/009-risk-management.md) | Risk Management - Defense in Depth | **Accepted** | Four independent layers: position limits, portfolio limits, circuit breakers, autonomy modes. PDT guard is non-negotiable. |
| [010](../../specs/adrs/010-ibkr-broker-switch.md) | Broker Switch to IBKR | **Accepted** | Replaced Alpaca with Interactive Brokers due to Canadian availability. Three-client-ID connection model (broker, data, feed). |

---

## Key Decisions

### Broker: Interactive Brokers

**Rationale:** Canadian availability, paper trading parity with live API, WebSocket real-time data, robust TWS API.

**Trade-offs:** Steeper learning curve than Alpaca, requires IB Gateway running locally, pacing limits (~60 req/10min).

**See:** [ADR-010](../../specs/adrs/010-ibkr-broker-switch.md)

---

### Architecture: Modular Monolith

**Rationale:** Solo developer, single-node deployment, zero operational overhead. Clean module boundaries enforced by abstract interfaces. Redis pub/sub for event-driven communication.

**Trade-offs:** Cannot scale horizontally without refactoring to microservices. Acceptable for retail trading (< $1M capital).

**See:** [ADR-007](../../specs/adrs/007-architecture.md)

---

### ML: XGBoost > Deep Learning

**Rationale:** XGBoost consistently wins financial ML competitions on tabular data. Handles missing values, provides feature importance, trains in seconds. Deep learning requires 10-100x more data and is prone to overfitting.

**Trade-offs:** LSTM/Transformers may outperform on specific time-series tasks. Deferred to Phase 3 if needed.

**See:** [ADR-003](../../specs/adrs/003-ml-model-architecture.md)

---

### Data: Free Tier First

**Rationale:** IBKR + Alpha Vantage + SEC EDGAR = $0/month (or $10/mo with IBKR real-time subscription). Sufficient for strategy development and small-scale trading.

**Trade-offs:** Rate limits (5 req/min AV, ~60 req/10min IBKR). Upgrade to EODHD ($20/mo) or Twelve Data ($79/mo) for intraday data when needed.

**See:** [ADR-002](../../specs/adrs/002-market-data-strategy.md)

---

### Risk: Defense in Depth

**Rationale:** Four independent safety layers, any of which can halt trading. PDT guard enforces FINRA rules (max 3 day trades per 5 business days for accounts under $25K).

**Trade-offs:** Conservative approach may miss opportunities. Acceptable — capital preservation > aggressive growth.

**See:** [ADR-009](../../specs/adrs/009-risk-management.md)

---

### Backtesting: Walk-Forward Required

**Rationale:** Overfitting is the #1 failure mode in automated trading. Walk-forward validation and out-of-sample holdout are non-negotiable. Minimum thresholds: Sharpe > 1.0, max drawdown < 20%, 100+ trades.

**Trade-offs:** Slower development cycle (can't cherry-pick parameters). Necessary for robust strategies.

**See:** [ADR-005](../../specs/adrs/005-backtesting.md)

---

## How to Use ADRs

### When Reading

1. **Start with context** — Understand the problem being solved
2. **Review alternatives** — What other options were considered?
3. **Check status** — Is this decision still current?
4. **Understand consequences** — What are the trade-offs?

### When Proposing Changes

If you want to change a significant architectural decision:

1. **Review existing ADRs** — Has this been decided before?
2. **Draft a new ADR** — Document context, alternatives, recommendation
3. **Discuss with team** — Get feedback before implementation
4. **Update status** — Mark superseded ADRs, link to new ADR

### When Implementing

- **Follow ADR guidance** — Don't deviate without explicit justification
- **Update ADRs** — If implementation reveals issues, update the ADR
- **Cross-reference** — Link to ADRs in code comments for complex decisions

---

## ADR Evolution

### Accepted
Decision is current and should be followed.

### Updated
Core decision remains valid, but details have changed (e.g., ADR-002 switched from Alpaca to IBKR for real-time data).

### Superseded
Decision has been replaced by a newer ADR. Links to the replacement. Original ADR preserved for historical context (e.g., ADR-001 superseded by ADR-010).

### Deprecated
Decision is no longer relevant due to system changes. Preserved for historical context.

---

## Further Reading

- [Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) by Michael Nygard
- [ADR GitHub Organization](https://adr.github.io/) — Templates and tools
- [ThoughtWorks Technology Radar](https://www.thoughtworks.com/radar) — Industry trends and best practices

---

<!-- DIAGRAM: ADR timeline showing evolution of key decisions from Phase 1 MVP through Phase 2 ML to Phase 3 LLM agents -->
