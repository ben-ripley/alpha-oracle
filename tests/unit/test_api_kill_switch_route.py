"""Tests for kill switch deactivation API route error handling."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


class TestKillSwitchDeactivateRoute:
    @pytest.mark.asyncio
    async def test_deactivate_returns_400_when_value_error_raised(self):
        """Kill switch deactivation failure should return HTTP 400, not 200 with error body."""
        from src.api.routes.risk import deactivate_kill_switch

        mock_risk_mgr = AsyncMock()
        mock_risk_mgr.kill_switch.deactivate = AsyncMock(
            side_effect=ValueError("cooldown period has not expired")
        )

        with patch(
            "src.api.routes.risk.get_risk_manager",
            new=AsyncMock(return_value=mock_risk_mgr),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await deactivate_kill_switch()

        assert exc_info.value.status_code == 400
        assert "cooldown period has not expired" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_deactivate_returns_200_on_success(self):
        """Successful deactivation should still return 200 with deactivated status."""
        from src.api.routes.risk import deactivate_kill_switch

        mock_risk_mgr = AsyncMock()
        mock_risk_mgr.kill_switch.deactivate = AsyncMock(return_value=None)

        with patch(
            "src.api.routes.risk.get_risk_manager",
            new=AsyncMock(return_value=mock_risk_mgr),
        ):
            result = await deactivate_kill_switch()

        assert result == {"status": "deactivated"}
