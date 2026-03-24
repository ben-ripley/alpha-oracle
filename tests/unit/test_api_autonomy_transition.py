"""Regression test for CRIT-01 — missing await on autonomy transition validator.

Before the fix, `validator.validate_transition(...)` was called without `await`,
returning a truthy coroutine object. `if not approved:` never fired, so every
transition to FULL_AUTONOMOUS was unconditionally approved. This test ensures
the endpoint correctly rejects a failing transition.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


class TestAutonomyTransitionRoute:
    @pytest.mark.asyncio
    async def test_transition_rejected_when_validator_rejects(self):
        """Endpoint must raise HTTP 422 when the validator returns (False, reasons)."""
        from src.api.routes.risk import TransitionRequest, transition_autonomy_mode

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.settings.autonomy_mode = "MANUAL_APPROVAL"

        mock_validator = MagicMock()
        mock_validator.validate_transition = AsyncMock(
            return_value=(False, ["requires 30 days in current mode"])
        )

        with patch(
            "src.api.routes.risk.get_risk_manager",
            new=AsyncMock(return_value=mock_risk_mgr),
        ):
            with patch(
                "src.risk.autonomy_validator.AutonomyValidator",
                return_value=mock_validator,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await transition_autonomy_mode(
                        TransitionRequest(
                            target_mode="BOUNDED_AUTONOMOUS",
                            days_in_mode=5,
                            sharpe=0.1,
                        )
                    )

        assert exc_info.value.status_code == 422
        assert "requires 30 days" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_transition_approved_when_validator_approves(self):
        """Endpoint must succeed when the validator returns (True, [])."""
        from src.api.routes.risk import TransitionRequest, transition_autonomy_mode

        mock_risk_mgr = MagicMock()
        mock_risk_mgr.settings.autonomy_mode = "MANUAL_APPROVAL"
        # No transition_autonomy_mode method — route skips the persist call
        del mock_risk_mgr.transition_autonomy_mode

        mock_validator = MagicMock()
        mock_validator.validate_transition = AsyncMock(return_value=(True, []))

        with patch(
            "src.api.routes.risk.get_risk_manager",
            new=AsyncMock(return_value=mock_risk_mgr),
        ):
            with patch(
                "src.risk.autonomy_validator.AutonomyValidator",
                return_value=mock_validator,
            ):
                result = await transition_autonomy_mode(
                    TransitionRequest(
                        target_mode="BOUNDED_AUTONOMOUS",
                        days_in_mode=60,
                        sharpe=0.8,
                        circuit_breakers_tested=True,
                    )
                )

        assert result["status"] == "transitioned"
        assert result["from_mode"] == "MANUAL_APPROVAL"
        assert result["to_mode"] == "BOUNDED_AUTONOMOUS"
