# Runbook: LLM Agent Operations

## Monitoring Agent Costs

### Check current spend
```bash
# Daily cost (replace date)
redis-cli GET agent:cost:daily:2026-03-13

# Monthly cost (replace month)
redis-cli GET agent:cost:monthly:2026-03
```

### Check via API (system must be running)
```bash
curl http://localhost:8000/api/agent/cost-summary
```

Returns daily spend, monthly spend, budget limits, and per-model breakdown.

### Budget thresholds
Default: $5/day, $100/month. Override in `config/settings.yaml`:
```yaml
agent:
  daily_budget_usd: 5.0
  monthly_budget_usd: 100.0
```

When a budget is exceeded, new agent API calls return HTTP 402 and log `agent.budget_exceeded`. The system continues operating on Phase 1/2 signals.

---

## Disabling Agents

Set env var and restart backend:
```bash
export SA_AGENT__ENABLED=false
./scripts/restart-backend.sh
```

Or edit `config/settings.yaml`:
```yaml
agent:
  enabled: false
```

Effects:
- All `/api/agent/*` endpoints return HTTP 503 `{"detail": "Agent module is disabled"}`
- `daily_sentiment_job` and `daily_briefing_job` skip at the start of each run
- Existing cached data in Redis remains accessible
- System operates normally using Phase 1/2 ML signals

---

## Checking Guardrail Status

```bash
# Check last verified timestamp
redis-cli GET risk:guardrails:last_verified

# Via API
curl http://localhost:8000/api/risk/guardrails/status
```

If not verified within 24 hours, the system blocks transitions to `FULL_AUTONOMOUS`.

### Re-verify guardrails
```bash
curl -X POST http://localhost:8000/api/risk/guardrails/verify
```

Expected response: `{"verified": true, "timestamp": "..."}`

---

## Handling "FinBERT not available"

If you see `WARNING: FinBERT not available — sentiment features will be empty`, `transformers` and/or `torch` are not installed.

**To install (optional):**
```bash
.venv/bin/pip install transformers torch --index-url https://download.pytorch.org/whl/cpu
```

**To ignore:** no action needed. XGBoost handles NaN sentiment features natively. Prediction quality is slightly degraded but the system remains fully operational.

---

## Clearing Response Cache

To force fresh Claude API calls (e.g., after a prompt change):
```bash
# Clear all agent response cache keys
redis-cli --scan --pattern 'agent:cache:*' | xargs redis-cli DEL
```

---

## Checking Autonomy Mode Readiness

```bash
curl http://localhost:8000/api/risk/autonomy-mode/readiness
```

Returns current mode, days in mode, and a checklist for the next mode upgrade including Sharpe ratio, drawdown, and guardrail status.

---

## Viewing Recent Agent Analyses

```bash
# List analyses for a symbol
redis-cli LRANGE agent:analyses:by_symbol:AAPL 0 9

# Get a specific analysis
redis-cli GET agent:analyses:{id}
```

Via API:
```bash
curl "http://localhost:8000/api/agent/analyses?symbol=AAPL&limit=10"
```

---

## Viewing Pending Recommendations

```bash
# List pending recommendation IDs
redis-cli SMEMBERS agent:recommendations:pending
```

Via API:
```bash
curl http://localhost:8000/api/agent/recommendations?status=pending
```

Approve or reject via:
```bash
curl -X POST http://localhost:8000/api/agent/recommendations/{id}/approve
curl -X POST http://localhost:8000/api/agent/recommendations/{id}/reject
```

---

## Triggering Agent Jobs Manually

```bash
# Trigger sentiment scoring (after market close)
curl -X POST http://localhost:8000/api/system/scheduler/trigger/daily_sentiment

# Trigger morning briefing
curl -X POST http://localhost:8000/api/system/scheduler/trigger/daily_briefing
```

---

## Viewing Autonomy Transition Log

```bash
# Full audit log of mode transitions
redis-cli LRANGE risk:autonomy:transition_log 0 -1

# When current mode was activated
redis-cli GET risk:autonomy:mode_since
```
