# ADR-008: LLM/Agent Integration - Read-First, Advise Later

**Status:** Accepted

**Decision:** LLM as analyst (Phase 2), LLM as advisor (Phase 3). LLM never has direct execution authority.

| Phase | LLM Role | Risk Level |
|---|---|---|
| Phase 2 | Analyst: summarize filings, extract sentiment, explain signals | Low (read-only) |
| Phase 3 | Advisor: synthesize signals into recommendations, daily briefings | Medium (human decides) |
| Future | Bounded executor: within strict risk limits, after extensive validation | High (requires proven track record) |

**Implementation:** Claude API with structured output (tool use / JSON mode). LangGraph workflows for multi-step analysis. All outputs are one feature among many -- never the sole decision driver. Temperature=0, token budget limits, all outputs logged and auditable.

**Estimated cost:** $10-50/month (100-500 analysis requests/day at ~2K tokens each).
