"""Tests for CostTracker: cost calculation, budget enforcement, response caching."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.cost_tracker import BudgetExceededError, CostTracker, _model_cost

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis(*, daily_val=None, monthly_val=None, cached=None):
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=lambda key: (
        daily_val if "daily" in key else
        monthly_val if "monthly" in key else
        cached
    ))
    redis.set = AsyncMock()
    redis.incrbyfloat = AsyncMock()
    redis.expire = AsyncMock()
    return redis


def _make_settings(daily_budget=5.0, monthly_budget=100.0, cache_ttl=14400):
    agent = MagicMock()
    agent.daily_budget_usd = daily_budget
    agent.monthly_budget_usd = monthly_budget
    agent.cache_ttl_seconds = cache_ttl
    settings = MagicMock()
    settings.agent = agent
    return settings


# ---------------------------------------------------------------------------
# _model_cost unit tests
# ---------------------------------------------------------------------------

class TestModelCost:
    def test_sonnet_cost(self):
        # $3/1M input, $15/1M output
        cost = _model_cost("claude-sonnet-4-20250514", 1_000_000, 0)
        assert cost == pytest.approx(3.0)

    def test_haiku_cost(self):
        # $0.25/1M input, $1.25/1M output
        cost = _model_cost("claude-haiku-4-5-20251001", 1_000_000, 0)
        assert cost == pytest.approx(0.25)

    def test_output_tokens_cost(self):
        cost = _model_cost("claude-sonnet-4-20250514", 0, 1_000_000)
        assert cost == pytest.approx(15.0)

    def test_combined_tokens(self):
        cost = _model_cost("claude-sonnet-4-20250514", 1000, 500)
        expected = (1000 * 3.0 + 500 * 15.0) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_uses_default(self):
        cost = _model_cost("unknown-model", 1_000_000, 0)
        assert cost == pytest.approx(0.25)  # fallback to haiku tier (cheapest known model)

    def test_unknown_model_fallback_not_at_sonnet_rate(self):
        """Unknown cheap models should not be overcharged at Sonnet pricing."""
        cost = _model_cost("some-unknown-cheap-model", 1_000_000, 0)
        assert cost < 3.0  # must not use Sonnet-tier $3/M input pricing

    def test_zero_tokens(self):
        assert _model_cost("claude-sonnet-4-20250514", 0, 0) == 0.0


# ---------------------------------------------------------------------------
# CostTracker.record_usage
# ---------------------------------------------------------------------------

class TestRecordUsage:
    @pytest.mark.asyncio
    async def test_record_usage_increments_counters(self):
        redis = _make_redis()
        tracker = CostTracker(redis_client=redis)

        record = await tracker.record_usage("analyst", "claude-sonnet-4-20250514", 1000, 200)

        assert record.agent_name == "analyst"
        assert record.model_name == "claude-sonnet-4-20250514"
        assert record.input_tokens == 1000
        assert record.output_tokens == 200
        assert record.cost_usd > 0

        assert redis.incrbyfloat.call_count == 2  # daily + monthly

    @pytest.mark.asyncio
    async def test_record_usage_returns_llm_usage_record(self):
        redis = _make_redis()
        tracker = CostTracker(redis_client=redis)

        record = await tracker.record_usage("advisor", "claude-haiku-4-5-20251001", 500, 100, "recommendation")

        assert record.task_type == "recommendation"
        assert record.cost_usd == pytest.approx(_model_cost("claude-haiku-4-5-20251001", 500, 100))


# ---------------------------------------------------------------------------
# Budget checks
# ---------------------------------------------------------------------------

class TestBudgetChecks:
    @pytest.mark.asyncio
    async def test_check_budget_under_limit_returns_true(self):
        redis = _make_redis(daily_val="1.0", monthly_val="10.0")
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(daily_budget=5.0, monthly_budget=100.0)):
            result = await tracker.check_budget()

        assert result is True

    @pytest.mark.asyncio
    async def test_check_budget_daily_exceeded_returns_false(self):
        redis = _make_redis(daily_val="5.5", monthly_val="10.0")
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(daily_budget=5.0)):
            result = await tracker.check_budget()

        assert result is False

    @pytest.mark.asyncio
    async def test_check_budget_monthly_exceeded_returns_false(self):
        redis = _make_redis(daily_val="1.0", monthly_val="105.0")
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(monthly_budget=100.0)):
            result = await tracker.check_budget()

        assert result is False

    @pytest.mark.asyncio
    async def test_reject_if_over_budget_daily_raises(self):
        redis = _make_redis(daily_val="6.0", monthly_val="10.0")
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(daily_budget=5.0)):
            with pytest.raises(BudgetExceededError, match="Daily"):
                await tracker.reject_if_over_budget()

    @pytest.mark.asyncio
    async def test_reject_if_over_budget_monthly_raises(self):
        redis = _make_redis(daily_val="1.0", monthly_val="110.0")
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(monthly_budget=100.0)):
            with pytest.raises(BudgetExceededError, match="Monthly"):
                await tracker.reject_if_over_budget()

    @pytest.mark.asyncio
    async def test_reject_if_under_budget_does_not_raise(self):
        redis = _make_redis(daily_val="1.0", monthly_val="10.0")
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings()):
            await tracker.reject_if_over_budget()  # Should not raise

    @pytest.mark.asyncio
    async def test_no_redis_data_treated_as_zero(self):
        redis = _make_redis(daily_val=None, monthly_val=None)
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings()):
            result = await tracker.check_budget()

        assert result is True


# ---------------------------------------------------------------------------
# Response caching
# ---------------------------------------------------------------------------

class TestResponseCaching:
    def test_compute_prompt_hash_deterministic(self):
        h1 = CostTracker.compute_prompt_hash("hello", "claude-sonnet-4-20250514", temperature=0)
        h2 = CostTracker.compute_prompt_hash("hello", "claude-sonnet-4-20250514", temperature=0)
        assert h1 == h2

    def test_compute_prompt_hash_different_inputs(self):
        h1 = CostTracker.compute_prompt_hash("hello", "claude-sonnet-4-20250514")
        h2 = CostTracker.compute_prompt_hash("world", "claude-sonnet-4-20250514")
        assert h1 != h2

    def test_compute_prompt_hash_different_models(self):
        h1 = CostTracker.compute_prompt_hash("hello", "claude-sonnet-4-20250514")
        h2 = CostTracker.compute_prompt_hash("hello", "claude-haiku-4-5-20251001")
        assert h1 != h2

    def test_compute_prompt_hash_is_sha256(self):
        h = CostTracker.compute_prompt_hash("test", "model")
        assert len(h) == 64  # SHA-256 hex = 64 chars

    @pytest.mark.asyncio
    async def test_get_cached_response_hit(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value='{"result": "cached"}')
        tracker = CostTracker(redis_client=redis)

        result = await tracker.get_cached_response("abc123")
        assert result == '{"result": "cached"}'

    @pytest.mark.asyncio
    async def test_get_cached_response_miss(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        tracker = CostTracker(redis_client=redis)

        result = await tracker.get_cached_response("abc123")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_response_stores_with_ttl(self):
        redis = AsyncMock()
        tracker = CostTracker(redis_client=redis)

        with patch("src.core.config.get_settings", return_value=_make_settings(cache_ttl=14400)):
            await tracker.cache_response("abc123", '{"result": "data"}')

        redis.set.assert_called_once_with(
            "agent:cache:abc123",
            '{"result": "data"}',
            ex=14400,
        )
