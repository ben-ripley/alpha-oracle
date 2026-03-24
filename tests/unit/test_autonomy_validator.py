"""Tests for AutonomyValidator — TDD first.

These tests define the contract for AutonomyValidator.validate_transition().

Transition rules:
  PAPER_ONLY -> MANUAL_APPROVAL: system healthy only
  MANUAL_APPROVAL -> BOUNDED_AUTONOMOUS: days >= 30, Sharpe >= 0.5, drawdown <= limit
  BOUNDED_AUTONOMOUS -> FULL_AUTONOMOUS: days >= 90, Sharpe >= 0.5, drawdown <= limit,
                                         circuit_breakers_tested, LLM guardrails verified
  Any mode -> lower mode: always allowed (downgrade)
  Skipping modes (e.g. PAPER -> FULL_AUTONOMOUS): rejected
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.models import AutonomyMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _healthy_metrics(
    days_in_mode: int = 60,
    sharpe: float = 0.8,
    max_drawdown_pct: float = 5.0,
    circuit_breakers_tested: bool = True,
) -> dict:
    return {
        "days_in_mode": days_in_mode,
        "sharpe": sharpe,
        "max_drawdown_pct": max_drawdown_pct,
        "circuit_breakers_tested": circuit_breakers_tested,
    }


def _make_validator(guardrails_verified: bool = True):
    """Import AutonomyValidator after mocking guardrails Redis check."""
    from src.risk.autonomy_validator import AutonomyValidator
    validator = AutonomyValidator()
    # Patch the internal async guardrails check
    validator._guardrails_recently_verified = AsyncMock(return_value=guardrails_verified)
    return validator


# ---------------------------------------------------------------------------
# PAPER_ONLY -> MANUAL_APPROVAL
# ---------------------------------------------------------------------------

class TestPaperToManual:
    @pytest.mark.asyncio
    async def test_paper_to_manual_approved_when_healthy(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.PAPER_ONLY,
            AutonomyMode.MANUAL_APPROVAL,
            _healthy_metrics(),
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_paper_to_manual_reasons_empty_on_approval(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.PAPER_ONLY,
            AutonomyMode.MANUAL_APPROVAL,
            _healthy_metrics(),
        )
        assert reasons == []

    @pytest.mark.asyncio
    async def test_paper_to_manual_does_not_require_days(self):
        """PAPER -> MANUAL does not check days_in_mode."""
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.PAPER_ONLY,
            AutonomyMode.MANUAL_APPROVAL,
            _healthy_metrics(days_in_mode=0),
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_paper_to_manual_does_not_require_sharpe(self):
        """PAPER -> MANUAL does not check Sharpe."""
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.PAPER_ONLY,
            AutonomyMode.MANUAL_APPROVAL,
            _healthy_metrics(sharpe=-1.0),
        )
        assert ok is True


# ---------------------------------------------------------------------------
# MANUAL_APPROVAL -> BOUNDED_AUTONOMOUS
# ---------------------------------------------------------------------------

class TestManualToBounded:
    @pytest.mark.asyncio
    async def test_manual_to_bounded_approved_when_all_met(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=30, sharpe=0.5, max_drawdown_pct=10.0),
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_manual_to_bounded_fails_insufficient_days(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=29, sharpe=0.8, max_drawdown_pct=5.0),
        )
        assert ok is False
        assert any("days" in r.lower() or "30" in r for r in reasons)

    @pytest.mark.asyncio
    async def test_manual_to_bounded_fails_low_sharpe(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=30, sharpe=0.4),
        )
        assert ok is False
        assert any("sharpe" in r.lower() for r in reasons)

    @pytest.mark.asyncio
    async def test_manual_to_bounded_fails_exactly_below_sharpe_threshold(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=30, sharpe=0.49),
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_manual_to_bounded_passes_at_sharpe_threshold(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=30, sharpe=0.5),
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_manual_to_bounded_fails_excessive_drawdown(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=30, sharpe=0.8, max_drawdown_pct=10.1),
        )
        assert ok is False
        assert any("drawdown" in r.lower() for r in reasons)

    @pytest.mark.asyncio
    async def test_manual_to_bounded_can_fail_multiple_checks(self):
        """Multiple failures should produce multiple reasons."""
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(days_in_mode=5, sharpe=0.1, max_drawdown_pct=20.0),
        )
        assert ok is False
        assert len(reasons) >= 2


# ---------------------------------------------------------------------------
# BOUNDED_AUTONOMOUS -> FULL_AUTONOMOUS
# ---------------------------------------------------------------------------

class TestBoundedToFull:
    @pytest.mark.asyncio
    async def test_bounded_to_full_approved_when_all_met(self):
        validator = _make_validator(guardrails_verified=True)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=90, sharpe=0.5, max_drawdown_pct=10.0, circuit_breakers_tested=True),
        )
        assert ok is True

    @pytest.mark.asyncio
    async def test_bounded_to_full_fails_insufficient_days(self):
        """Must be 90 days (not 30)."""
        validator = _make_validator(guardrails_verified=True)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=89, sharpe=0.8, max_drawdown_pct=5.0, circuit_breakers_tested=True),
        )
        assert ok is False
        assert any("90" in r or "days" in r.lower() for r in reasons)

    @pytest.mark.asyncio
    async def test_bounded_to_full_fails_30_days_not_enough(self):
        """30 days is enough for MANUAL->BOUNDED but NOT for BOUNDED->FULL."""
        validator = _make_validator(guardrails_verified=True)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=30, sharpe=0.8, max_drawdown_pct=5.0, circuit_breakers_tested=True),
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_bounded_to_full_fails_low_sharpe(self):
        validator = _make_validator(guardrails_verified=True)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=90, sharpe=0.4, max_drawdown_pct=5.0, circuit_breakers_tested=True),
        )
        assert ok is False
        assert any("sharpe" in r.lower() for r in reasons)

    @pytest.mark.asyncio
    async def test_bounded_to_full_fails_circuit_breakers_not_tested(self):
        validator = _make_validator(guardrails_verified=True)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=90, sharpe=0.8, max_drawdown_pct=5.0, circuit_breakers_tested=False),
        )
        assert ok is False
        assert any("circuit" in r.lower() for r in reasons)

    @pytest.mark.asyncio
    async def test_bounded_to_full_fails_guardrails_not_verified(self):
        validator = _make_validator(guardrails_verified=False)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=90, sharpe=0.8, max_drawdown_pct=5.0, circuit_breakers_tested=True),
        )
        assert ok is False
        assert any("guardrail" in r.lower() for r in reasons)

    @pytest.mark.asyncio
    async def test_bounded_to_full_fails_excessive_drawdown(self):
        validator = _make_validator(guardrails_verified=True)
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(days_in_mode=90, sharpe=0.8, max_drawdown_pct=11.0, circuit_breakers_tested=True),
        )
        assert ok is False
        assert any("drawdown" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# Downgrade transitions (always allowed)
# ---------------------------------------------------------------------------

class TestDowngradeTransitions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("current,target", [
        (AutonomyMode.MANUAL_APPROVAL, AutonomyMode.PAPER_ONLY),
        (AutonomyMode.BOUNDED_AUTONOMOUS, AutonomyMode.MANUAL_APPROVAL),
        (AutonomyMode.BOUNDED_AUTONOMOUS, AutonomyMode.PAPER_ONLY),
        (AutonomyMode.FULL_AUTONOMOUS, AutonomyMode.BOUNDED_AUTONOMOUS),
        (AutonomyMode.FULL_AUTONOMOUS, AutonomyMode.MANUAL_APPROVAL),
        (AutonomyMode.FULL_AUTONOMOUS, AutonomyMode.PAPER_ONLY),
    ])
    async def test_downgrade_always_approved(self, current, target):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(current, target, {})
        assert ok is True

    @pytest.mark.asyncio
    async def test_downgrade_reasons_empty(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.FULL_AUTONOMOUS,
            AutonomyMode.PAPER_ONLY,
            {},
        )
        assert reasons == []


# ---------------------------------------------------------------------------
# Invalid / skipped transitions
# ---------------------------------------------------------------------------

class TestInvalidTransitions:
    @pytest.mark.asyncio
    async def test_skip_modes_paper_to_bounded_rejected(self):
        """Cannot skip MANUAL_APPROVAL and go straight to BOUNDED_AUTONOMOUS."""
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.PAPER_ONLY,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(),
        )
        assert ok is False
        assert len(reasons) > 0

    @pytest.mark.asyncio
    async def test_skip_modes_paper_to_full_rejected(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.PAPER_ONLY,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(),
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_skip_modes_manual_to_full_rejected(self):
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.MANUAL_APPROVAL,
            AutonomyMode.FULL_AUTONOMOUS,
            _healthy_metrics(),
        )
        assert ok is False

    @pytest.mark.asyncio
    async def test_same_mode_transition_rejected(self):
        """Transitioning to same mode makes no sense."""
        validator = _make_validator()
        ok, reasons = await validator.validate_transition(
            AutonomyMode.BOUNDED_AUTONOMOUS,
            AutonomyMode.BOUNDED_AUTONOMOUS,
            _healthy_metrics(),
        )
        assert ok is False
