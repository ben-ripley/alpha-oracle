"""Tests for RiskManagerImpl — top-level risk manager facade."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.core.models import (
    Order,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    RiskAction,
    RiskCheckResult,
)
from src.risk.manager import RiskManagerImpl

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_broker():
    """Mock BrokerAdapter for RiskManagerImpl."""
    broker = AsyncMock()
    broker.get_portfolio = AsyncMock(return_value=PortfolioSnapshot(
        total_equity=20000.0,
        cash=12000.0,
        positions_value=8000.0,
    ))
    return broker


@pytest.fixture
def risk_manager_with_mocks(mock_broker):
    """RiskManagerImpl with mocked subsystems."""
    mgr = RiskManagerImpl.__new__(RiskManagerImpl)

    # Mock all subsystems
    mgr._kill_switch = AsyncMock()
    mgr._kill_switch.is_active = AsyncMock(return_value=False)
    mgr._kill_switch.get_status = AsyncMock(return_value={
        "active": False,
        "reason": None,
    })

    mgr._circuit_breakers = AsyncMock()
    mgr._circuit_breakers.get_states = AsyncMock(return_value={})
    mgr._circuit_breakers.check_all = AsyncMock(return_value=[])
    mgr._circuit_breakers.build_context = AsyncMock(return_value={})

    mgr._pre_trade = AsyncMock()
    mgr._pre_trade.check_pre_trade = AsyncMock(return_value=RiskCheckResult(
        action=RiskAction.APPROVE,
        reasons=[],
    ))
    mgr._pre_trade._settings = AsyncMock()
    mgr._pre_trade._settings.autonomy_mode = "PAPER_ONLY"

    mgr._monitor = AsyncMock()
    mgr._monitor.check_portfolio = AsyncMock(return_value=RiskCheckResult(
        action=RiskAction.APPROVE,
        reasons=[],
    ))
    mgr._monitor.get_risk_metrics = AsyncMock(return_value={
        "total_equity": 20000.0,
        "cash_reserve_pct": 60.0,
    })

    mgr._pdt = AsyncMock()
    mgr._reconciliation = AsyncMock()

    return mgr


@pytest.fixture
def sample_order() -> Order:
    """Sample order for testing."""
    return Order(
        id="test-order",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        limit_price=150.0,
    )


# ---------------------------------------------------------------------------
# TestCheckPreTrade
# ---------------------------------------------------------------------------

class TestCheckPreTrade:
    """Test check_pre_trade logic with kill switch and circuit breakers."""

    @pytest.mark.asyncio
    async def test_kill_switch_active_short_circuits_with_reject(
        self, risk_manager_with_mocks, sample_order, sample_portfolio
    ):
        """Kill switch active short-circuits with REJECT."""
        risk_manager_with_mocks._kill_switch.is_active = AsyncMock(return_value=True)

        result = await risk_manager_with_mocks.check_pre_trade(
            sample_order, sample_portfolio
        )

        assert result.action == RiskAction.REJECT
        assert "Kill switch is ACTIVE" in result.reasons[0]
        # Should not reach pre_trade engine
        risk_manager_with_mocks._pre_trade.check_pre_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_circuit_breaker_tripped_returns_reject(
        self, risk_manager_with_mocks, sample_order, sample_portfolio
    ):
        """Circuit breaker tripped returns REJECT with breaker reasons."""
        risk_manager_with_mocks._circuit_breakers.get_states = AsyncMock(
            return_value={
                "vix": {"tripped": True, "reason": "VIX above 35"},
                "stale_data": {"tripped": False, "reason": None},
            }
        )

        result = await risk_manager_with_mocks.check_pre_trade(
            sample_order, sample_portfolio
        )

        assert result.action == RiskAction.REJECT
        assert any("vix" in reason.lower() for reason in result.reasons)
        # Should not reach pre_trade engine
        risk_manager_with_mocks._pre_trade.check_pre_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_issues_delegates_to_pre_trade_engine(
        self, risk_manager_with_mocks, sample_order, sample_portfolio
    ):
        """No issues delegates to pre-trade engine (returns its result)."""
        risk_manager_with_mocks._pre_trade.check_pre_trade = AsyncMock(
            return_value=RiskCheckResult(
                action=RiskAction.APPROVE,
                reasons=["All checks passed"],
            )
        )

        result = await risk_manager_with_mocks.check_pre_trade(
            sample_order, sample_portfolio
        )

        assert result.action == RiskAction.APPROVE
        risk_manager_with_mocks._pre_trade.check_pre_trade.assert_called_once_with(
            sample_order, sample_portfolio
        )

    @pytest.mark.asyncio
    async def test_multiple_breakers_tripped_lists_all_reasons(
        self, risk_manager_with_mocks, sample_order, sample_portfolio
    ):
        """Multiple breakers tripped lists all reasons."""
        risk_manager_with_mocks._circuit_breakers.get_states = AsyncMock(
            return_value={
                "vix": {"tripped": True, "reason": "VIX above 35"},
                "drawdown": {"tripped": True, "reason": "Drawdown exceeded 10%"},
                "stale_data": {"tripped": False, "reason": None},
            }
        )

        result = await risk_manager_with_mocks.check_pre_trade(
            sample_order, sample_portfolio
        )

        assert result.action == RiskAction.REJECT
        assert len(result.reasons) == 2
        assert any("vix" in reason.lower() for reason in result.reasons)
        assert any("drawdown" in reason.lower() for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_kill_switch_inactive_no_breakers_pre_trade_approves(
        self, risk_manager_with_mocks, sample_order, sample_portfolio
    ):
        """Kill switch inactive + no breakers + pre-trade approves = APPROVE."""
        risk_manager_with_mocks._kill_switch.is_active = AsyncMock(return_value=False)
        risk_manager_with_mocks._circuit_breakers.get_states = AsyncMock(
            return_value={}
        )
        risk_manager_with_mocks._pre_trade.check_pre_trade = AsyncMock(
            return_value=RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        )

        result = await risk_manager_with_mocks.check_pre_trade(
            sample_order, sample_portfolio
        )

        assert result.action == RiskAction.APPROVE

    @pytest.mark.asyncio
    async def test_kill_switch_inactive_no_breakers_pre_trade_rejects(
        self, risk_manager_with_mocks, sample_order, sample_portfolio
    ):
        """Kill switch inactive + no breakers + pre-trade rejects = REJECT."""
        risk_manager_with_mocks._kill_switch.is_active = AsyncMock(return_value=False)
        risk_manager_with_mocks._circuit_breakers.get_states = AsyncMock(
            return_value={}
        )
        risk_manager_with_mocks._pre_trade.check_pre_trade = AsyncMock(
            return_value=RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=["Position limit exceeded"],
            )
        )

        result = await risk_manager_with_mocks.check_pre_trade(
            sample_order, sample_portfolio
        )

        assert result.action == RiskAction.REJECT
        assert "Position limit exceeded" in result.reasons


# ---------------------------------------------------------------------------
# TestCheckPortfolio
# ---------------------------------------------------------------------------

class TestCheckPortfolio:
    """Test check_portfolio logic with monitor and circuit breakers."""

    @pytest.mark.asyncio
    async def test_clean_portfolio_with_no_breakers_passes(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Clean portfolio with no breakers passes (APPROVE)."""
        risk_manager_with_mocks._monitor.check_portfolio = AsyncMock(
            return_value=RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        )
        risk_manager_with_mocks._circuit_breakers.check_all = AsyncMock(
            return_value=[]
        )

        result = await risk_manager_with_mocks.check_portfolio(sample_portfolio)

        assert result.action == RiskAction.APPROVE
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_breaker_trip_upgrades_approve_to_reject(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Breaker trip upgrades APPROVE to REJECT."""
        risk_manager_with_mocks._monitor.check_portfolio = AsyncMock(
            return_value=RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        )
        risk_manager_with_mocks._circuit_breakers.check_all = AsyncMock(
            return_value=[
                ("vix", True, "VIX above 35"),
            ]
        )

        result = await risk_manager_with_mocks.check_portfolio(sample_portfolio)

        assert result.action == RiskAction.REJECT
        assert any("vix" in reason.lower() for reason in result.reasons)

    @pytest.mark.asyncio
    async def test_critical_breaker_drawdown_auto_activates_kill_switch(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Critical breaker (drawdown) auto-activates kill switch."""
        risk_manager_with_mocks._monitor.check_portfolio = AsyncMock(
            return_value=RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        )
        risk_manager_with_mocks._circuit_breakers.check_all = AsyncMock(
            return_value=[
                ("drawdown", True, "Max drawdown exceeded 10%"),
            ]
        )
        risk_manager_with_mocks._kill_switch.activate = AsyncMock()

        result = await risk_manager_with_mocks.check_portfolio(sample_portfolio)

        assert result.action == RiskAction.REJECT
        risk_manager_with_mocks._kill_switch.activate.assert_called_once()
        call_args = risk_manager_with_mocks._kill_switch.activate.call_args[0][0]
        assert "drawdown" in call_args.lower()

    @pytest.mark.asyncio
    async def test_critical_breaker_daily_loss_auto_activates_kill_switch(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Critical breaker (daily_loss) auto-activates kill switch."""
        risk_manager_with_mocks._monitor.check_portfolio = AsyncMock(
            return_value=RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        )
        risk_manager_with_mocks._circuit_breakers.check_all = AsyncMock(
            return_value=[
                ("daily_loss", True, "Daily loss exceeded 3%"),
            ]
        )
        risk_manager_with_mocks._kill_switch.activate = AsyncMock()

        result = await risk_manager_with_mocks.check_portfolio(sample_portfolio)

        assert result.action == RiskAction.REJECT
        risk_manager_with_mocks._kill_switch.activate.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_critical_breaker_vix_does_not_activate_kill_switch(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Non-critical breaker (vix) does NOT activate kill switch."""
        risk_manager_with_mocks._monitor.check_portfolio = AsyncMock(
            return_value=RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        )
        risk_manager_with_mocks._circuit_breakers.check_all = AsyncMock(
            return_value=[
                ("vix", True, "VIX above 35"),
            ]
        )
        risk_manager_with_mocks._kill_switch.activate = AsyncMock()

        result = await risk_manager_with_mocks.check_portfolio(sample_portfolio)

        assert result.action == RiskAction.REJECT
        risk_manager_with_mocks._kill_switch.activate.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_breakers_append_all_reasons(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Multiple breakers append all reasons."""
        risk_manager_with_mocks._monitor.check_portfolio = AsyncMock(
            return_value=RiskCheckResult(
                action=RiskAction.APPROVE,
                reasons=["Monitor check passed"],
            )
        )
        risk_manager_with_mocks._circuit_breakers.check_all = AsyncMock(
            return_value=[
                ("vix", True, "VIX above 35"),
                ("stale_data", True, "Data is stale"),
            ]
        )

        result = await risk_manager_with_mocks.check_portfolio(sample_portfolio)

        assert result.action == RiskAction.REJECT
        # Should have monitor reason + 2 breaker reasons
        assert len(result.reasons) == 3
        assert "Monitor check passed" in result.reasons
        assert any("vix" in reason.lower() for reason in result.reasons)
        assert any("stale" in reason.lower() for reason in result.reasons)


# ---------------------------------------------------------------------------
# TestDashboard
# ---------------------------------------------------------------------------

class TestDashboard:
    """Test get_risk_dashboard combining all subsystem data."""

    @pytest.mark.asyncio
    async def test_returns_combined_metrics(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Returns combined metrics from monitor, circuit breakers, kill switch."""
        risk_manager_with_mocks._monitor.get_risk_metrics = AsyncMock(
            return_value={
                "total_equity": 20000.0,
                "cash_reserve_pct": 60.0,
                "position_count": 3,
            }
        )
        risk_manager_with_mocks._circuit_breakers.get_states = AsyncMock(
            return_value={
                "vix": {"tripped": False, "reason": None},
                "drawdown": {"tripped": False, "reason": None},
            }
        )
        risk_manager_with_mocks._kill_switch.get_status = AsyncMock(
            return_value={
                "active": False,
                "reason": None,
                "activated_at": None,
            }
        )
        risk_manager_with_mocks._pre_trade._settings.autonomy_mode = "BOUNDED_AUTONOMOUS"

        dashboard = await risk_manager_with_mocks.get_risk_dashboard(sample_portfolio)

        assert "portfolio_metrics" in dashboard
        assert "circuit_breakers" in dashboard
        assert "kill_switch" in dashboard
        assert "autonomy_mode" in dashboard
        assert dashboard["autonomy_mode"] == "BOUNDED_AUTONOMOUS"
        assert dashboard["portfolio_metrics"]["total_equity"] == 20000.0
        assert "vix" in dashboard["circuit_breakers"]
        assert dashboard["kill_switch"]["active"] is False

    @pytest.mark.asyncio
    async def test_includes_autonomy_mode_from_settings(
        self, risk_manager_with_mocks, sample_portfolio
    ):
        """Includes autonomy_mode from settings."""
        risk_manager_with_mocks._pre_trade._settings.autonomy_mode = "MANUAL_APPROVAL"

        dashboard = await risk_manager_with_mocks.get_risk_dashboard(sample_portfolio)

        assert dashboard["autonomy_mode"] == "MANUAL_APPROVAL"


# ---------------------------------------------------------------------------
# TestProperties
# ---------------------------------------------------------------------------

class TestProperties:
    """Test property accessors for subsystems."""

    def test_pdt_guard_property_returns_correct_instance(
        self, risk_manager_with_mocks
    ):
        """pdt_guard property returns correct instance."""
        assert risk_manager_with_mocks.pdt_guard == risk_manager_with_mocks._pdt

    def test_kill_switch_property_returns_correct_instance(
        self, risk_manager_with_mocks
    ):
        """kill_switch property returns correct instance."""
        assert risk_manager_with_mocks.kill_switch == risk_manager_with_mocks._kill_switch
