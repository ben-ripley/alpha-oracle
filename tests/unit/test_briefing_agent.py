"""Tests for PortfolioReviewAgent: briefing generation, portfolio summary, risk utilization."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import AgentContext
from src.agents.briefing import PortfolioReviewAgent
from src.agents.cost_tracker import BudgetExceededError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_claude_response(
    portfolio_summary: str = "Portfolio is up 2% today.",
    key_observations: list | None = None,
    market_regime: str = "BULL",
    upcoming_catalysts: list | None = None,
    suggested_exits: list | None = None,
    input_tokens: int = 800,
    output_tokens: int = 300,
) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "generate_briefing"
    tool_block.input = {
        "portfolio_summary": portfolio_summary,
        "key_observations": key_observations or ["Tech sector leading", "Low volatility"],
        "market_regime": market_regime,
        "upcoming_catalysts": upcoming_catalysts or ["AAPL earnings 2026-01-28"],
        "suggested_exits": suggested_exits or [],
    }

    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens

    response = MagicMock()
    response.content = [tool_block]
    response.usage = usage
    return response


def _make_portfolio(
    total_equity: float = 20000.0,
    cash: float = 5000.0,
    daily_pnl: float = 400.0,
    daily_pnl_pct: float = 2.0,
    total_pnl: float = 1200.0,
    total_pnl_pct: float = 6.0,
    max_drawdown_pct: float = 3.0,
) -> MagicMock:
    p = MagicMock()
    p.total_equity = total_equity
    p.cash = cash
    p.daily_pnl = daily_pnl
    p.daily_pnl_pct = daily_pnl_pct
    p.total_pnl = total_pnl
    p.total_pnl_pct = total_pnl_pct
    p.max_drawdown_pct = max_drawdown_pct
    return p


def _make_redis(*, cached: str | None = None) -> AsyncMock:
    redis = AsyncMock()

    def _get_side_effect(key):
        if key.startswith("agent:cache:"):
            return cached
        return None

    redis.get = AsyncMock(side_effect=_get_side_effect)
    redis.set = AsyncMock()
    redis.incrbyfloat = AsyncMock()
    redis.expire = AsyncMock()
    return redis


def _make_settings(
    enabled: bool = True,
    briefing_model: str = "claude-sonnet-4-20250514",
    daily_budget: float = 5.0,
    monthly_budget: float = 100.0,
    max_drawdown_pct: float = 10.0,
) -> MagicMock:
    agent_cfg = MagicMock()
    agent_cfg.enabled = enabled
    agent_cfg.briefing_model = briefing_model
    agent_cfg.max_output_tokens = 4096
    agent_cfg.temperature = 0.0
    agent_cfg.daily_budget_usd = daily_budget
    agent_cfg.monthly_budget_usd = monthly_budget
    agent_cfg.cache_ttl_seconds = 14400

    portfolio_limits = MagicMock()
    portfolio_limits.max_drawdown_pct = max_drawdown_pct
    risk_cfg = MagicMock()
    risk_cfg.portfolio_limits = portfolio_limits

    settings = MagicMock()
    settings.agent = agent_cfg
    settings.risk = risk_cfg
    return settings


def _make_context(portfolio=None, positions=None, recent_trades=None) -> AgentContext:
    return AgentContext(
        data={
            "portfolio": portfolio or _make_portfolio(),
            "positions": positions or [],
            "recent_trades": recent_trades or [],
            "market_data": {"vix": 18.5},
        }
    )


# ---------------------------------------------------------------------------
# Basic briefing generation
# ---------------------------------------------------------------------------

class TestBriefingGeneration:
    @pytest.mark.asyncio
    async def test_briefing_returned_with_all_fields(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        briefing = result.output
        assert briefing is not None
        assert briefing.portfolio_summary == "Portfolio is up 2% today."
        assert briefing.market_regime == "BULL"
        assert len(briefing.key_observations) >= 1
        assert briefing.schema_version == 1

    @pytest.mark.asyncio
    async def test_daily_pnl_from_portfolio_snapshot(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)
        portfolio = _make_portfolio(daily_pnl=350.0)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context(portfolio=portfolio))

        assert result.output.daily_pnl == pytest.approx(350.0)

    @pytest.mark.asyncio
    async def test_risk_utilization_computed_correctly(self):
        """risk_utilization = current_drawdown / max_drawdown"""
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)
        portfolio = _make_portfolio(max_drawdown_pct=5.0)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(max_drawdown_pct=10.0)),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context(portfolio=portfolio))

        assert result.output.risk_utilization == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_risk_utilization_capped_at_1(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)
        portfolio = _make_portfolio(max_drawdown_pct=15.0)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(max_drawdown_pct=10.0)),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context(portfolio=portfolio))

        assert result.output.risk_utilization <= 1.0

    @pytest.mark.asyncio
    async def test_upcoming_catalysts_preserved(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)
        catalysts = ["MSFT earnings 2026-01-29", "Fed meeting 2026-01-31"]

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(upcoming_catalysts=catalysts)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.upcoming_catalysts == catalysts

    @pytest.mark.asyncio
    async def test_suggested_exits_preserved(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)
        exits = ["TSLA: stop-loss at $180 within 2%", "META: holding 45 days, consider trimming"]

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(suggested_exits=exits)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.suggested_exits == exits

    @pytest.mark.asyncio
    async def test_briefing_date_is_today(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        today = datetime.now(UTC).date()
        assert result.output.date.date() == today


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_call(self):
        cached_data = json.dumps({
            "portfolio_summary": "Cached briefing.",
            "key_observations": ["All good"],
            "market_regime": "SIDEWAYS",
            "upcoming_catalysts": [],
            "suggested_exits": [],
        })
        redis = _make_redis(cached=cached_data)
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            result = await agent.run(_make_context())
            mock_factory.assert_not_called()

        assert result.output.portfolio_summary == "Cached briefing."
        assert result.metadata["cached"] is True

    @pytest.mark.asyncio
    async def test_cache_miss_calls_api(self):
        redis = _make_redis(cached=None)
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.metadata["cached"] is False
        assert result.tokens_used > 0


# ---------------------------------------------------------------------------
# Budget and disabled
# ---------------------------------------------------------------------------

class TestBudgetAndDisabled:
    @pytest.mark.asyncio
    async def test_disabled_returns_none(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(enabled=False)):
            result = await agent.run(_make_context())

        assert result.output is None
        assert result.metadata.get("disabled") is True

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises(self):
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=lambda key: "6.0" if "daily" in key else None)
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings(daily_budget=5.0)),
            pytest.raises(BudgetExceededError),
        ):
            await agent.run(_make_context())


# ---------------------------------------------------------------------------
# Redis storage
# ---------------------------------------------------------------------------

class TestRedisStorage:
    @pytest.mark.asyncio
    async def test_briefing_stored_with_date_key(self):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response()
            mock_factory.return_value = mock_client

            await agent.run(_make_context())

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        stored = [c for c in redis.set.call_args_list if f"agent:briefings:{today}" in str(c)]
        assert len(stored) >= 1


# ---------------------------------------------------------------------------
# Market regime
# ---------------------------------------------------------------------------

class TestMarketRegime:
    @pytest.mark.parametrize("regime", ["BULL", "BEAR", "SIDEWAYS", "HIGH_VOLATILITY"])
    @pytest.mark.asyncio
    async def test_regime_values_accepted(self, regime):
        redis = _make_redis()
        agent = PortfolioReviewAgent(redis_client=redis)

        with (
            patch("src.core.config.get_settings", return_value=_make_settings()),
            patch("src.agents.client.get_anthropic_client") as mock_factory,
        ):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = _make_claude_response(market_regime=regime)
            mock_factory.return_value = mock_client

            result = await agent.run(_make_context())

        assert result.output.market_regime == regime
