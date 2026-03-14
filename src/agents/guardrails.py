"""LLM safety guardrails: prevents agents from accessing broker or taking direct actions."""
from __future__ import annotations

import functools
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

from src.agents.base import AgentResult

logger = structlog.get_logger(__name__)

# Patterns that must not appear in agent output — signals attempted broker access
_BROKER_ACCESS_PATTERNS = [
    "BrokerAdapter",
    "place_order",
    "submit_order",
    "cancel_order",
    "get_portfolio",
    "execute_trade",
]


def guardrail(func: Callable) -> Callable:
    """Decorator for BaseAgent.run() methods that validates output is advisory-only.

    If the output violates guardrails, any stored data is cleaned up from Redis
    before re-raising the error.
    """

    @functools.wraps(func)
    async def wrapper(self, context, *args, **kwargs) -> AgentResult:
        result: AgentResult = await func(self, context, *args, **kwargs)
        try:
            return validate_output(result)
        except GuardrailViolationError:
            # Clean up any data stored during run() to avoid poisoned cache
            await _cleanup_stored_output(self, result)
            raise

    return wrapper


async def _cleanup_stored_output(agent: Any, result: AgentResult) -> None:
    """Best-effort removal of data stored by an agent whose output failed guardrails."""
    try:
        redis_client = await agent._get_redis() if hasattr(agent, "_get_redis") else None
        if redis_client is None:
            return

        output = result.output
        if output is None:
            return

        # Remove by known key patterns based on output model type
        model_type = type(output).__name__
        if model_type == "AgentAnalysis" and hasattr(output, "symbol"):
            # Analyses are stored under agent:analyses:{id} — we don't have the ID,
            # but the most recent entry on the by_symbol list is the one we just stored
            symbol_key = f"agent:analyses:by_symbol:{output.symbol}"
            bad_id = await redis_client.lpop(symbol_key)
            if bad_id:
                await redis_client.delete(f"agent:analyses:{bad_id}")
        elif model_type == "TradeRecommendation":
            # Recent recommendation is at the head of the recent list
            bad_id = await redis_client.lpop("agent:recommendations:recent")
            if bad_id:
                await redis_client.delete(f"agent:recommendations:{bad_id}")
        elif model_type == "DailyBriefing" and hasattr(output, "date"):
            date_str = output.date.strftime("%Y-%m-%d") if hasattr(output.date, "strftime") else str(output.date)
            await redis_client.delete(f"agent:briefings:{date_str}")

        logger.warning("agent.guardrail_cleanup_complete", model_type=model_type)
    except Exception as exc:
        logger.error("agent.guardrail_cleanup_failed", error=str(exc))


def validate_output(result: AgentResult) -> AgentResult:
    """Verify AgentResult output contains no broker access patterns.

    Raises GuardrailViolationError if any restricted patterns are found.
    """
    output_str = str(result.output) if result.output is not None else ""

    for pattern in _BROKER_ACCESS_PATTERNS:
        if pattern in output_str:
            logger.error(
                "agent.guardrail_violation",
                pattern=pattern,
                output_preview=output_str[:200],
            )
            raise GuardrailViolationError(
                f"Agent output contains restricted pattern '{pattern}'. "
                "Agents must be advisory-only and cannot access broker interfaces."
            )

    return result


class LLMGuardrailsChecker:
    """Verifies guardrail integrity and records last verification timestamp in Redis."""

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client

    async def _get_redis(self):
        if self._redis is None:
            from src.core.redis import get_redis
            self._redis = await get_redis()
        return self._redis

    async def verify(self) -> bool:
        """Run self-test of guardrails and store verification timestamp.

        Tests that:
        1. A result containing a broker access pattern is rejected.
        2. A clean result passes through.

        Returns True if guardrails are working correctly.
        """
        # Test 1: broker pattern should be blocked
        dirty_result = AgentResult(output="You should call BrokerAdapter.place_order()")
        try:
            validate_output(dirty_result)
            # Should have raised — guardrails are broken
            logger.error("agent.guardrails_self_test_failed", reason="dirty result not blocked")
            return False
        except GuardrailViolationError:
            pass  # Expected

        # Test 2: clean result should pass
        clean_result = AgentResult(output={"recommendation": "BUY", "rationale": "Strong momentum"})
        try:
            validate_output(clean_result)
        except GuardrailViolationError:
            logger.error("agent.guardrails_self_test_failed", reason="clean result was blocked")
            return False

        # Record verification timestamp
        redis = await self._get_redis()
        timestamp = datetime.now(timezone.utc).isoformat()
        await redis.set("risk:guardrails:last_verified", timestamp)
        logger.info("agent.guardrails_verified", timestamp=timestamp)
        return True

    async def get_last_verified(self) -> str | None:
        """Return ISO timestamp of last successful verification, or None."""
        redis = await self._get_redis()
        return await redis.get("risk:guardrails:last_verified")


class GuardrailViolationError(Exception):
    """Raised when an agent output violates safety guardrails."""
