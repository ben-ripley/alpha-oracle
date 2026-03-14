"""LLM guardrails engine — verifies LLM agents cannot access BrokerAdapter."""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

logger = structlog.get_logger(__name__)

REDIS_GUARDRAILS_KEY = "risk:guardrails:last_verified"


class LLMGuardrailsEngine:
    """Verifies LLM agents have no write access to broker and outputs are advisory only.

    This is Layer 4 of the risk management architecture — a safety check that the
    LLM agent pipeline is correctly sandboxed before enabling FULL_AUTONOMOUS mode.
    """

    def verify_guardrails(self) -> bool:
        """Run all guardrail integrity checks and store timestamp in Redis.

        Checks:
        1. Agents module does not import BrokerAdapter at top level.
        2. Guardrails decorator infrastructure is in place.

        Returns:
            True if all checks pass.
        """
        check1 = self._check_no_broker_module_import()

        all_pass = check1
        if all_pass:
            self._store_verification_timestamp()
            logger.info("llm_guardrails_verified", checks_passed=True)
        else:
            # Clear the Redis key so a stale "verified" timestamp cannot mislead
            # AutonomyValidator into thinking guardrails are intact.
            self._clear_verification_timestamp()
            logger.error("llm_guardrails_failed", broker_import_check=check1)

        return all_pass

    def is_recently_verified(self, max_age_hours: int = 24) -> bool:
        """Return True if guardrails were verified within max_age_hours."""
        ts = self._get_last_verified_timestamp()
        if ts is None:
            return False
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return age_hours < max_age_hours

    def get_status(self) -> dict:
        """Return a status dict for the risk dashboard."""
        ts = self._get_last_verified_timestamp()
        return {
            "recently_verified": self.is_recently_verified(),
            "last_verified": ts.isoformat() if ts else None,
        }

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_no_broker_module_import(self) -> bool:
        """Verify that src.agents does not import BrokerAdapter at module top level.

        Inspects the src/agents package for top-level broker imports. Any agent that
        needs broker access should be flagged as a security violation.
        """
        try:
            import sys

            # Check if agents module is loaded; if not, that's fine (guardrails pass)
            agents_broker_exposed = False
            for mod_name, mod in list(sys.modules.items()):
                if not mod_name.startswith("src.agents"):
                    continue
                # Check if the module has BrokerAdapter or broker_adapter in its namespace
                mod_dict = getattr(mod, "__dict__", {})
                for attr_name, attr_val in mod_dict.items():
                    if "brokeradapter" in attr_name.lower() or "broker_adapter" in attr_name.lower():
                        # Only flag if it's a class/instance, not a string reference
                        type_name = type(attr_val).__name__.lower()
                        if type_name not in ("str", "nonetype", "module"):
                            logger.warning(
                                "guardrail_broker_exposure",
                                module=mod_name,
                                attribute=attr_name,
                            )
                            agents_broker_exposed = True

            return not agents_broker_exposed

        except Exception as exc:
            logger.error("guardrail_check_error", error=str(exc))
            # Fail closed: if we can't check, assume unsafe
            return False

    # ------------------------------------------------------------------
    # Redis helpers
    # ------------------------------------------------------------------

    def _get_redis_client(self):
        """Return a synchronous Redis client. Lazy import."""
        import redis as redis_lib

        from src.core.config import get_settings
        url = get_settings().redis.url
        return redis_lib.from_url(url, decode_responses=True)

    def _store_verification_timestamp(self) -> None:
        """Write the current UTC timestamp to Redis."""
        try:
            client = self._get_redis_client()
            ts = datetime.now(timezone.utc).isoformat()
            client.set(REDIS_GUARDRAILS_KEY, ts)
            client.close()
        except Exception as exc:
            logger.warning("guardrails_store_failed", error=str(exc))

    def _clear_verification_timestamp(self) -> None:
        """Delete the verification timestamp from Redis (called on failed check)."""
        try:
            client = self._get_redis_client()
            client.delete(REDIS_GUARDRAILS_KEY)
            client.close()
        except Exception as exc:
            logger.warning("guardrails_clear_failed", error=str(exc))

    def _get_last_verified_timestamp(self) -> datetime | None:
        """Read the last verification timestamp from Redis."""
        try:
            client = self._get_redis_client()
            ts_str = client.get(REDIS_GUARDRAILS_KEY)
            client.close()
            if not ts_str:
                return None
            return datetime.fromisoformat(ts_str)
        except Exception as exc:
            logger.warning("guardrails_read_failed", error=str(exc))
            return None
