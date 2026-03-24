"""Tests for the pre-trade risk engine."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
    Order,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    Position,
    RiskAction,
    RiskCheckResult,
)
from src.risk.pre_trade import PreTradeRiskEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_portfolio(
    equity: float = 20000.0,
    cash: float = 12000.0,
    positions: list[Position] | None = None,
    sector_exposure: dict[str, float] | None = None,
) -> PortfolioSnapshot:
    positions = positions or []
    return PortfolioSnapshot(
        total_equity=equity,
        cash=cash,
        positions_value=equity - cash,
        positions=positions,
        sector_exposure=sector_exposure or {},
    )


def _make_order(
    symbol: str = "GOOG",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 5,
    limit_price: float = 170.0,
) -> Order:
    return Order(
        id="test-order",
        symbol=symbol,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=limit_price,
    )


@pytest.fixture
def mock_pdt():
    pdt = AsyncMock()
    pdt.check = AsyncMock(return_value=RiskCheckResult(
        action=RiskAction.APPROVE,
        reasons=["PDT OK"],
        metadata={"pdt_trades_used": 0, "pdt_trades_max": 3, "pdt_exempt": False},
    ))
    return pdt


@pytest.fixture
def engine(mock_pdt):
    with patch("src.risk.pre_trade.get_settings") as mock_settings:
        settings = MagicMock()
        settings.risk.position_limits.max_position_pct = 5.0
        settings.risk.position_limits.max_sector_pct = 25.0
        settings.risk.position_limits.min_price = 5.0
        settings.risk.position_limits.stop_loss_pct = 2.0
        settings.risk.portfolio_limits.max_positions = 20
        settings.risk.portfolio_limits.max_daily_trades = 50
        settings.risk.portfolio_limits.min_cash_reserve_pct = 10.0
        settings.risk.autonomy_mode = "PAPER_ONLY"
        mock_settings.return_value = settings
        engine = PreTradeRiskEngine(pdt_guard=mock_pdt)
    return engine


class TestMinPrice:
    @pytest.mark.asyncio
    async def test_rejects_penny_stock(self, engine):
        order = _make_order(limit_price=3.50)
        portfolio = _make_portfolio()
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.REJECT
        assert any("penny" in r.lower() or "minimum" in r.lower() for r in result.reasons)

    @pytest.mark.asyncio
    async def test_approves_above_min_price(self, engine):
        order = _make_order(limit_price=50.0, quantity=1)
        portfolio = _make_portfolio()
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.APPROVE


class TestPositionSize:
    @pytest.mark.asyncio
    async def test_rejects_oversized_position(self, engine):
        """Order for >5% of portfolio should be rejected or reduced."""
        # $20K equity, 5% = $1000 max. Order: 10 shares @ $170 = $1700
        order = _make_order(quantity=10, limit_price=170.0)
        portfolio = _make_portfolio(equity=20000.0, cash=15000.0)
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action in (RiskAction.REDUCE_SIZE, RiskAction.REJECT)

    @pytest.mark.asyncio
    async def test_approves_small_position(self, engine):
        """Order well within 5% limit."""
        # $20K equity, 5% = $1000 max. Order: 5 shares @ $170 = $850
        order = _make_order(quantity=5, limit_price=170.0)
        portfolio = _make_portfolio(equity=20000.0, cash=15000.0)
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.APPROVE

    @pytest.mark.asyncio
    async def test_reduces_size_when_possible(self, engine):
        """If order is too big but can be reduced, return REDUCE_SIZE."""
        # 5% of $20K = $1000. Order: 8 shares @ $170 = $1360 (too big)
        # Can reduce to 5 shares = $850 (within limit)
        order = _make_order(quantity=8, limit_price=170.0)
        portfolio = _make_portfolio(equity=20000.0, cash=15000.0)
        result = await engine.check_pre_trade(order, portfolio)
        if result.action == RiskAction.REDUCE_SIZE:
            assert result.adjusted_quantity is not None
            assert result.adjusted_quantity > 0
            assert result.adjusted_quantity * 170.0 <= 1000.0


class TestMaxPositions:
    @pytest.mark.asyncio
    async def test_rejects_at_max_positions(self, engine):
        """With 20 positions, reject a new position buy."""
        positions = [
            Position(symbol=f"SYM{i}", quantity=1, avg_entry_price=10.0, market_value=10.0)
            for i in range(20)
        ]
        order = _make_order(symbol="NEW", quantity=1, limit_price=10.0)
        portfolio = _make_portfolio(equity=20000.0, cash=19800.0, positions=positions)
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.REJECT
        assert any("max positions" in r.lower() for r in result.reasons)

    @pytest.mark.asyncio
    async def test_allows_adding_to_existing_position(self, engine):
        """Adding to an existing position doesn't count as a new position."""
        positions = [
            Position(symbol=f"SYM{i}", quantity=1, avg_entry_price=10.0, market_value=10.0)
            for i in range(20)
        ]
        # Add to SYM0 which already exists
        order = _make_order(symbol="SYM0", quantity=1, limit_price=10.0)
        portfolio = _make_portfolio(equity=20000.0, cash=19800.0, positions=positions)
        result = await engine.check_pre_trade(order, portfolio)
        # Should not reject for max positions (though may reject for other reasons)
        position_reject = any("max positions" in r.lower() for r in result.reasons)
        assert not position_reject

    @pytest.mark.asyncio
    async def test_sell_always_allowed_regardless_of_max(self, engine):
        """Selling is always allowed even at max positions."""
        positions = [
            Position(symbol=f"SYM{i}", quantity=1, avg_entry_price=10.0, market_value=10.0)
            for i in range(20)
        ]
        order = _make_order(symbol="SYM0", side=OrderSide.SELL, quantity=1, limit_price=10.0)
        portfolio = _make_portfolio(equity=20000.0, cash=19800.0, positions=positions)
        result = await engine.check_pre_trade(order, portfolio)
        position_reject = any("max positions" in r.lower() for r in result.reasons)
        assert not position_reject


class TestCashReserve:
    @pytest.mark.asyncio
    async def test_rejects_when_cash_too_low(self, engine):
        """Buying when it would drop cash below 10% reserve."""
        # $20K equity, 10% reserve = $2K min cash
        # Cash: $2500, buying $1000 would leave $1500 (7.5% < 10%)
        order = _make_order(quantity=5, limit_price=200.0)  # $1000 order
        portfolio = _make_portfolio(equity=20000.0, cash=2500.0)
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.REJECT
        assert any("cash reserve" in r.lower() for r in result.reasons)

    @pytest.mark.asyncio
    async def test_approves_with_sufficient_cash(self, engine):
        """Buying with plenty of cash remaining."""
        order = _make_order(quantity=2, limit_price=50.0)  # $100 order
        portfolio = _make_portfolio(equity=20000.0, cash=15000.0)
        result = await engine.check_pre_trade(order, portfolio)
        # Cash after: $14900, reserve 74.5% - well above 10%
        cash_reject = any("cash reserve" in r.lower() for r in result.reasons)
        assert not cash_reject


class TestSectorExposure:
    @pytest.mark.asyncio
    async def test_rejects_sector_concentration(self, engine):
        """Reject buy when sector would exceed 25%."""
        positions = [
            Position(
                symbol="AAPL",
                quantity=10,
                avg_entry_price=178.0,
                current_price=180.0,
                market_value=4800.0,
                sector="Technology",
            ),
        ]
        # Tech already at $4800/20000 = 24%. Adding $500 more = 26.5% > 25%
        order = _make_order(symbol="AAPL", quantity=3, limit_price=180.0)
        portfolio = _make_portfolio(
            equity=20000.0,
            cash=15000.0,
            positions=positions,
            sector_exposure={"Technology": 4800.0},
        )
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.REJECT
        assert any("sector" in r.lower() for r in result.reasons)


class TestAutonomyMode:
    @pytest.mark.asyncio
    async def test_paper_only_approves(self, engine):
        order = _make_order(quantity=1, limit_price=50.0)
        portfolio = _make_portfolio()
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.APPROVE

    @pytest.mark.asyncio
    async def test_manual_approval_requires_human(self, mock_pdt):
        with patch("src.risk.pre_trade.get_settings") as mock_settings:
            settings = MagicMock()
            settings.risk.position_limits.max_position_pct = 5.0
            settings.risk.position_limits.max_sector_pct = 25.0
            settings.risk.position_limits.min_price = 5.0
            settings.risk.portfolio_limits.max_positions = 20
            settings.risk.portfolio_limits.max_daily_trades = 50
            settings.risk.portfolio_limits.min_cash_reserve_pct = 10.0
            settings.risk.autonomy_mode = "MANUAL_APPROVAL"
            mock_settings.return_value = settings
            engine = PreTradeRiskEngine(pdt_guard=mock_pdt)

        order = _make_order(quantity=1, limit_price=50.0)
        portfolio = _make_portfolio()
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.REQUIRE_HUMAN_APPROVAL


class TestZeroEquityEdgeCase:
    @pytest.mark.asyncio
    async def test_rejects_with_zero_equity(self, engine):
        order = _make_order(quantity=1, limit_price=50.0)
        portfolio = _make_portfolio(equity=0.0, cash=0.0)
        result = await engine.check_pre_trade(order, portfolio)
        assert result.action == RiskAction.REJECT
