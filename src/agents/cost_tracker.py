"""LLM cost tracking, budget enforcement, and response caching."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Per-model pricing in USD per 1M tokens (input, output)
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Claude Sonnet 4 / claude-sonnet-4-20250514
    "claude-sonnet-4-20250514": (3.0, 15.0),
    # Claude Haiku 4.5
    "claude-haiku-4-5-20251001": (0.25, 1.25),
    # Bedrock model IDs
    "us.anthropic.claude-sonnet-4-20250514-v1:0": (3.0, 15.0),
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": (0.25, 1.25),
}
_DEFAULT_PRICING = (3.0, 15.0)  # fallback if model not in dict


def _model_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = _MODEL_PRICING.get(model_name, _DEFAULT_PRICING)
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


class CostTracker:
    """Tracks LLM API costs in Redis and enforces daily/monthly budgets."""

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client

    async def _get_redis(self):
        if self._redis is None:
            from src.core.redis import get_redis
            self._redis = await get_redis()
        return self._redis

    def _daily_key(self) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return f"agent:cost:daily:{date_str}"

    def _monthly_key(self) -> str:
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")
        return f"agent:cost:monthly:{month_str}"

    async def record_usage(
        self,
        agent_name: str,
        model_name: str,
        input_tokens: int,
        output_tokens: int,
        task_type: str = "",
    ):
        """Record token usage and increment cost counters. Returns LLMUsageRecord."""
        from src.core.models import LLMUsageRecord

        cost = _model_cost(model_name, input_tokens, output_tokens)

        redis = await self._get_redis()
        daily_key = self._daily_key()
        monthly_key = self._monthly_key()

        # Atomic increments — safe for concurrent requests
        await redis.incrbyfloat(daily_key, cost)
        await redis.expire(daily_key, 86400 * 2)  # keep for 2 days
        await redis.incrbyfloat(monthly_key, cost)
        await redis.expire(monthly_key, 86400 * 35)  # keep for ~35 days

        record = LLMUsageRecord(
            agent_name=agent_name,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            task_type=task_type,
        )
        logger.info(
            "agent.cost_recorded",
            agent=agent_name,
            model=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 6),
        )
        return record

    async def get_daily_cost(self) -> float:
        redis = await self._get_redis()
        val = await redis.get(self._daily_key())
        return float(val) if val else 0.0

    async def get_monthly_cost(self) -> float:
        redis = await self._get_redis()
        val = await redis.get(self._monthly_key())
        return float(val) if val else 0.0

    async def check_budget(self) -> bool:
        """Returns True if both daily and monthly budgets have remaining capacity."""
        from src.core.config import get_settings
        settings = get_settings().agent
        daily_cost = await self.get_daily_cost()
        monthly_cost = await self.get_monthly_cost()
        return daily_cost < settings.daily_budget_usd and monthly_cost < settings.monthly_budget_usd

    async def reject_if_over_budget(self) -> None:
        """Raise BudgetExceededError if daily or monthly budget is exceeded."""
        from src.core.config import get_settings
        settings = get_settings().agent
        daily_cost = await self.get_daily_cost()
        monthly_cost = await self.get_monthly_cost()

        if daily_cost >= settings.daily_budget_usd:
            raise BudgetExceededError(
                f"Daily LLM budget exceeded: ${daily_cost:.4f} >= ${settings.daily_budget_usd:.2f}"
            )
        if monthly_cost >= settings.monthly_budget_usd:
            raise BudgetExceededError(
                f"Monthly LLM budget exceeded: ${monthly_cost:.4f} >= ${settings.monthly_budget_usd:.2f}"
            )

    # ------------------------------------------------------------------
    # Response caching
    # ------------------------------------------------------------------

    @staticmethod
    def compute_prompt_hash(prompt: str, model: str, **kwargs: Any) -> str:
        """SHA-256 hash of (prompt + model + sorted kwargs) for cache keying."""
        payload = json.dumps(
            {"prompt": prompt, "model": model, **{k: kwargs[k] for k in sorted(kwargs)}},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def get_cached_response(self, prompt_hash: str) -> str | None:
        """Return cached response string or None on miss."""
        redis = await self._get_redis()
        cached = await redis.get(f"agent:cache:{prompt_hash}")
        if cached:
            logger.debug("agent.cache_hit", hash=prompt_hash[:12])
        return cached

    async def cache_response(self, prompt_hash: str, response: str) -> None:
        """Store response in Redis with TTL from agent.cache_ttl_seconds."""
        from src.core.config import get_settings
        ttl = get_settings().agent.cache_ttl_seconds
        redis = await self._get_redis()
        await redis.set(f"agent:cache:{prompt_hash}", response, ex=ttl)
        logger.debug("agent.cache_set", hash=prompt_hash[:12], ttl=ttl)

    async def get_cost_summary(self) -> dict[str, float]:
        """Return dict with daily_cost, monthly_cost, and budget info."""
        from src.core.config import get_settings
        settings = get_settings().agent
        daily_cost = await self.get_daily_cost()
        monthly_cost = await self.get_monthly_cost()
        return {
            "daily_cost_usd": daily_cost,
            "daily_budget_usd": settings.daily_budget_usd,
            "monthly_cost_usd": monthly_cost,
            "monthly_budget_usd": settings.monthly_budget_usd,
        }


class BudgetExceededError(Exception):
    """Raised when LLM API budget is exceeded."""
