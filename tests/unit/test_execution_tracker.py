"""Tests for ExecutionTracker: fill handling, day trade detection, slippage, metrics."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from src.core.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    TradeRecord,
)
from src.execution.tracker import ExecutionTracker

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tracker(mock_broker):
    """ExecutionTracker instance with mocked broker."""
    return ExecutionTracker(broker=mock_broker)


def _make_order(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 10,
    limit_price: float = 170.0,
    filled_price: float | None = 171.0,
    filled_quantity: float | None = None,
    filled_at: datetime | None = None,
    status: OrderStatus = OrderStatus.FILLED,
    strategy_name: str = "SwingMomentum",
) -> Order:
    """Helper to create Order objects for testing."""
    return Order(
        id=f"test-order-{symbol}",
        symbol=symbol,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=limit_price,
        filled_price=filled_price,
        filled_quantity=filled_quantity,
        filled_at=filled_at or datetime.utcnow(),
        status=status,
        strategy_name=strategy_name,
        broker_order_id=f"broker-{symbol}",
    )


# ---------------------------------------------------------------------------
# TestOnFill
# ---------------------------------------------------------------------------

class TestOnFill:
    """Test the on_fill method: records trades, publishes events, detects day trades."""

    @pytest.mark.asyncio
    async def test_records_trade_in_redis(self, tracker, mock_redis):
        """Should record TradeRecord in Redis for both symbol-specific and global keys."""
        order = _make_order(symbol="AAPL", filled_price=171.0)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Should push to symbol-specific and global keys
        assert mock_redis.rpush.call_count == 2
        calls = mock_redis.rpush.call_args_list

        # Check symbol-specific key
        symbol_call = [c for c in calls if "AAPL" in str(c)][0]
        assert "execution:trade_history:AAPL" in symbol_call[0]

        # Check global key
        global_call = [c for c in calls if c != symbol_call][0]
        assert "execution:trade_history" == global_call[0][0]

        # Verify trade record structure
        trade_json = calls[0][0][1]
        trade = TradeRecord.model_validate_json(trade_json)
        assert trade.symbol == "AAPL"
        assert trade.side == OrderSide.BUY
        assert trade.quantity == 10
        assert trade.entry_price == 171.0

    @pytest.mark.asyncio
    async def test_publishes_fill_event(self, tracker, mock_redis):
        """Should publish fill event via Redis publish."""
        order = _make_order(symbol="GOOG", filled_price=150.0)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Verify publish was called
        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]

        assert channel == "execution:fill_events"
        event = json.loads(payload)
        assert event["event_type"] == "fill"
        assert event["order"]["symbol"] == "GOOG"
        assert event["trade"]["entry_price"] == 150.0

    @pytest.mark.asyncio
    async def test_detects_day_trade(self, tracker, mock_redis):
        """Should detect day trade when same-day opposite-side trade exists."""
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Mock a past BUY trade from today
        past_buy = TradeRecord(
            id="past-trade",
            symbol="TSLA",
            side=OrderSide.BUY,
            quantity=5,
            entry_price=200.0,
            entry_time=datetime.utcnow(),
            strategy_name="TestStrategy",
        )
        mock_redis.lrange.return_value = [past_buy.model_dump_json()]

        # Now submit a SELL order for same symbol today
        order = _make_order(symbol="TSLA", side=OrderSide.SELL, filled_price=205.0)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Should push to day_trades key
        calls = mock_redis.rpush.call_args_list
        day_trade_calls = [c for c in calls if "day_trades" in str(c)]
        assert len(day_trade_calls) == 1
        assert today in day_trade_calls[0][0][0]

    @pytest.mark.asyncio
    async def test_price_fallback_to_limit(self, tracker, mock_redis):
        """Should use limit_price when filled_price is None."""
        order = _make_order(symbol="MSFT", filled_price=None, limit_price=420.0)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Check the trade record uses limit_price
        trade_json = mock_redis.rpush.call_args_list[0][0][1]
        trade = TradeRecord.model_validate_json(trade_json)
        assert trade.entry_price == 420.0


# ---------------------------------------------------------------------------
# TestCheckDayTrade
# ---------------------------------------------------------------------------

class TestCheckDayTrade:
    """Test the _check_day_trade method indirectly via on_fill."""

    @pytest.mark.asyncio
    async def test_same_day_opposite_side_is_day_trade(self, tracker, mock_redis):
        """Same-day opposite-side trade should return True."""
        # Mock a BUY from today
        past_buy = TradeRecord(
            id="buy-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            entry_price=180.0,
            entry_time=datetime.utcnow(),
            strategy_name="Test",
        )
        mock_redis.lrange.return_value = [past_buy.model_dump_json()]

        # SELL today
        order = _make_order(symbol="AAPL", side=OrderSide.SELL)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Verify day trade detected
        day_trade_calls = [c for c in mock_redis.rpush.call_args_list if "day_trades" in str(c)]
        assert len(day_trade_calls) == 1

    @pytest.mark.asyncio
    async def test_different_day_not_day_trade(self, tracker, mock_redis):
        """Different day should return False."""
        from datetime import timedelta

        # Mock a BUY from 2 days ago
        past_buy = TradeRecord(
            id="buy-old",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            entry_price=180.0,
            entry_time=datetime.utcnow() - timedelta(days=2),
            strategy_name="Test",
        )
        mock_redis.lrange.return_value = [past_buy.model_dump_json()]

        # SELL today
        order = _make_order(symbol="AAPL", side=OrderSide.SELL)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Verify no day trade detected
        day_trade_calls = [c for c in mock_redis.rpush.call_args_list if "day_trades" in str(c)]
        assert len(day_trade_calls) == 0

    @pytest.mark.asyncio
    async def test_same_side_not_day_trade(self, tracker, mock_redis):
        """Same-side trade (BUY after BUY) should not be a day trade."""
        # Mock a BUY from today
        past_buy = TradeRecord(
            id="buy-1",
            symbol="NVDA",
            side=OrderSide.BUY,
            quantity=5,
            entry_price=500.0,
            entry_time=datetime.utcnow(),
            strategy_name="Test",
        )
        mock_redis.lrange.return_value = [past_buy.model_dump_json()]

        # Another BUY today
        order = _make_order(symbol="NVDA", side=OrderSide.BUY)

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            await tracker.on_fill(order)

        # Verify no day trade detected
        day_trade_calls = [c for c in mock_redis.rpush.call_args_list if "day_trades" in str(c)]
        assert len(day_trade_calls) == 0


# ---------------------------------------------------------------------------
# TestSlippage
# ---------------------------------------------------------------------------

class TestSlippage:
    """Test the _calculate_slippage static method."""

    def test_correct_slippage_calculation(self):
        """Should calculate slippage correctly."""
        order = _make_order(filled_price=171.0, limit_price=170.0)
        slippage = ExecutionTracker._calculate_slippage(order)

        # |171 - 170| / 170 * 100 = 0.5882%
        assert slippage is not None
        assert abs(slippage - 0.5882) < 0.001

    def test_missing_filled_price_returns_none(self):
        """Should return None when filled_price is None."""
        order = _make_order(filled_price=None, limit_price=170.0)
        slippage = ExecutionTracker._calculate_slippage(order)
        assert slippage is None

    def test_zero_limit_price_returns_none(self):
        """Should return None when limit_price is zero (avoid division by zero)."""
        order = _make_order(filled_price=171.0, limit_price=0.0)
        slippage = ExecutionTracker._calculate_slippage(order)
        assert slippage is None


# ---------------------------------------------------------------------------
# TestMetrics
# ---------------------------------------------------------------------------

class TestMetrics:
    """Test the get_execution_metrics method."""

    @pytest.mark.asyncio
    async def test_no_trades_returns_zeroes(self, tracker, mock_redis):
        """Should return zeroes when no trades exist."""
        mock_redis.lrange.return_value = []
        mock_redis.hlen.return_value = 0

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            metrics = await tracker.get_execution_metrics()

        assert metrics["total_trades"] == 0
        assert metrics["fill_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_with_trades_returns_correct_fill_rate(self, tracker, mock_redis):
        """Should calculate fill rate correctly when trades exist."""
        # Mock 8 filled trades
        trades = [
            TradeRecord(
                id=f"trade-{i}",
                symbol="AAPL",
                side=OrderSide.BUY,
                quantity=10,
                entry_price=180.0,
                entry_time=datetime.utcnow(),
                strategy_name="Test",
            ).model_dump_json()
            for i in range(8)
        ]
        mock_redis.lrange.return_value = trades
        mock_redis.hlen.return_value = 2  # 2 open orders

        with patch("src.execution.tracker.get_redis", return_value=mock_redis):
            metrics = await tracker.get_execution_metrics()

        assert metrics["total_trades"] == 8
        assert metrics["open_orders"] == 2
        # fill_rate = 8 / (8 + 2) = 0.8
        assert abs(metrics["fill_rate"] - 0.8) < 0.001
