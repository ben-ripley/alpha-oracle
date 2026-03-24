"""Tests for the order generator: Kelly criterion, position sizing, edge cases."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.models import (
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    Position,
    Signal,
    SignalDirection,
)
from src.execution.order_generator import OrderGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator():
    with patch("src.execution.order_generator.get_settings") as mock_settings:
        settings = MagicMock()
        settings.execution.default_order_type = "limit"
        settings.execution.limit_offset_pct = 0.05
        settings.execution.max_slippage_pct = 0.10
        settings.execution.position_sizing = "half_kelly"
        settings.risk.position_limits.max_position_pct = 5.0
        settings.risk.position_limits.stop_loss_pct = 2.0
        settings.risk.portfolio_limits.min_cash_reserve_pct = 10.0
        mock_settings.return_value = settings
        gen = OrderGenerator()
    return gen


def _make_signal(
    symbol: str = "AAPL",
    direction: SignalDirection = SignalDirection.LONG,
    strength: float = 0.75,
    latest_price: float = 180.0,
    win_rate: float = 0.58,
    avg_win_pct: float = 3.0,
    avg_loss_pct: float = 1.5,
) -> Signal:
    return Signal(
        symbol=symbol,
        timestamp=datetime.utcnow(),
        direction=direction,
        strength=strength,
        strategy_name="SwingMomentum",
        metadata={
            "latest_price": latest_price,
            "win_rate": win_rate,
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
        },
    )


def _make_portfolio(
    equity: float = 20000.0,
    cash: float = 15000.0,
    positions: list[Position] | None = None,
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        total_equity=equity,
        cash=cash,
        positions_value=equity - cash,
        positions=positions or [],
    )


# ---------------------------------------------------------------------------
# Kelly Criterion Tests
# ---------------------------------------------------------------------------

class TestKellyCriterion:
    def test_positive_expectation(self):
        """Typical winning strategy: 58% win rate, 2:1 reward-risk."""
        kelly = OrderGenerator.kelly_criterion(0.58, 3.0, 1.5)
        assert kelly > 0
        assert kelly < 0.25  # capped at 25%

    def test_breakeven_returns_zero(self):
        """50% win rate with 1:1 = zero edge."""
        kelly = OrderGenerator.kelly_criterion(0.50, 1.0, 1.0)
        assert kelly == 0.0

    def test_negative_expectation_returns_zero(self):
        """Losing strategy returns zero allocation."""
        kelly = OrderGenerator.kelly_criterion(0.40, 1.0, 1.5)
        assert kelly == 0.0

    def test_zero_win_rate(self):
        kelly = OrderGenerator.kelly_criterion(0.0, 3.0, 1.5)
        assert kelly == 0.0

    def test_100_pct_win_rate(self):
        kelly = OrderGenerator.kelly_criterion(1.0, 3.0, 1.5)
        assert kelly == 0.0  # edge case: win_rate >= 1 returns 0

    def test_zero_avg_loss(self):
        kelly = OrderGenerator.kelly_criterion(0.6, 3.0, 0.0)
        assert kelly == 0.0

    def test_half_kelly(self):
        """Result should be half of full Kelly for safety."""
        # Full Kelly: (0.6 * 2 - 0.4) / 2 = 0.4
        # Half Kelly: 0.2
        kelly = OrderGenerator.kelly_criterion(0.6, 2.0, 1.0)
        assert abs(kelly - 0.2) < 0.001

    def test_capped_at_25_percent(self):
        """Even extreme edge should be capped at 25%."""
        kelly = OrderGenerator.kelly_criterion(0.95, 10.0, 0.1)
        assert kelly <= 0.25


# ---------------------------------------------------------------------------
# Order Generation Tests
# ---------------------------------------------------------------------------

class TestGenerateOrder:
    def test_basic_long_order(self, generator):
        signal = _make_signal()
        portfolio = _make_portfolio()
        order = generator.generate_order(signal, portfolio)
        assert order.symbol == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.quantity > 0
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price is not None
        assert order.stop_price is not None
        assert order.strategy_name == "SwingMomentum"
        assert order.signal_strength == 0.75

    def test_short_signal_generates_sell(self, generator):
        signal = _make_signal(direction=SignalDirection.SHORT)
        portfolio = _make_portfolio(
            positions=[Position(
                symbol="AAPL", quantity=10, avg_entry_price=175.0,
                current_price=180.0, market_value=1800.0,
            )]
        )
        order = generator.generate_order(signal, portfolio)
        assert order.side == OrderSide.SELL

    def test_flat_signal_raises(self, generator):
        signal = _make_signal(direction=SignalDirection.FLAT)
        portfolio = _make_portfolio()
        with pytest.raises(ValueError, match="FLAT"):
            generator.generate_order(signal, portfolio)

    def test_limit_price_offset_for_buy(self, generator):
        """Buy limit should be slightly above current price."""
        signal = _make_signal(latest_price=100.0)
        portfolio = _make_portfolio()
        order = generator.generate_order(signal, portfolio)
        assert order.limit_price is not None
        assert order.limit_price > 100.0  # offset above

    def test_stop_loss_for_buy(self, generator):
        """Stop loss should be below entry for buys."""
        signal = _make_signal(latest_price=100.0)
        portfolio = _make_portfolio()
        order = generator.generate_order(signal, portfolio)
        assert order.stop_price is not None
        assert order.stop_price < 100.0
        # 2% stop loss
        assert order.stop_price == pytest.approx(98.0, abs=0.01)

    def test_unique_order_ids(self, generator):
        signal = _make_signal()
        portfolio = _make_portfolio()
        order1 = generator.generate_order(signal, portfolio)
        order2 = generator.generate_order(signal, portfolio)
        assert order1.id != order2.id


# ---------------------------------------------------------------------------
# Position Sizing Tests
# ---------------------------------------------------------------------------

class TestCalculateQuantity:
    def test_respects_max_position_pct(self, generator):
        """Quantity should not exceed 5% of equity."""
        signal = _make_signal(latest_price=10.0, strength=1.0)
        portfolio = _make_portfolio(equity=20000.0, cash=15000.0)
        order = generator.generate_order(signal, portfolio)
        order_value = order.quantity * 10.0
        assert order_value <= 20000.0 * 0.05 + 10.0  # tolerance of 1 share

    def test_scales_by_signal_strength(self, generator):
        """Weaker signals should produce smaller positions."""
        portfolio = _make_portfolio(equity=20000.0, cash=15000.0)
        signal_strong = _make_signal(strength=1.0, latest_price=50.0)
        signal_weak = _make_signal(strength=0.3, latest_price=50.0)
        order_strong = generator.generate_order(signal_strong, portfolio)
        order_weak = generator.generate_order(signal_weak, portfolio)
        assert order_strong.quantity >= order_weak.quantity

    def test_respects_cash_reserve(self, generator):
        """Should not use cash below the 10% reserve."""
        # $20K equity, 10% reserve = $2K min cash
        # Available: $3000 - $2000 = $1000
        signal = _make_signal(latest_price=50.0, strength=1.0)
        portfolio = _make_portfolio(equity=20000.0, cash=3000.0)
        order = generator.generate_order(signal, portfolio)
        order_cost = order.quantity * 50.0
        cash_after = 3000.0 - order_cost
        assert cash_after >= 2000.0 - 50.0  # tolerance of 1 share

    def test_zero_cash_returns_zero_quantity(self, generator):
        """No cash available -> cannot buy."""
        signal = _make_signal(latest_price=50.0)
        portfolio = _make_portfolio(equity=20000.0, cash=1000.0)  # below 10% reserve
        with pytest.raises(ValueError, match="zero quantity"):
            generator.generate_order(signal, portfolio)

    def test_whole_shares_only(self, generator):
        """Quantity should be whole number."""
        signal = _make_signal(latest_price=173.42)
        portfolio = _make_portfolio()
        order = generator.generate_order(signal, portfolio)
        assert order.quantity == int(order.quantity)

    def test_zero_price_signal(self, generator):
        """Signal with no price info should produce zero quantity."""
        signal = _make_signal(latest_price=0.0)
        portfolio = _make_portfolio()
        with pytest.raises(ValueError):
            generator.generate_order(signal, portfolio)
