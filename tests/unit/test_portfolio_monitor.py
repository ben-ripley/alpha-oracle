"""Tests for PortfolioMonitor: portfolio health checks and risk metrics."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
    PortfolioSnapshot,
    Position,
    RiskAction,
)
from src.risk.portfolio_monitor import PortfolioMonitor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    """Mock settings with risk limits."""
    settings = MagicMock()
    settings.risk.portfolio_limits.max_drawdown_pct = 10.0
    settings.risk.portfolio_limits.max_daily_loss_pct = 3.0
    settings.risk.portfolio_limits.max_positions = 20
    settings.risk.position_limits.stop_loss_pct = 2.0
    settings.risk.position_limits.max_sector_pct = 25.0
    settings.risk.pdt_guard.max_day_trades = 3
    return settings


@pytest.fixture
def mock_pdt_guard():
    """Mock PDT guard."""
    pdt = AsyncMock()
    pdt.count_day_trades = AsyncMock(return_value=1)
    return pdt


@pytest.fixture
def monitor(mock_settings, mock_pdt_guard):
    """PortfolioMonitor instance with mocked dependencies."""
    with patch("src.risk.portfolio_monitor.get_settings", return_value=mock_settings):
        return PortfolioMonitor(pdt_guard=mock_pdt_guard)


def _make_portfolio(
    equity: float = 20000.0,
    cash: float = 12000.0,
    daily_pnl_pct: float = 0.5,
    max_drawdown_pct: float = 3.0,
    positions: list[Position] | None = None,
    sector_exposure: dict[str, float] | None = None,
) -> PortfolioSnapshot:
    """Helper to create PortfolioSnapshot for testing."""
    positions = positions or []
    return PortfolioSnapshot(
        timestamp=datetime.utcnow(),
        total_equity=equity,
        cash=cash,
        positions_value=equity - cash,
        daily_pnl_pct=daily_pnl_pct,
        max_drawdown_pct=max_drawdown_pct,
        positions=positions,
        sector_exposure=sector_exposure or {},
    )


def _make_position(
    symbol: str = "AAPL",
    quantity: float = 10,
    avg_entry_price: float = 180.0,
    current_price: float = 183.0,
    sector: str = "Technology",
) -> Position:
    """Helper to create Position for testing."""
    market_value = quantity * current_price
    unrealized_pnl = quantity * (current_price - avg_entry_price)
    unrealized_pnl_pct = (unrealized_pnl / (quantity * avg_entry_price)) * 100

    return Position(
        symbol=symbol,
        quantity=quantity,
        avg_entry_price=avg_entry_price,
        current_price=current_price,
        market_value=market_value,
        unrealized_pnl=unrealized_pnl,
        unrealized_pnl_pct=unrealized_pnl_pct,
        sector=sector,
        entry_date=datetime.utcnow() - timedelta(days=3),
        strategy_name="TestStrategy",
    )


# ---------------------------------------------------------------------------
# TestCheckPortfolio
# ---------------------------------------------------------------------------

class TestCheckPortfolio:
    """Test the check_portfolio method."""

    @pytest.mark.asyncio
    async def test_drawdown_exceeds_max_rejects(self, monitor):
        """Should REJECT when drawdown exceeds max (10%)."""
        portfolio = _make_portfolio(max_drawdown_pct=12.0)

        result = await monitor.check_portfolio(portfolio)

        assert result.action == RiskAction.REJECT
        assert any("Drawdown" in r and "12.0%" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_daily_loss_exceeds_max_rejects(self, monitor):
        """Should REJECT when daily loss exceeds max (3%)."""
        portfolio = _make_portfolio(daily_pnl_pct=-3.5)

        result = await monitor.check_portfolio(portfolio)

        assert result.action == RiskAction.REJECT
        assert any("Daily loss" in r and "-3.5%" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_both_exceed_both_reasons(self, monitor):
        """Should include both reasons when both limits exceeded."""
        portfolio = _make_portfolio(max_drawdown_pct=12.0, daily_pnl_pct=-4.0)

        result = await monitor.check_portfolio(portfolio)

        assert result.action == RiskAction.REJECT
        assert len(result.reasons) == 2
        assert any("Drawdown" in r for r in result.reasons)
        assert any("Daily loss" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_within_limits_approves(self, monitor):
        """Should APPROVE when all limits are within bounds."""
        portfolio = _make_portfolio(max_drawdown_pct=5.0, daily_pnl_pct=0.8)

        result = await monitor.check_portfolio(portfolio)

        assert result.action == RiskAction.APPROVE
        assert len(result.reasons) == 0

    @pytest.mark.asyncio
    async def test_stop_loss_proximity_adds_warning(self, monitor):
        """Should add warning when position is at stop-loss."""
        # Create position down 2.1% (exceeds stop_loss_pct of 2%)
        position = _make_position(
            symbol="AAPL",
            avg_entry_price=180.0,
            current_price=176.22,  # 2.1% down
        )
        portfolio = _make_portfolio(
            max_drawdown_pct=5.0,
            daily_pnl_pct=0.5,
            positions=[position],
        )

        result = await monitor.check_portfolio(portfolio)

        assert result.action == RiskAction.APPROVE  # Not rejected, just warning
        assert any("STOP-LOSS" in r and "AAPL" in r for r in result.reasons)

    @pytest.mark.asyncio
    async def test_sector_concentration_adds_warning(self, monitor):
        """Should add warning when sector concentration exceeds max (25%)."""
        # Create portfolio with 30% in Technology (exceeds 25% max)
        equity = 20000.0
        tech_exposure = 6000.0  # 30% of equity
        portfolio = _make_portfolio(
            equity=equity,
            max_drawdown_pct=5.0,
            daily_pnl_pct=0.5,
            sector_exposure={"Technology": tech_exposure},
        )

        result = await monitor.check_portfolio(portfolio)

        assert result.action == RiskAction.APPROVE  # Not rejected, just warning
        assert any("CONCENTRATION" in r and "Technology" in r and "30.0%" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# TestGetRiskMetrics
# ---------------------------------------------------------------------------

class TestGetRiskMetrics:
    """Test the get_risk_metrics method."""

    @pytest.mark.asyncio
    async def test_returns_correct_drawdown_and_pnl(self, monitor):
        """Should return correct drawdown and PnL values."""
        portfolio = _make_portfolio(max_drawdown_pct=5.5, daily_pnl_pct=1.2)

        metrics = await monitor.get_risk_metrics(portfolio)

        assert metrics["current_drawdown_pct"] == 5.5
        assert metrics["daily_pnl_pct"] == 1.2

    @pytest.mark.asyncio
    async def test_identifies_positions_at_risk(self, monitor):
        """Should identify positions at risk (down >= 50% of stop_loss_pct)."""
        # stop_loss_pct = 2.0, so 50% is 1.0%
        # Create position down 1.2% (more than 50% towards stop)
        position = _make_position(
            symbol="TSLA",
            avg_entry_price=200.0,
            current_price=197.6,  # 1.2% down
        )
        portfolio = _make_portfolio(positions=[position])

        metrics = await monitor.get_risk_metrics(portfolio)

        assert len(metrics["positions_at_risk"]) == 1
        assert metrics["positions_at_risk"][0]["symbol"] == "TSLA"
        assert metrics["positions_at_risk"][0]["stop_loss_pct"] == 2.0

    @pytest.mark.asyncio
    async def test_sector_percentages_calculated(self, monitor):
        """Should calculate sector exposure percentages correctly."""
        equity = 20000.0
        portfolio = _make_portfolio(
            equity=equity,
            sector_exposure={
                "Technology": 8000.0,  # 40%
                "Financials": 4000.0,  # 20%
            },
        )

        metrics = await monitor.get_risk_metrics(portfolio)

        assert metrics["sector_exposure"]["Technology"] == 40.0
        assert metrics["sector_exposure"]["Financials"] == 20.0

    @pytest.mark.asyncio
    async def test_zero_equity_handled(self, monitor):
        """Should handle zero equity without division error."""
        portfolio = _make_portfolio(equity=0.0, cash=0.0)

        metrics = await monitor.get_risk_metrics(portfolio)

        assert metrics["cash_reserve_pct"] == 0.0
        assert metrics["sector_exposure"] == {}
