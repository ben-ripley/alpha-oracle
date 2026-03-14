"""Tests for LLM safety guardrails."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.agents.base import AgentResult
from src.agents.guardrails import (
    GuardrailViolationError,
    LLMGuardrailsChecker,
    guardrail,
    validate_output,
)


# ---------------------------------------------------------------------------
# validate_output
# ---------------------------------------------------------------------------

class TestValidateOutput:
    def test_clean_output_passes(self):
        result = AgentResult(output={"action": "BUY", "confidence": 0.8})
        out = validate_output(result)
        assert out.output == {"action": "BUY", "confidence": 0.8}

    def test_string_output_passes(self):
        result = AgentResult(output="Strong momentum, recommend holding position.")
        out = validate_output(result)
        assert out is result

    def test_broker_adapter_blocked(self):
        result = AgentResult(output="Call BrokerAdapter to place order")
        with pytest.raises(GuardrailViolationError, match="BrokerAdapter"):
            validate_output(result)

    def test_place_order_blocked(self):
        result = AgentResult(output="You should use place_order() to execute")
        with pytest.raises(GuardrailViolationError, match="place_order"):
            validate_output(result)

    def test_submit_order_blocked(self):
        result = AgentResult(output="submit_order with symbol AAPL")
        with pytest.raises(GuardrailViolationError, match="submit_order"):
            validate_output(result)

    def test_cancel_order_blocked(self):
        result = AgentResult(output="cancel_order if price drops")
        with pytest.raises(GuardrailViolationError, match="cancel_order"):
            validate_output(result)

    def test_execute_trade_blocked(self):
        result = AgentResult(output="execute_trade at market open")
        with pytest.raises(GuardrailViolationError, match="execute_trade"):
            validate_output(result)

    def test_get_portfolio_blocked(self):
        result = AgentResult(output="Use get_portfolio to check positions")
        with pytest.raises(GuardrailViolationError, match="get_portfolio"):
            validate_output(result)

    def test_none_output_passes(self):
        result = AgentResult(output=None)
        out = validate_output(result)
        assert out.output is None

    def test_dict_output_with_analysis_passes(self):
        result = AgentResult(output={
            "summary": "Strong earnings growth",
            "key_points": ["Revenue up 15%", "EPS beat by 10%"],
            "sentiment_score": 0.7,
        })
        out = validate_output(result)
        assert out is result

    @pytest.mark.parametrize("bad_text", [
        "BrokerAdapter",
        "place_order",
        "submit_order",
        "cancel_order",
        "execute_trade",
        "get_portfolio",
    ])
    def test_all_restricted_patterns_blocked(self, bad_text):
        result = AgentResult(output=f"I would {bad_text} here")
        with pytest.raises(GuardrailViolationError):
            validate_output(result)


# ---------------------------------------------------------------------------
# guardrail decorator
# ---------------------------------------------------------------------------

class TestGuardrailDecorator:
    @pytest.mark.asyncio
    async def test_decorator_allows_clean_output(self):
        class FakeAgent:
            @guardrail
            async def run(self, context):
                return AgentResult(output={"summary": "all good"})

        agent = FakeAgent()
        result = await agent.run(None)
        assert result.output == {"summary": "all good"}

    @pytest.mark.asyncio
    async def test_decorator_blocks_broker_access(self):
        class FakeAgent:
            @guardrail
            async def run(self, context):
                return AgentResult(output="please call BrokerAdapter.place_order()")

        agent = FakeAgent()
        with pytest.raises(GuardrailViolationError):
            await agent.run(None)

    @pytest.mark.asyncio
    async def test_decorator_preserves_metadata(self):
        class FakeAgent:
            @guardrail
            async def run(self, context):
                return AgentResult(output="clean", tokens_used=100, cost_usd=0.001)

        agent = FakeAgent()
        result = await agent.run(None)
        assert result.tokens_used == 100
        assert result.cost_usd == 0.001


# ---------------------------------------------------------------------------
# LLMGuardrailsChecker
# ---------------------------------------------------------------------------

class TestLLMGuardrailsChecker:
    @pytest.mark.asyncio
    async def test_verify_returns_true_and_stores_timestamp(self):
        redis = AsyncMock()
        checker = LLMGuardrailsChecker(redis_client=redis)

        result = await checker.verify()

        assert result is True
        redis.set.assert_called_once()
        key = redis.set.call_args[0][0]
        assert key == "risk:guardrails:last_verified"

    @pytest.mark.asyncio
    async def test_get_last_verified_returns_none_when_unset(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        checker = LLMGuardrailsChecker(redis_client=redis)

        result = await checker.get_last_verified()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_verified_returns_stored_timestamp(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="2026-03-13T08:00:00+00:00")
        checker = LLMGuardrailsChecker(redis_client=redis)

        result = await checker.get_last_verified()
        assert "2026-03-13" in result

    @pytest.mark.asyncio
    async def test_verify_self_test_logic(self):
        """verify() must catch dirty results and pass clean ones."""
        redis = AsyncMock()
        checker = LLMGuardrailsChecker(redis_client=redis)

        # Should pass — guardrails work as expected
        assert await checker.verify() is True
