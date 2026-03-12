"""Tests for core Pydantic models: validation, serialization, edge cases."""
from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.core.models import (
    OHLCV,
    AutonomyMode,
    BacktestResult,
    FundamentalData,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PortfolioSnapshot,
    RiskAction,
    RiskCheckResult,
    Signal,
    SignalDirection,
    StrategyRanking,
    TradeRecord,
)


class TestOHLCV:
    def test_basic_creation(self):
        bar = OHLCV(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2),
            open=150.0,
            high=155.0,
            low=149.0,
            close=153.0,
            volume=5000000,
        )
        assert bar.symbol == "AAPL"
        assert bar.close == 153.0
        assert bar.source == ""
        assert bar.adjusted_close is None

    def test_with_optional_fields(self):
        bar = OHLCV(
            symbol="MSFT",
            timestamp=datetime(2024, 1, 2),
            open=400.0,
            high=410.0,
            low=395.0,
            close=405.0,
            volume=3000000,
            source="ibkr",
            adjusted_close=404.50,
        )
        assert bar.source == "ibkr"
        assert bar.adjusted_close == 404.50

    def test_serialization_round_trip(self):
        bar = OHLCV(
            symbol="GOOG",
            timestamp=datetime(2024, 6, 15, 14, 30),
            open=175.0,
            high=178.0,
            low=174.0,
            close=177.0,
            volume=2000000,
        )
        json_str = bar.model_dump_json()
        restored = OHLCV.model_validate_json(json_str)
        assert restored.symbol == bar.symbol
        assert restored.close == bar.close
        assert restored.timestamp == bar.timestamp


class TestSignal:
    def test_valid_signal(self):
        sig = Signal(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            direction=SignalDirection.LONG,
            strength=0.85,
            strategy_name="SwingMomentum",
        )
        assert sig.direction == SignalDirection.LONG
        assert sig.strength == 0.85

    def test_strength_bounds(self):
        with pytest.raises(ValidationError):
            Signal(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                direction=SignalDirection.LONG,
                strength=1.5,  # > 1.0
                strategy_name="test",
            )

        with pytest.raises(ValidationError):
            Signal(
                symbol="AAPL",
                timestamp=datetime.utcnow(),
                direction=SignalDirection.LONG,
                strength=-0.1,  # < 0.0
                strategy_name="test",
            )

    def test_signal_directions(self):
        for direction in SignalDirection:
            sig = Signal(
                symbol="TEST",
                timestamp=datetime.utcnow(),
                direction=direction,
                strength=0.5,
                strategy_name="test",
            )
            assert sig.direction == direction

    def test_metadata(self):
        sig = Signal(
            symbol="AAPL",
            timestamp=datetime.utcnow(),
            direction=SignalDirection.LONG,
            strength=0.7,
            strategy_name="test",
            metadata={"rsi": 45.2, "ma_cross": True},
        )
        assert sig.metadata["rsi"] == 45.2
        assert sig.metadata["ma_cross"] is True


class TestOrder:
    def test_default_values(self):
        order = Order(
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        assert order.status == OrderStatus.PENDING
        assert order.limit_price is None
        assert order.filled_at is None
        assert order.broker_order_id == ""

    def test_limit_order(self):
        order = Order(
            symbol="MSFT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=5,
            limit_price=420.50,
            stop_price=410.0,
        )
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 420.50
        assert order.stop_price == 410.0

    def test_serialization_round_trip(self):
        order = Order(
            id="test-123",
            symbol="GOOG",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LIMIT,
            quantity=15,
            limit_price=170.0,
            stop_price=165.0,
            strategy_name="MeanReversion",
            signal_strength=0.65,
            metadata={"reason": "stop_loss"},
        )
        json_str = order.model_dump_json()
        restored = Order.model_validate_json(json_str)
        assert restored.id == order.id
        assert restored.symbol == order.symbol
        assert restored.limit_price == order.limit_price
        assert restored.metadata["reason"] == "stop_loss"


class TestPosition:
    def test_basic_position(self):
        pos = Position(
            symbol="AAPL",
            quantity=10,
            avg_entry_price=178.0,
            current_price=183.0,
            market_value=1830.0,
            unrealized_pnl=50.0,
            unrealized_pnl_pct=2.81,
        )
        assert pos.symbol == "AAPL"
        assert pos.unrealized_pnl == 50.0
        assert pos.sector == ""


class TestPortfolioSnapshot:
    def test_empty_portfolio(self):
        snap = PortfolioSnapshot(
            total_equity=20000.0,
            cash=20000.0,
            positions_value=0.0,
        )
        assert len(snap.positions) == 0
        assert snap.daily_pnl == 0.0
        assert snap.sector_exposure == {}

    def test_with_positions(self, sample_portfolio):
        assert sample_portfolio.total_equity == 20000.0
        assert len(sample_portfolio.positions) == 3
        assert "Technology" in sample_portfolio.sector_exposure


class TestRiskCheckResult:
    def test_approve(self):
        result = RiskCheckResult(action=RiskAction.APPROVE)
        assert result.action == RiskAction.APPROVE
        assert result.reasons == []
        assert result.adjusted_quantity is None

    def test_reject_with_reasons(self):
        result = RiskCheckResult(
            action=RiskAction.REJECT,
            reasons=["Position too large", "Sector limit exceeded"],
        )
        assert result.action == RiskAction.REJECT
        assert len(result.reasons) == 2

    def test_reduce_size(self):
        result = RiskCheckResult(
            action=RiskAction.REDUCE_SIZE,
            adjusted_quantity=5.0,
            reasons=["Reduced from 10 to 5 shares"],
        )
        assert result.adjusted_quantity == 5.0


class TestEnums:
    def test_autonomy_modes(self):
        assert AutonomyMode.PAPER_ONLY.value == "PAPER_ONLY"
        assert AutonomyMode.MANUAL_APPROVAL.value == "MANUAL_APPROVAL"
        assert AutonomyMode.BOUNDED_AUTONOMOUS.value == "BOUNDED_AUTONOMOUS"
        assert AutonomyMode.FULL_AUTONOMOUS.value == "FULL_AUTONOMOUS"

    def test_order_statuses(self):
        terminal = {OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.EXPIRED}
        active = {OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        assert len(terminal | active) == len(OrderStatus)

    def test_risk_actions(self):
        actions = set(RiskAction)
        assert RiskAction.APPROVE in actions
        assert RiskAction.REJECT in actions
        assert RiskAction.REQUIRE_HUMAN_APPROVAL in actions
        assert RiskAction.REDUCE_SIZE in actions


class TestTradeRecord:
    def test_day_trade_flag(self):
        trade = TradeRecord(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            entry_price=178.0,
            entry_time=datetime(2024, 1, 2, 10, 0),
            exit_price=180.0,
            exit_time=datetime(2024, 1, 2, 15, 0),
            pnl=20.0,
            pnl_pct=1.12,
            is_day_trade=True,
        )
        assert trade.is_day_trade is True
        assert trade.pnl == 20.0

    def test_open_trade(self):
        trade = TradeRecord(
            symbol="MSFT",
            side=OrderSide.BUY,
            quantity=5,
            entry_price=415.0,
            entry_time=datetime(2024, 1, 2, 10, 0),
        )
        assert trade.exit_price is None
        assert trade.exit_time is None
        assert trade.pnl == 0.0


class TestBacktestResult:
    def test_basic_result(self):
        result = BacktestResult(
            strategy_name="SwingMomentum",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
            initial_capital=20000.0,
            final_capital=28000.0,
            total_return_pct=40.0,
            annual_return_pct=8.8,
            sharpe_ratio=1.42,
            sortino_ratio=1.78,
            max_drawdown_pct=12.3,
            profit_factor=1.82,
            total_trades=247,
            winning_trades=143,
            losing_trades=104,
            win_rate=57.9,
            avg_win_pct=3.2,
            avg_loss_pct=1.8,
        )
        assert result.sharpe_ratio == 1.42
        assert result.total_trades == 247
        assert result.equity_curve == []
