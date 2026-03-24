"""Autonomy mode transition validator.

Validates preconditions before the system can advance to a higher autonomy mode.
All transitions are conservative: reject when in doubt.
"""
from __future__ import annotations

from datetime import UTC

import structlog

from src.core.config import get_settings
from src.core.models import AutonomyMode

logger = structlog.get_logger(__name__)

# Mode ordering for skip-check
_MODE_ORDER = [
    AutonomyMode.PAPER_ONLY,
    AutonomyMode.MANUAL_APPROVAL,
    AutonomyMode.BOUNDED_AUTONOMOUS,
    AutonomyMode.FULL_AUTONOMOUS,
]

# BOUNDED -> FULL requires 90 days regardless of settings (safety threshold)
_FULL_AUTONOMOUS_MIN_DAYS = 90


class AutonomyValidator:
    """Validates preconditions for autonomy mode transitions."""

    async def validate_transition(
        self,
        current_mode: AutonomyMode,
        target_mode: AutonomyMode,
        portfolio_metrics: dict,
    ) -> tuple[bool, list[str]]:
        """Check all preconditions for transitioning from current_mode to target_mode.

        Args:
            current_mode: The current autonomy mode.
            target_mode: The desired autonomy mode.
            portfolio_metrics: Dict with keys:
                - days_in_mode (int): Days spent in current_mode.
                - sharpe (float): Sharpe ratio during evaluation period.
                - max_drawdown_pct (float): Max drawdown during evaluation period.
                - circuit_breakers_tested (bool): Whether circuit breakers have been triggered/tested.

        Returns:
            (approved, reasons) — approved is True if transition is permitted.
            reasons lists why transition was denied (empty when approved).
        """
        current_idx = _MODE_ORDER.index(current_mode)
        target_idx = _MODE_ORDER.index(target_mode)

        # Downgrade: always allowed
        if target_idx < current_idx:
            logger.info(
                "autonomy_downgrade_approved",
                current=current_mode.value,
                target=target_mode.value,
            )
            return True, []

        # Same mode
        if current_idx == target_idx:
            return False, [f"Already in {current_mode.value} mode"]

        # Skip modes not allowed (must advance one step at a time)
        if target_idx > current_idx + 1:
            skip_through = _MODE_ORDER[current_idx + 1].value
            return False, [
                f"Cannot skip from {current_mode.value} to {target_mode.value}. "
                f"Must transition through {skip_through} first."
            ]

        # One-step upgrades
        if current_mode == AutonomyMode.PAPER_ONLY and target_mode == AutonomyMode.MANUAL_APPROVAL:
            return self._validate_paper_to_manual(portfolio_metrics)

        if current_mode == AutonomyMode.MANUAL_APPROVAL and target_mode == AutonomyMode.BOUNDED_AUTONOMOUS:
            return self._validate_manual_to_bounded(portfolio_metrics)

        if current_mode == AutonomyMode.BOUNDED_AUTONOMOUS and target_mode == AutonomyMode.FULL_AUTONOMOUS:
            return await self._validate_bounded_to_full(portfolio_metrics)

        return False, [f"Unhandled transition: {current_mode.value} -> {target_mode.value}"]

    # ------------------------------------------------------------------
    # Individual transition validators
    # ------------------------------------------------------------------

    def _validate_paper_to_manual(self, metrics: dict) -> tuple[bool, list[str]]:
        """PAPER_ONLY -> MANUAL_APPROVAL: only requires system to be healthy."""
        logger.info("autonomy_transition_approved", current="PAPER_ONLY", target="MANUAL_APPROVAL")
        return True, []

    def _validate_manual_to_bounded(self, metrics: dict) -> tuple[bool, list[str]]:
        """MANUAL_APPROVAL -> BOUNDED_AUTONOMOUS: days, Sharpe, drawdown."""
        settings = get_settings().risk
        min_days = settings.autonomy_transition_min_days
        min_sharpe = settings.autonomy_min_sharpe
        max_drawdown = settings.autonomy_max_drawdown_pct

        reasons: list[str] = []

        days = metrics.get("days_in_mode", 0)
        if days < min_days:
            reasons.append(
                f"Insufficient time in MANUAL_APPROVAL mode: {days} days (minimum {min_days} days required)"
            )

        sharpe = metrics.get("sharpe", 0.0)
        if sharpe < min_sharpe:
            reasons.append(
                f"Sharpe ratio {sharpe:.3f} below minimum {min_sharpe:.1f}"
            )

        drawdown = metrics.get("max_drawdown_pct", 0.0)
        if drawdown > max_drawdown:
            reasons.append(
                f"Max drawdown {drawdown:.1f}% exceeds limit {max_drawdown:.1f}%"
            )

        approved = len(reasons) == 0
        logger.info(
            "autonomy_transition_evaluated",
            current="MANUAL_APPROVAL",
            target="BOUNDED_AUTONOMOUS",
            approved=approved,
            reason_count=len(reasons),
        )
        return approved, reasons

    async def _validate_bounded_to_full(self, metrics: dict) -> tuple[bool, list[str]]:
        """BOUNDED_AUTONOMOUS -> FULL_AUTONOMOUS: 90 days, Sharpe, drawdown, circuit breakers, guardrails."""
        settings = get_settings().risk
        min_sharpe = settings.autonomy_min_sharpe
        max_drawdown = settings.autonomy_max_drawdown_pct

        reasons: list[str] = []

        days = metrics.get("days_in_mode", 0)
        if days < _FULL_AUTONOMOUS_MIN_DAYS:
            reasons.append(
                f"Insufficient time in BOUNDED_AUTONOMOUS mode: {days} days "
                f"(minimum {_FULL_AUTONOMOUS_MIN_DAYS} days required for FULL_AUTONOMOUS)"
            )

        sharpe = metrics.get("sharpe", 0.0)
        if sharpe < min_sharpe:
            reasons.append(
                f"Sharpe ratio {sharpe:.3f} below minimum {min_sharpe:.1f}"
            )

        drawdown = metrics.get("max_drawdown_pct", 0.0)
        if drawdown > max_drawdown:
            reasons.append(
                f"Max drawdown {drawdown:.1f}% exceeds limit {max_drawdown:.1f}%"
            )

        if not metrics.get("circuit_breakers_tested", False):
            reasons.append(
                "Circuit breakers must have been triggered and tested at least once before FULL_AUTONOMOUS"
            )

        if not await self._guardrails_recently_verified():
            reasons.append(
                "LLM guardrails have not been verified recently — run guardrail self-test first"
            )

        approved = len(reasons) == 0
        logger.info(
            "autonomy_transition_evaluated",
            current="BOUNDED_AUTONOMOUS",
            target="FULL_AUTONOMOUS",
            approved=approved,
            reason_count=len(reasons),
        )
        return approved, reasons

    async def _guardrails_recently_verified(self) -> bool:
        """Check if LLM guardrails were verified recently (within 24h).

        Reads Redis key `risk:guardrails:last_verified`.
        Returns True if verified within 24 hours, False otherwise.
        Lazy import to avoid Redis dependency at module import time.
        """
        try:
            from datetime import datetime

            from src.core.redis import get_redis

            redis = await get_redis()
            ts_str = await redis.get("risk:guardrails:last_verified")

            if not ts_str:
                return False

            verified_at = datetime.fromisoformat(ts_str)
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=UTC)
            age_hours = (datetime.now(UTC) - verified_at).total_seconds() / 3600
            return age_hours <= 24.0

        except Exception as exc:
            # Fail-closed policy: any error (Redis unavailable, parse failure, etc.)
            # is treated as "guardrails not verified", blocking BOUNDED→FULL transitions.
            # This is consistent with manager.py which also fails closed on Redis errors.
            logger.warning("guardrails_check_failed", error=str(exc))
            return False
