"""Tests for AgentRateLimiter: limit enforcement, window behavior."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.rate_limiter import AgentRateLimiter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis(count: int = 1):
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=count)
    redis.expire = AsyncMock()
    redis.get = AsyncMock(return_value=str(count))
    return redis


# ---------------------------------------------------------------------------
# check_rate_limit
# ---------------------------------------------------------------------------

class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_first_request_allowed(self):
        redis = _make_redis(count=1)
        limiter = AgentRateLimiter(redis_client=redis)

        result = await limiter.check_rate_limit("analyses", 10)

        assert result is True

    @pytest.mark.asyncio
    async def test_request_at_limit_allowed(self):
        redis = _make_redis(count=10)
        limiter = AgentRateLimiter(redis_client=redis)

        result = await limiter.check_rate_limit("analyses", 10)

        assert result is True

    @pytest.mark.asyncio
    async def test_request_over_limit_rejected(self):
        redis = _make_redis(count=11)
        limiter = AgentRateLimiter(redis_client=redis)

        result = await limiter.check_rate_limit("analyses", 10)

        assert result is False

    @pytest.mark.asyncio
    async def test_first_request_sets_expiry(self):
        redis = _make_redis(count=1)
        limiter = AgentRateLimiter(redis_client=redis)

        await limiter.check_rate_limit("analyses", 10)

        redis.expire.assert_called_once()
        key, ttl = redis.expire.call_args[0]
        assert "analyses" in key
        assert ttl == 7200

    @pytest.mark.asyncio
    async def test_subsequent_requests_do_not_reset_expiry(self):
        redis = _make_redis(count=5)
        limiter = AgentRateLimiter(redis_client=redis)

        await limiter.check_rate_limit("analyses", 10)

        # expire should NOT be called when count > 1
        redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_different_endpoints_have_independent_limits(self):
        redis_a = _make_redis(count=11)
        redis_r = _make_redis(count=5)

        limiter_a = AgentRateLimiter(redis_client=redis_a)
        limiter_r = AgentRateLimiter(redis_client=redis_r)

        assert await limiter_a.check_rate_limit("analyses", 10) is False
        assert await limiter_r.check_rate_limit("recommendations", 50) is True

    @pytest.mark.asyncio
    async def test_high_recommendation_limit(self):
        redis = _make_redis(count=50)
        limiter = AgentRateLimiter(redis_client=redis)

        result = await limiter.check_rate_limit("recommendations", 50)
        assert result is True

    @pytest.mark.asyncio
    async def test_window_key_includes_endpoint(self):
        redis = _make_redis(count=1)
        limiter = AgentRateLimiter(redis_client=redis)

        await limiter.check_rate_limit("my_endpoint", 100)

        key_used = redis.incr.call_args[0][0]
        assert "my_endpoint" in key_used

    @pytest.mark.asyncio
    async def test_get_current_count(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value="7")
        limiter = AgentRateLimiter(redis_client=redis)

        count = await limiter.get_current_count("analyses")
        assert count == 7

    @pytest.mark.asyncio
    async def test_get_current_count_no_data_returns_zero(self):
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        limiter = AgentRateLimiter(redis_client=redis)

        count = await limiter.get_current_count("analyses")
        assert count == 0
