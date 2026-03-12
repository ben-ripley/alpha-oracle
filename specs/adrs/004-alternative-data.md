# ADR-004: Alternative Data - High-Value Free Sources First

**Status:** Accepted

**Decision:** Prioritize free, academically-validated signals over expensive institutional data.

**Phase 2 (free, high-value):**
- SEC Form 4 insider transactions - one of the strongest documented signals in finance
- Short interest data (FINRA) - crowding/distress indicator

**Phase 3 (low-cost, proven):**
- Analyst estimate revisions (Alpha Vantage)
- Options flow / unusual activity ($0-30/mo)
- News sentiment via FinBERT (compute cost only)
- Google Trends (free, experimental)

**Not viable at retail scale:** Satellite imagery, credit card data, web traffic, app downloads ($10K+/month, institutional only).
