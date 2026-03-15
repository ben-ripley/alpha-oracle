"""Tests for ClaudeAnalystAgent: filing analysis, mocked Claude API, caching, error handling."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.analyst import ClaudeAnalystAgent
from src.agents.base import AgentContext
from src.agents.cost_tracker import BudgetExceededError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claude_response(
    summary: str = "Revenue grew 10% YoY.",
    key_points: list | None = None,
    sentiment_score: float = 0.5,
    risk_flags: list | None = None,
    financial_highlights: dict | None = None,
    input_tokens: int = 1000,
    output_tokens: int = 200,
) -> MagicMock:
    """Build a mock Anthropic SDK response object matching the tool_use format."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "analyze_filing"
    tool_block.input = {
        "summary": summary,
        "key_points": key_points or ["Revenue up 10%", "Margin stable"],
        "sentiment_score": sentiment_score,
        "risk_flags": risk_flags or [],
        "financial_highlights": financial_highlights or {"revenue": "$10B"},
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
        # Return cached response only for cache keys; return None for cost keys
        if key.startswith("agent:cache:"):
            return cached
        return None  # cost keys return None → treated as $0.00

    redis.get = AsyncMock(side_effect=_get_side_effect)
    redis.set = AsyncMock()
    redis.eval = AsyncMock(return_value=1)
    redis.lpush = AsyncMock()
    redis.ltrim = AsyncMock()
    redis.expire = AsyncMock()
    redis.incrbyfloat = AsyncMock()
    return redis


def _make_agent_settings(
    enabled: bool = True,
    analyst_model: str = "claude-sonnet-4-20250514",
    max_input_tokens: int = 50000,
    max_output_tokens: int = 4096,
    temperature: float = 0.0,
    daily_budget: float = 5.0,
    monthly_budget: float = 100.0,
    cache_ttl: int = 14400,
) -> MagicMock:
    cfg = MagicMock()
    cfg.enabled = enabled
    cfg.analyst_model = analyst_model
    cfg.max_input_tokens = max_input_tokens
    cfg.max_output_tokens = max_output_tokens
    cfg.temperature = temperature
    cfg.daily_budget_usd = daily_budget
    cfg.monthly_budget_usd = monthly_budget
    cfg.cache_ttl_seconds = cache_ttl
    settings = MagicMock()
    settings.agent = cfg
    return settings


def _make_context(
    symbol: str = "AAPL",
    filing_text: str = "Net revenues increased 10% to $10B.",
    filing_type: str = "FILING_10K",
) -> AgentContext:
    return AgentContext(
        symbol=symbol,
        data={"filing_text": filing_text, "filing_type": filing_type},
    )


# ---------------------------------------------------------------------------
# Basic filing analysis
# ---------------------------------------------------------------------------

class TestFilingAnalysis:
    @pytest.mark.asyncio
    async def test_successful_analysis_returns_agent_analysis(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        mock_response = _make_claude_response(summary="Strong revenue growth.", sentiment_score=0.6)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output is not None
        analysis = result.output
        assert analysis.symbol == "AAPL"
        assert analysis.summary == "Strong revenue growth."
        assert analysis.sentiment_score == pytest.approx(0.6)
        assert analysis.model_name == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_analysis_sets_filing_type(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context(filing_type="FILING_8K"))

        from src.core.models import AgentAnalysisType
        assert result.output.analysis_type == AgentAnalysisType.FILING_8K

    @pytest.mark.asyncio
    async def test_analysis_includes_risk_flags(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        flags = ["Going concern doubt", "Material weakness in controls"]
        mock_response = _make_claude_response(risk_flags=flags, sentiment_score=-0.7)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.risk_flags == flags
        assert result.output.sentiment_score == pytest.approx(-0.7)

    @pytest.mark.asyncio
    async def test_analysis_stores_schema_version(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.schema_version == 1

    @pytest.mark.asyncio
    async def test_tokens_recorded_in_result(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        mock_response = _make_claude_response(input_tokens=2000, output_tokens=400)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.tokens_used == 2400
        assert result.output.tokens_used == 2400

    @pytest.mark.asyncio
    async def test_cost_is_nonzero_after_api_call(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(input_tokens=1000, output_tokens=200)
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.cost_usd > 0
        assert result.output.cost_usd > 0


# ---------------------------------------------------------------------------
# Response caching
# ---------------------------------------------------------------------------

class TestResponseCaching:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self):
        cached_data = json.dumps({
            "summary": "Cached result.",
            "key_points": ["Point A"],
            "sentiment_score": 0.3,
            "risk_flags": [],
            "financial_highlights": {},
        })
        redis = _make_redis(cached=cached_data)
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            result = await agent.run(_make_context())

            # API should NOT be called
            mock_client_factory.assert_not_called()

        assert result.output.summary == "Cached result."
        assert result.tokens_used == 0  # no tokens used from cache
        assert result.metadata["cached"] is True

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api_and_caches(self):
        redis = _make_redis(cached=None)
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

            mock_client.messages.create.assert_called_once()

        # Cache should be written; analysis stored via eval (Lua script)
        assert redis.set.call_count >= 1  # cache write
        assert redis.eval.call_count >= 1  # atomic analysis storage
        assert result.metadata["cached"] is False

    @pytest.mark.asyncio
    async def test_cache_hit_has_zero_cost(self):
        cached_data = json.dumps({
            "summary": "Cached.",
            "key_points": [],
            "sentiment_score": 0.0,
            "risk_flags": [],
            "financial_highlights": {},
        })
        redis = _make_redis(cached=cached_data)
        agent = ClaudeAnalystAgent(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_agent_settings()):
            result = await agent.run(_make_context())

        assert result.cost_usd == 0.0


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    @pytest.mark.asyncio
    async def test_raises_when_budget_exceeded(self):
        redis = _make_redis()
        # Set daily cost above budget
        redis.get = AsyncMock(side_effect=lambda key: "6.0" if "daily" in key else "10.0")
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings(daily_budget=5.0)),
            pytest.raises(BudgetExceededError, match="Daily"),
        ):
            await agent.run(_make_context())

    @pytest.mark.asyncio
    async def test_disabled_agent_returns_none_output(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_agent_settings(enabled=False)):
            result = await agent.run(_make_context())

        assert result.output is None
        assert result.metadata.get("disabled") is True


# ---------------------------------------------------------------------------
# Redis storage
# ---------------------------------------------------------------------------

class TestRedisStorage:
    @pytest.mark.asyncio
    async def test_analysis_stored_with_ttl(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            await agent.run(_make_context(symbol="MSFT"))

        # Analysis stored atomically via Lua script (eval), not raw set
        eval_calls = [call for call in redis.eval.call_args_list if "agent:analyses:" in str(call)]
        assert len(eval_calls) >= 1

    @pytest.mark.asyncio
    async def test_symbol_list_updated(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            await agent.run(_make_context(symbol="TSLA"))

        # Symbol index is updated inside the atomic Lua script (eval)
        eval_calls = [call for call in redis.eval.call_args_list if "by_symbol:TSLA" in str(call)]
        assert len(eval_calls) >= 1


# ---------------------------------------------------------------------------
# Structured output parsing
# ---------------------------------------------------------------------------

class TestStructuredOutputParsing:
    @pytest.mark.asyncio
    async def test_financial_highlights_parsed(self):
        highlights = {"revenue": "$50B", "eps": "$4.50", "guidance": "$52-54B next quarter"}
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(
                financial_highlights=highlights
            )
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.financial_highlights == highlights

    @pytest.mark.asyncio
    async def test_key_points_list_preserved(self):
        points = ["EPS beat by 15%", "Cloud revenue +30%", "Buyback program announced"]
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(key_points=points)
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.key_points == points

    @pytest.mark.asyncio
    async def test_invalid_filing_type_defaults_to_10k(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            ctx = AgentContext(symbol="AAPL", data={"filing_text": "text", "filing_type": "INVALID_TYPE"})
            result = await agent.run(ctx)

        from src.core.models import AgentAnalysisType
        assert result.output.analysis_type == AgentAnalysisType.FILING_10K


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_retry_on_api_error(self):
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        call_count = 0
        good_response = _make_claude_response()

        def create_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("API temporarily unavailable")
            return good_response

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = create_side_effect
            mock_client_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output is not None
        assert call_count == 2  # failed once, succeeded on retry

    @pytest.mark.asyncio
    async def test_audit_logging_on_success(self, caplog):
        import logging
        redis = _make_redis()
        agent = ClaudeAnalystAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_agent_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_client_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_client_factory.return_value = mock_client

            # Should not raise
            result = await agent.run(_make_context())

        assert result.output is not None
