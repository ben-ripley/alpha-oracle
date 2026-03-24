"""Circuit breakers: independent safety switches that halt trading."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis
import structlog

from src.core.config import get_settings
from src.core.models import PortfolioSnapshot
from src.core.redis import get_redis

logger = structlog.get_logger(__name__)

REDIS_CB_PREFIX = "risk:circuit_breaker:"


class CircuitBreaker:
    """Base class for individual circuit breakers."""

    name: str = "base"

    async def check(self, context: dict) -> tuple[bool, str]:
        """Return (tripped, reason). Override in subclasses."""
        return False, ""


class VIXBreaker(CircuitBreaker):
    name = "vix"

    def __init__(self, threshold: float = 35.0) -> None:
        self.threshold = threshold

    async def check(self, context: dict) -> tuple[bool, str]:
        vix = context.get("vix_level")
        if vix is None:
            return False, "VIX data unavailable (not tripped)"
        if vix > self.threshold:
            return True, f"VIX at {vix:.1f} exceeds threshold {self.threshold:.1f}"
        return False, f"VIX at {vix:.1f} (threshold {self.threshold:.1f})"


class StaleDataBreaker(CircuitBreaker):
    name = "stale_data"

    def __init__(self, max_age_seconds: int = 300) -> None:
        self.max_age_seconds = max_age_seconds

    async def check(self, context: dict) -> tuple[bool, str]:
        last_data_ts = context.get("last_data_timestamp")
        if last_data_ts is None:
            return True, "No data timestamp available — assuming stale"
        if isinstance(last_data_ts, str):
            last_data_ts = datetime.fromisoformat(last_data_ts)
        age = (datetime.now(UTC) - last_data_ts).total_seconds()
        if age > self.max_age_seconds:
            return True, f"Data is {age:.0f}s old (max {self.max_age_seconds}s)"
        return False, f"Data age {age:.0f}s (max {self.max_age_seconds}s)"


class DrawdownBreaker(CircuitBreaker):
    name = "drawdown"

    def __init__(self, threshold_pct: float = 10.0) -> None:
        self.threshold_pct = threshold_pct

    async def check(self, context: dict) -> tuple[bool, str]:
        dd = context.get("max_drawdown_pct", 0.0)
        if dd > self.threshold_pct:
            return True, f"Drawdown {dd:.1f}% exceeds {self.threshold_pct:.1f}%"
        return False, f"Drawdown {dd:.1f}% (max {self.threshold_pct:.1f}%)"


class DailyLossBreaker(CircuitBreaker):
    name = "daily_loss"

    def __init__(self, threshold_pct: float = 3.0) -> None:
        self.threshold_pct = threshold_pct

    async def check(self, context: dict) -> tuple[bool, str]:
        daily_loss = context.get("daily_pnl_pct", 0.0)
        if daily_loss < -self.threshold_pct:
            return True, f"Daily loss {daily_loss:.1f}% exceeds -{self.threshold_pct:.1f}%"
        return False, f"Daily P&L {daily_loss:.1f}% (limit -{self.threshold_pct:.1f}%)"


class ReconciliationBreaker(CircuitBreaker):
    name = "reconciliation"

    def __init__(self, max_drift_pct: float = 1.0) -> None:
        self.max_drift_pct = max_drift_pct

    async def check(self, context: dict) -> tuple[bool, str]:
        drift = context.get("reconciliation_drift_pct")
        if drift is None:
            return False, "No reconciliation data (not tripped)"
        if drift > self.max_drift_pct:
            return True, f"Position drift {drift:.2f}% exceeds {self.max_drift_pct:.2f}%"
        return False, f"Position drift {drift:.2f}% (max {self.max_drift_pct:.2f}%)"


class DeadManSwitchBreaker(CircuitBreaker):
    name = "dead_man_switch"

    def __init__(self, max_hours: int = 48) -> None:
        self.max_hours = max_hours

    async def check(self, context: dict) -> tuple[bool, str]:
        last_heartbeat = context.get("last_operator_heartbeat")
        if last_heartbeat is None:
            return True, "No operator heartbeat recorded — tripping dead man's switch"
        if isinstance(last_heartbeat, str):
            last_heartbeat = datetime.fromisoformat(last_heartbeat)
        hours = (datetime.now(UTC) - last_heartbeat).total_seconds() / 3600
        if hours > self.max_hours:
            return True, f"No operator heartbeat for {hours:.1f}h (max {self.max_hours}h)"
        return False, f"Last heartbeat {hours:.1f}h ago (max {self.max_hours}h)"


class CircuitBreakerManager:
    """Manages all circuit breakers and persists state in Redis."""

    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        settings = get_settings().risk.circuit_breakers
        self._redis_override = redis_client
        self._breakers: list[CircuitBreaker] = [
            VIXBreaker(threshold=settings.vix_threshold),
            StaleDataBreaker(max_age_seconds=settings.stale_data_seconds),
            DrawdownBreaker(threshold_pct=get_settings().risk.portfolio_limits.max_drawdown_pct),
            DailyLossBreaker(threshold_pct=get_settings().risk.portfolio_limits.max_daily_loss_pct),
            ReconciliationBreaker(max_drift_pct=settings.max_reconciliation_drift_pct),
            DeadManSwitchBreaker(max_hours=settings.dead_man_switch_hours),
        ]

    async def _redis(self) -> aioredis.Redis:
        return self._redis_override or await get_redis()

    def build_context(
        self,
        portfolio: PortfolioSnapshot | None = None,
        vix_level: float | None = None,
        last_data_timestamp: datetime | None = None,
        last_operator_heartbeat: datetime | None = None,
        reconciliation_drift_pct: float | None = None,
    ) -> dict:
        """Build the context dict needed by circuit breakers."""
        ctx: dict = {}
        if portfolio:
            ctx["max_drawdown_pct"] = portfolio.max_drawdown_pct
            ctx["daily_pnl_pct"] = portfolio.daily_pnl_pct
        if vix_level is not None:
            ctx["vix_level"] = vix_level
        if last_data_timestamp is not None:
            ctx["last_data_timestamp"] = last_data_timestamp
        if last_operator_heartbeat is not None:
            ctx["last_operator_heartbeat"] = last_operator_heartbeat
        if reconciliation_drift_pct is not None:
            ctx["reconciliation_drift_pct"] = reconciliation_drift_pct
        return ctx

    async def build_context_from_redis(
        self,
        portfolio: PortfolioSnapshot | None = None,
    ) -> dict:
        """Build context, reading persisted values (heartbeat) from Redis."""
        ctx = self.build_context(portfolio=portfolio)
        try:
            r = await self._redis()
            # Check both key formats (record_heartbeat uses REDIS_CB_PREFIX, seed uses bare key)
            for key in (f"{REDIS_CB_PREFIX}heartbeat", "circuit_breaker:heartbeat"):
                raw = await r.get(key)
                if raw:
                    ctx["last_operator_heartbeat"] = raw
                    break
        except Exception:
            pass
        return ctx

    async def check_all(
        self, context: dict
    ) -> list[tuple[str, bool, str]]:
        """Check all circuit breakers. Returns list of (name, tripped, reason)."""
        results: list[tuple[str, bool, str]] = []
        r = await self._redis()

        for breaker in self._breakers:
            tripped, reason = await breaker.check(context)
            results.append((breaker.name, tripped, reason))

            # Persist state in Redis
            state = json.dumps({
                "tripped": tripped,
                "reason": reason,
                "checked_at": datetime.now(UTC).isoformat(),
            })
            await r.set(f"{REDIS_CB_PREFIX}{breaker.name}", state, ex=600)

            if tripped:
                logger.critical(
                    "circuit_breaker_tripped",
                    breaker=breaker.name,
                    reason=reason,
                )

        return results

    async def is_any_tripped(self, context: dict) -> bool:
        """Return True if any circuit breaker is tripped."""
        results = await self.check_all(context)
        return any(tripped for _, tripped, _ in results)

    async def get_states(self) -> dict[str, dict]:
        """Get last known state of all breakers from Redis."""
        r = await self._redis()
        states = {}
        for breaker in self._breakers:
            raw = await r.get(f"{REDIS_CB_PREFIX}{breaker.name}")
            if raw:
                states[breaker.name] = json.loads(raw)
            else:
                states[breaker.name] = {"tripped": False, "reason": "No data"}
        return states

    async def record_heartbeat(self) -> None:
        """Record an operator heartbeat (extends dead man's switch)."""
        r = await self._redis()
        ts = datetime.now(UTC).isoformat()
        await r.set(f"{REDIS_CB_PREFIX}heartbeat", ts)
        logger.info("operator_heartbeat_recorded", timestamp=ts)
