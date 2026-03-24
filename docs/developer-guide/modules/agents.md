---
title: Agents Module
nav_order: 9
parent: Modules
---

# Agents Module (`src/agents/`)

## Overview

The agents module provides LLM-powered advisory capabilities via Anthropic's Claude API. Agents are **read-only**: they consume data from the feature store, data adapters, and Redis, and produce structured advisory output. They never have access to `BrokerAdapter` or any execution path.

## Module Structure

```
src/agents/
  __init__.py          # Lazy imports
  base.py              # BaseAgent ABC, AgentContext, AgentResult dataclasses
  analyst.py           # ClaudeAnalystAgent — filing analysis
  advisor.py           # TradeAdvisorAgent — trade recommendations
  briefing.py          # PortfolioReviewAgent — daily briefing
  context.py           # gather_symbol_context() utility
  cost_tracker.py      # LLM cost/budget tracking + response caching
  rate_limiter.py      # Token-bucket rate limiter (Redis-backed)
  guardrails.py        # guardrail decorator, validate_output(), LLMGuardrailsChecker
  sentiment_scorer.py  # FinBERTSentimentPipeline (optional dep)
  prompts/
    analyst.py         # Filing analysis system prompt + few-shot examples
    advisor.py         # Trade recommendation system prompt
    briefing.py        # Portfolio review system prompt
```

## BaseAgent ABC (`src/agents/base.py`)

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult: ...

    def get_token_budget(self) -> int:
        return get_settings().agent.max_input_tokens
```

`AgentContext` is a dataclass: `symbol: str | None`, `data: dict[str, Any]`.
`AgentResult` is a dataclass: `output: Any`, `tokens_used: int`, `cost_usd: float`, `metadata: dict`.

## Async Workflow Pattern

Agents use plain async Python — no LangGraph or LangChain. The advisor workflow is linear:

```
receive signal + symbol
    → gather_symbol_context()
    → check budget + rate limit
    → check response cache (agent:cache:{hash})
    → call Claude API
    → validate output (guardrails)
    → risk gate check (autonomy mode)
    → store result in Redis
    → return TradeRecommendation
```

## Model Selection (Tiered)

| Agent | Model | Rationale |
|-------|-------|-----------|
| `ClaudeAnalystAgent` | `claude-sonnet-4-20250514` | Dense financial text requires complex reasoning |
| `TradeAdvisorAgent` | `claude-haiku-4-5-20251001` | Speed and cost — many calls per day |
| `PortfolioReviewAgent` | `claude-sonnet-4-20250514` | Quality matters — one call per day |

Override via `config/settings.yaml`:
```yaml
agent:
  analyst_model: claude-sonnet-4-20250514
  advisor_model: claude-haiku-4-5-20251001
  briefing_model: claude-sonnet-4-20250514
```

## Cost Tracker (`src/agents/cost_tracker.py`)

- Per-model pricing dict (input/output tokens per 1M)
- `record_usage(agent_name, model_name, input_tokens, output_tokens) -> LLMUsageRecord`
- Redis atomic INCRBYFLOAT: `agent:cost:daily:{date}`, `agent:cost:monthly:{month}`
- `check_budget() -> bool` — True if under budget
- `reject_if_over_budget()` — raises exception if daily or monthly budget exceeded
- `get_cached_response(prompt_hash) -> str | None` and `cache_response(prompt_hash, response)`
- `compute_prompt_hash(prompt, model, **kwargs) -> str` — SHA-256

## Rate Limiter (`src/agents/rate_limiter.py`)

Redis-backed token-bucket rate limiter. Key: `agent:ratelimit:{endpoint}:{window}` where window = current hour timestamp. `check_rate_limit(endpoint, limit_per_hour) -> bool` — returns False when exceeded. Callers raise `HTTPException(429)`.

## Guardrails (`src/agents/guardrails.py`)

```python
@guardrail           # decorator for BaseAgent.run() methods
async def run(self, context):
    ...
```

The `guardrail` decorator calls `validate_output()` after every `run()`. `validate_output()` scans the output string for broker access patterns (`BrokerAdapter`, `place_order`, `submit_order`, etc.) and raises `GuardrailViolationError` if found.

`LLMGuardrailsChecker.verify()` runs a self-test (dirty result blocked, clean result passes) and stores the timestamp in `risk:guardrails:last_verified`.

## Adding a New Agent

1. Create `src/agents/my_agent.py` subclassing `BaseAgent`
2. Implement `name`, `description`, `run(context) -> AgentResult`
3. Decorate `run` with `@guardrail`
4. Add prompt template in `src/agents/prompts/my_agent.py`
5. Inject `CostTracker` and call `reject_if_over_budget()` before the Claude call
6. Add singleton to `src/api/dependencies.py`
7. Write tests in `tests/unit/test_my_agent.py` — mock Claude API responses as dicts matching Anthropic SDK format

## FinBERT Sentiment Scorer (`src/agents/sentiment_scorer.py`)

Optional dependency — requires `transformers` and `torch`. If not installed, `FinBERTSentimentPipeline` logs a warning and returns empty results. All downstream code handles empty sentiment gracefully (XGBoost treats missing features as NaN). The scheduler job checks for availability before running.
