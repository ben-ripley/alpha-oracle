"""Per-endpoint token-bucket rate limiter for agent API calls."""
from __future__ import annotations

import time

import structlog

logger = structlog.get_logger(__name__)


class AgentRateLimiter:
    """Redis-backed sliding-window rate limiter for agent endpoints.

    Uses a simple counter per (endpoint, hour-window) key. Returns False
    when the limit is exceeded — callers are responsible for raising HTTP 429.
    """

    def __init__(self, redis_client=None) -> None:
        self._redis = redis_client

    async def _get_redis(self):
        if self._redis is None:
            from src.core.redis import get_redis
            self._redis = await get_redis()
        return self._redis

    @staticmethod
    def _window_key(endpoint: str) -> str:
        """Redis key scoped to the current hour window."""
        window = int(time.time()) // 3600
        return f"agent:ratelimit:{endpoint}:{window}"

    async def check_rate_limit(self, endpoint: str, limit_per_hour: int) -> bool:
        """Return True if the request is within the rate limit, False if exceeded.

        Increments the counter atomically. The key expires after 2 hours to
        avoid stale accumulation across window boundaries.
        """
        redis = await self._get_redis()
        key = self._window_key(endpoint)

        count = await redis.incr(key)
        if count == 1:
            # First request in this window — set expiry
            await redis.expire(key, 7200)

        if count > limit_per_hour:
            logger.warning(
                "agent.rate_limit_exceeded",
                endpoint=endpoint,
                count=count,
                limit=limit_per_hour,
            )
            return False

        return True

    async def get_current_count(self, endpoint: str) -> int:
        """Return current request count for this endpoint in the current hour."""
        redis = await self._get_redis()
        key = self._window_key(endpoint)
        val = await redis.get(key)
        return int(val) if val else 0
