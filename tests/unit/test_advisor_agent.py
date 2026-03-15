"""Tests for TradeAdvisorAgent: workflow, recommendations, autonomy mode gating, caching."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.advisor import TradeAdvisorAgent

# Default value from AgentSettings.bounded_auto_confidence_threshold
_BOUNDED_AUTO_CONFIDENCE_THRESHOLD = 0.7
from src.agents.base import AgentContext
from src.agents.cost_tracker import BudgetExceededError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claude_response(
    action: str = "BUY",
    confidence: float = 0.75,
    rationale: str = "Strong momentum and positive sentiment.",
    supporting_signals: list | None = None,
    risk_factors: list | None = None,
    suggested_entry: float | None = 150.0,
    suggested_stop: float | None = 145.0,
    suggested_target: float | None = 165.0,
    input_tokens: int = 500,
    output_tokens: int = 150,
) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "recommend_trade"
    tool_block.input = {
        "action": action,
        "confidence": confidence,
        "rationale": rationale,
        "supporting_signals": supporting_signals or ["RSI oversold", "Volume spike"],
        "risk_factors": risk_factors or ["Earnings next week"],
        "suggested_entry": suggested_entry,
        "suggested_stop": suggested_stop,
        "suggested_target": suggested_target,
    }

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def _make_redis(*, cached: str | None = None) -> AsyncMock:
    redis = AsyncMock()

    def _get_side_effect(key):
        if key.startswith("agent:cache:"):
            return cached
        return None

    redis.get = AsyncMock(side_effect=_get_side_effect)
    redis.set = AsyncMock()
    redis.lpush = AsyncMock()
    redis.expire = AsyncMock()
    redis.incrbyfloat = AsyncMock()
    return redis


def _make_settings(
    enabled: bool = True,
    advisor_model: str = "claude-haiku-4-5-20251001",
    autonomy_mode: str = "PAPER_ONLY",
    daily_budget: float = 5.0,
    monthly_budget: float = 100.0,
) -> MagicMock:
    agent_cfg = MagicMock()
    agent_cfg.enabled = enabled
    agent_cfg.advisor_model = advisor_model
    agent_cfg.max_output_tokens = 4096
    agent_cfg.temperature = 0.0
    agent_cfg.daily_budget_usd = daily_budget
    agent_cfg.monthly_budget_usd = monthly_budget
    agent_cfg.cache_ttl_seconds = 14400
    agent_cfg.bounded_auto_confidence_threshold = _BOUNDED_AUTO_CONFIDENCE_THRESHOLD
    agent_cfg.recommendation_ttl_seconds = 604800
    agent_cfg.max_recommendations_per_symbol = 50

    risk_cfg = MagicMock()
    risk_cfg.autonomy_mode = autonomy_mode
    portfolio_limits = MagicMock()
    portfolio_limits.max_drawdown_pct = 10.0
    risk_cfg.portfolio_limits = portfolio_limits

    settings = MagicMock()
    settings.agent = agent_cfg
    settings.risk = risk_cfg
    return settings


def _make_context(symbol: str = "AAPL") -> AgentContext:
    return AgentContext(
        symbol=symbol,
        data={"_context_gathered": True, "symbol": symbol, "technical_features": {}},
    )


# ---------------------------------------------------------------------------
# Basic recommendation
# ---------------------------------------------------------------------------

class TestBasicRecommendation:
    @pytest.mark.asyncio
    async def test_buy_recommendation_returned(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(action="BUY")
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        from src.core.models import RecommendationAction
        assert result.output.action == RecommendationAction.BUY
        assert result.output.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_sell_recommendation_returned(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(action="SELL", confidence=0.8)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        from src.core.models import RecommendationAction
        assert result.output.action == RecommendationAction.SELL

    @pytest.mark.asyncio
    async def test_hold_recommendation_returned(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(action="HOLD", confidence=0.4)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        from src.core.models import RecommendationAction
        assert result.output.action == RecommendationAction.HOLD

    @pytest.mark.asyncio
    async def test_invalid_action_defaults_to_hold(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(action="STRONG_BUY")
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        from src.core.models import RecommendationAction
        assert result.output.action == RecommendationAction.HOLD

    @pytest.mark.asyncio
    async def test_confidence_clamped_to_0_1(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(confidence=1.5)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_entry_stop_target_prices_preserved(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(
                suggested_entry=150.0, suggested_stop=145.0, suggested_target=165.0
            )
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.suggested_entry == 150.0
        assert result.output.suggested_stop == 145.0
        assert result.output.suggested_target == 165.0

    @pytest.mark.asyncio
    async def test_schema_version_is_1(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.schema_version == 1


# ---------------------------------------------------------------------------
# Autonomy mode gating
# ---------------------------------------------------------------------------

class TestAutonomyModeGating:
    @pytest.mark.asyncio
    async def test_paper_only_queues_for_human_review(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(autonomy_mode="PAPER_ONLY")),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(confidence=0.95)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.human_approved is None

    @pytest.mark.asyncio
    async def test_manual_approval_queues_for_human_review(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(autonomy_mode="MANUAL_APPROVAL")),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(confidence=0.95)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.human_approved is None

    @pytest.mark.asyncio
    async def test_bounded_auto_high_confidence_auto_approves(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        high_conf = _BOUNDED_AUTO_CONFIDENCE_THRESHOLD + 0.01

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(autonomy_mode="BOUNDED_AUTONOMOUS")),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(confidence=high_conf)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.human_approved is True

    @pytest.mark.asyncio
    async def test_bounded_auto_low_confidence_queues_review(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        low_conf = _BOUNDED_AUTO_CONFIDENCE_THRESHOLD - 0.01

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(autonomy_mode="BOUNDED_AUTONOMOUS")),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(confidence=low_conf)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.human_approved is None

    @pytest.mark.asyncio
    async def test_full_autonomous_auto_approves(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(autonomy_mode="FULL_AUTONOMOUS")),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(confidence=0.4)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.human_approved is True

    @pytest.mark.asyncio
    async def test_paper_only_pending_rec_added_to_pending_list(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(autonomy_mode="PAPER_ONLY")),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            await agent.run(_make_context())

        key, value = redis.lpush.call_args[0]
        assert key == "agent:recommendations:pending"
        assert isinstance(value, str) and len(value) > 0  # UUID string


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self):
        cached_data = json.dumps({
            "action": "BUY",
            "confidence": 0.8,
            "rationale": "Cached result.",
            "supporting_signals": ["RSI"],
            "risk_factors": [],
            "suggested_entry": None,
            "suggested_stop": None,
            "suggested_target": None,
        })
        redis = _make_redis(cached=cached_data)
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            result = await agent.run(_make_context())
            mock_factory.assert_not_called()

        assert result.metadata["cached"] is True
        assert result.tokens_used == 0

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self):
        redis = _make_redis(cached=None)
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())
            mock_client.messages.create.assert_called_once()

        assert result.metadata["cached"] is False


# ---------------------------------------------------------------------------
# Budget + disabled
# ---------------------------------------------------------------------------

class TestBudgetAndDisabled:
    @pytest.mark.asyncio
    async def test_budget_exceeded_raises(self):
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=lambda key: "6.0" if "daily" in key else None)
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(daily_budget=5.0)),
            pytest.raises(BudgetExceededError),
        ):
            await agent.run(_make_context())

    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(enabled=False)):
            result = await agent.run(_make_context())

        assert result.output is None
        assert result.metadata.get("disabled") is True


# ---------------------------------------------------------------------------
# Redis storage
# ---------------------------------------------------------------------------

class TestRedisStorage:
    @pytest.mark.asyncio
    async def test_recommendation_stored_in_redis(self):
        redis = _make_redis()
        agent = TradeAdvisorAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            await agent.run(_make_context())

        # Should have stored the recommendation
        set_calls = [c for c in redis.set.call_args_list if "agent:recommendations:" in str(c)]
        assert len(set_calls) >= 1
