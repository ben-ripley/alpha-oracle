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
    """Decorator for BaseAgent.run() methods that validates output is advisory-only."""

    @functools.wraps(func)
    async def wrapper(self, context, *args, **kwargs) -> AgentResult:
        result: AgentResult = await func(self, context, *args, **kwargs)
        return validate_output(result)

    return wrapper


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
