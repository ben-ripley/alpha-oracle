# LLM Agents

## Overview

Alpha Oracle's Phase 3 adds three LLM-powered agents built on Anthropic's Claude API. These agents are **advisory only** — they read data and produce analysis, but they never place orders or access the broker directly. Every recommendation must pass through the standard risk pipeline before execution.

## The Three Agents

### ClaudeAnalystAgent

Analyzes SEC filings (10-K, 10-Q, 8-K) and earnings summaries. Given filing text, it returns a structured `AgentAnalysis` with:
- Executive summary
- Key points (bulleted)
- Sentiment score (-1 to +1)
- Risk flags
- Financial highlights

**Model:** `claude-sonnet-4-20250514` (complex reasoning required for dense financial text)

### TradeAdvisorAgent

Produces trade recommendations for a given signal + symbol. Workflow:
1. Gather context (feature store values, sentiment scores, insider data)
2. Call Claude with structured output
3. Pass through risk gate (checks autonomy mode)
4. Return `TradeRecommendation` with action, confidence, rationale, suggested entry/stop/target

**Model:** `claude-haiku-4-5-20251001` (speed and cost matter — many recommendations per day)

In `MANUAL_APPROVAL` mode, recommendations are queued for human review. In `BOUNDED_AUTONOMOUS` mode, high-confidence recommendations auto-approve if risk engine approves.

### PortfolioReviewAgent

Generates a daily portfolio briefing each morning at 8am ET. Input: portfolio snapshot, recent trades, market data. Output: `DailyBriefing` with P&L summary, risk utilization, upcoming catalysts, suggested exits, and market regime.

**Model:** `claude-sonnet-4-20250514` (quality matters — one call per day)

## Cost Management

All Claude API calls are tracked in Redis:
- `agent:cost:daily:{date}` — daily spend counter
- `agent:cost:monthly:{month}` — monthly spend counter

Defaults: `$5/day`, `$100/month`. If a budget is exceeded, the system rejects new agent calls until the next period. Configure via `agent.daily_budget_usd` and `agent.monthly_budget_usd` in `config/settings.yaml`.

### Response Caching

Before calling Claude, the system hashes the prompt + model + key parameters (SHA-256) and checks `agent:cache:{hash}` in Redis. Cache hits return immediately without an API call. Default TTL: 4 hours (`agent.cache_ttl_seconds`). This prevents duplicate charges when the same analysis is triggered by both scheduled jobs and manual requests.

## Rate Limiting

- Filing analyses: 10 per hour (configurable via `agent.rate_limit_analyses_per_hour`)
- Trade recommendations: 50 per hour (configurable via `agent.rate_limit_recommendations_per_hour`)

Exceeding a rate limit returns HTTP 429. Rate limits are enforced independently of budget — the rate limiter is the first line of defense.

## Disabling Agents

Set `SA_AGENT__ENABLED=false` (environment variable) or `agent.enabled: false` in `config/settings.yaml`. When disabled:
- All `/api/agent/*` endpoints return HTTP 503
- Scheduler jobs (`daily_sentiment_job`, `daily_briefing_job`) skip immediately
- The system continues to function normally using Phase 1/2 signals only
- The Agent dashboard page shows a "Disabled" banner

## Limitations

- Agents cannot place orders, cancel orders, or access portfolio positions directly
- Agent output is data only — all actions require the risk pipeline
- Claude API requires `SA_ANTHROPIC_API_KEY` to be set (or `SA_AGENT__PROVIDER=bedrock` with AWS credentials)
- FinBERT sentiment scoring requires `transformers` and `torch` to be installed (optional — graceful fallback to empty sentiment features)
