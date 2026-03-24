"""Kill switch: emergency halt of all trading activity."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis
import structlog

from src.core.config import get_settings
from src.core.redis import get_redis

logger = structlog.get_logger(__name__)

REDIS_KS_KEY = "risk:kill_switch"
REDIS_KS_LOG_KEY = "risk:kill_switch:log"


class KillSwitch:
    """Emergency kill switch persisted in Redis (fast) and logged for audit.

    When active, ALL trading is halted — no new orders, and existing open
    orders should be cancelled by the caller.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis | None = None,
        broker_adapter=None,
    ) -> None:
        self._redis_override = redis_client
        self._broker = broker_adapter
        self._config = get_settings().risk.kill_switch

    async def _redis(self) -> aioredis.Redis:
        return self._redis_override or await get_redis()

    async def activate(self, reason: str) -> None:
        """Activate the kill switch. This halts all trading immediately."""
        r = await self._redis()
        now = datetime.now(UTC)

        state = json.dumps({
            "active": True,
            "reason": reason,
            "activated_at": now.isoformat(),
        })
        await r.set(REDIS_KS_KEY, state)

        # Audit log entry
        log_entry = json.dumps({
            "action": "activate",
            "reason": reason,
            "timestamp": now.isoformat(),
        })
        await r.rpush(REDIS_KS_LOG_KEY, log_entry)

        logger.critical(
            "kill_switch_activated",
            reason=reason,
            activated_at=now.isoformat(),
        )

        # Cancel all open orders if broker adapter available
        if self._broker is not None:
            try:
                orders = await self._broker.get_open_orders() if hasattr(self._broker, "get_open_orders") else []
                for order in orders:
                    if order.broker_order_id:
                        await self._broker.cancel_order(order.broker_order_id)
                        logger.info("kill_switch_order_cancelled", order_id=order.broker_order_id)
            except Exception:
                logger.exception("kill_switch_cancel_orders_failed")

    async def deactivate(self) -> None:
        """Deactivate the kill switch. Respects cooldown period."""
        r = await self._redis()
        raw = await r.get(REDIS_KS_KEY)
        if raw:
            state = json.loads(raw)
            if state.get("active"):
                activated_at = datetime.fromisoformat(state["activated_at"])
                elapsed_min = (datetime.now(UTC) - activated_at).total_seconds() / 60
                cooldown = self._config.cooldown_minutes
                if elapsed_min < cooldown:
                    remaining = cooldown - elapsed_min
                    logger.warning(
                        "kill_switch_cooldown_active",
                        remaining_minutes=round(remaining, 1),
                    )
                    raise ValueError(
                        f"Kill switch cooldown active. {remaining:.0f} minutes remaining "
                        f"(cooldown: {cooldown} minutes)."
                    )

        now = datetime.now(UTC)
        new_state = json.dumps({
            "active": False,
            "deactivated_at": now.isoformat(),
        })
        await r.set(REDIS_KS_KEY, new_state)

        log_entry = json.dumps({
            "action": "deactivate",
            "timestamp": now.isoformat(),
        })
        await r.rpush(REDIS_KS_LOG_KEY, log_entry)

        logger.warning("kill_switch_deactivated", deactivated_at=now.isoformat())

    async def is_active(self) -> bool:
        """Check if kill switch is currently active. Fast Redis lookup."""
        r = await self._redis()
        raw = await r.get(REDIS_KS_KEY)
        if not raw:
            return False
        state = json.loads(raw)
        return state.get("active", False)

    async def get_status(self) -> dict:
        """Return full kill switch status for the dashboard."""
        r = await self._redis()
        raw = await r.get(REDIS_KS_KEY)
        if not raw:
            return {"active": False, "reason": None, "activated_at": None}
        return json.loads(raw)

    async def get_audit_log(self, limit: int = 50) -> list[dict]:
        """Return recent kill switch events."""
        r = await self._redis()
        entries = await r.lrange(REDIS_KS_LOG_KEY, -limit, -1)
        return [json.loads(e) for e in entries]
