"""Tests for SimulatedBroker — in-memory BrokerAdapter."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import (
    OHLCV,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)
from src.execution.broker_adapters.simulated_broker import (
    SimulatedBroker,
    _BUY_SLIPPAGE,
    _SELL_SLIPPAGE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(symbol: str = "AAPL", close: float = 150.0) -> OHLCV:
    return OHLCV(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        open=close * 0.99,
        high=close * 1.01,
        low=close * 0.98,
        close=close,
        volume=1_000_000,
    )


def _buy_order(
    symbol: str = "AAPL",
    qty: float = 10.0,
    limit_price: float | None = None,
) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=qty,
        limit_price=limit_price,
    )


def _sell_order(
    symbol: str = "AAPL",
    qty: float = 10.0,
    limit_price: float | None = None,
) -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=qty,
        limit_price=limit_price,
    )


def _mock_storage(close: float = 150.0, symbol: str = "AAPL"):
    """Return a context-manager patch that makes TimeSeriesStorage.get_ohlcv
    return a single bar with the given close price."""
    mock_instance = MagicMock()
    mock_instance.get_ohlcv = AsyncMock(return_value=[_make_ohlcv(symbol, close)])
    mock_cls = MagicMock(return_value=mock_instance)
    return patch("src.data.storage.TimeSeriesStorage", mock_cls)


def _mock_storage_empty():
    """Return a patch that makes get_ohlcv return an empty list."""
    mock_instance = MagicMock()
    mock_instance.get_ohlcv = AsyncMock(return_value=[])
    mock_cls = MagicMock(return_value=mock_instance)
    return patch("src.data.storage.TimeSeriesStorage", mock_cls)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuyOrder:
    @pytest.mark.asyncio
    async def test_buy_creates_position(self):
        broker = SimulatedBroker(initial_cash=10_000.0)
        close = 150.0
        qty = 10.0
        with _mock_storage(close):
            order = await broker.submit_order(_buy_order(qty=qty))

        assert order.status == OrderStatus.FILLED
        assert "AAPL" in broker._positions
        pos = broker._positions["AAPL"]
        assert pos.quantity == qty

    @pytest.mark.asyncio
    async def test_buy_reduces_cash(self):
        broker = SimulatedBroker(initial_cash=10_000.0)
        close = 150.0
        qty = 10.0
        with _mock_storage(close):
            await broker.submit_order(_buy_order(qty=qty))

        fill_price = close * _BUY_SLIPPAGE
        expected_cash = 10_000.0 - qty * fill_price
        assert abs(broker._cash - expected_cash) < 0.01

    @pytest.mark.asyncio
    async def test_buy_slippage(self):
        broker = SimulatedBroker()
        close = 200.0
        with _mock_storage(close):
            order = await broker.submit_order(_buy_order())

        assert order.filled_price == pytest.approx(close * _BUY_SLIPPAGE)


class TestSellOrder:
    @pytest.mark.asyncio
    async def test_sell_reduces_position(self):
        broker = SimulatedBroker(initial_cash=10_000.0)
        with _mock_storage(150.0):
            await broker.submit_order(_buy_order(qty=10.0))
            order = await broker.submit_order(_sell_order(qty=5.0))

        assert order.status == OrderStatus.FILLED
        assert broker._positions["AAPL"].quantity == pytest.approx(5.0)

    @pytest.mark.asyncio
    async def test_sell_increases_cash(self):
        broker = SimulatedBroker(initial_cash=10_000.0)
        close = 150.0
        with _mock_storage(close):
            await broker.submit_order(_buy_order(qty=10.0))
            cash_after_buy = broker._cash
            await broker.submit_order(_sell_order(qty=5.0))

        fill_price = close * _SELL_SLIPPAGE
        assert broker._cash == pytest.approx(cash_after_buy + 5.0 * fill_price)

    @pytest.mark.asyncio
    async def test_sell_slippage(self):
        broker = SimulatedBroker()
        close = 200.0
        with _mock_storage(close):
            await broker.submit_order(_buy_order(qty=10.0))
            order = await broker.submit_order(_sell_order(qty=5.0))

        assert order.filled_price == pytest.approx(close * _SELL_SLIPPAGE)

    @pytest.mark.asyncio
    async def test_sell_entire_position_removes_it(self):
        broker = SimulatedBroker()
        with _mock_storage(150.0):
            await broker.submit_order(_buy_order(qty=10.0))
            await broker.submit_order(_sell_order(qty=10.0))

        assert "AAPL" not in broker._positions

    @pytest.mark.asyncio
    async def test_oversell_rejected(self):
        broker = SimulatedBroker(initial_cash=10_000.0)
        cash_before = broker._cash
        with _mock_storage(150.0):
            await broker.submit_order(_buy_order(qty=5.0))
            cash_after_buy = broker._cash
            order = await broker.submit_order(_sell_order(qty=10.0))

        assert order.status == OrderStatus.REJECTED
        assert "insufficient position" in order.metadata.get("rejection_reason", "")
        # Cash and position unchanged by the rejected sell
        assert broker._cash == pytest.approx(cash_after_buy)
        assert broker._positions["AAPL"].quantity == pytest.approx(5.0)


class TestNoPriceData:
    @pytest.mark.asyncio
    async def test_no_price_data_no_limit_rejected(self):
        broker = SimulatedBroker()
        with _mock_storage_empty():
            order = await broker.submit_order(_buy_order(limit_price=None))

        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_no_price_data_uses_limit_price(self):
        broker = SimulatedBroker()
        limit = 150.0
        with _mock_storage_empty():
            order = await broker.submit_order(_buy_order(limit_price=limit))

        assert order.status == OrderStatus.FILLED
        # slippage applied to limit_price
        assert order.filled_price == pytest.approx(limit * _BUY_SLIPPAGE)


class TestAverageEntryPrice:
    @pytest.mark.asyncio
    async def test_successive_buys_average_entry(self):
        broker = SimulatedBroker(initial_cash=50_000.0)
        # First buy: 10 shares @ 100
        with _mock_storage(100.0):
            await broker.submit_order(_buy_order(qty=10.0))
        # Second buy: 10 shares @ 120
        with _mock_storage(120.0):
            await broker.submit_order(_buy_order(qty=10.0))

        pos = broker._positions["AAPL"]
        assert pos.quantity == pytest.approx(20.0)
        # avg = (10*100*BUY_SLIP + 10*120*BUY_SLIP) / 20
        expected_avg = (10 * 100 * _BUY_SLIPPAGE + 10 * 120 * _BUY_SLIPPAGE) / 20
        assert pos.avg_entry_price == pytest.approx(expected_avg)


class TestGetPortfolio:
    @pytest.mark.asyncio
    async def test_initial_portfolio_is_empty(self):
        broker = SimulatedBroker(initial_cash=20_000.0)
        with _mock_storage_empty():
            snapshot = await broker.get_portfolio()

        assert snapshot.cash == pytest.approx(20_000.0)
        assert snapshot.positions_value == pytest.approx(0.0)
        assert snapshot.total_equity == pytest.approx(20_000.0)
        assert snapshot.positions == []

    @pytest.mark.asyncio
    async def test_portfolio_equity_after_buy(self):
        broker = SimulatedBroker(initial_cash=10_000.0)
        close = 150.0
        qty = 10.0
        with _mock_storage(close):
            await broker.submit_order(_buy_order(qty=qty))
            snapshot = await broker.get_portfolio()

        fill_price = close * _BUY_SLIPPAGE
        expected_cash = 10_000.0 - qty * fill_price
        # current_price refreshed to close in get_portfolio
        expected_positions_value = qty * close
        expected_equity = expected_cash + expected_positions_value
        assert snapshot.cash == pytest.approx(expected_cash)
        assert snapshot.positions_value == pytest.approx(expected_positions_value)
        assert snapshot.total_equity == pytest.approx(expected_equity)

    @pytest.mark.asyncio
    async def test_sector_exposure_aggregated(self):
        broker = SimulatedBroker(initial_cash=50_000.0)
        close = 100.0

        # Two buys in different sectors
        with _mock_storage(close, "AAPL"):
            order_aapl = _buy_order("AAPL", qty=10.0)
            filled = await broker.submit_order(order_aapl)
            broker._positions["AAPL"].sector = "Technology"

        with _mock_storage(close, "JPM"):
            order_jpm = _buy_order("JPM", qty=10.0)
            await broker.submit_order(order_jpm)
            broker._positions["JPM"].sector = "Financials"

        with _mock_storage(close):
            snapshot = await broker.get_portfolio()

        assert "Technology" in snapshot.sector_exposure
        assert "Financials" in snapshot.sector_exposure


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_pending_order(self):
        broker = SimulatedBroker()
        order = Order(
            id="test-id",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10.0,
            status=OrderStatus.PENDING,
            broker_order_id="sim-test-id",
        )
        broker._orders["test-id"] = order

        result = await broker.cancel_order("sim-test-id")

        assert result is True
        assert broker._orders["test-id"].status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_filled_order_returns_false(self):
        broker = SimulatedBroker()
        close = 150.0
        with _mock_storage(close):
            order = await broker.submit_order(_buy_order())

        result = await broker.cancel_order(order.broker_order_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_unknown_order_returns_false(self):
        broker = SimulatedBroker()
        result = await broker.cancel_order("nonexistent-id")
        assert result is False


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_always_true(self):
        broker = SimulatedBroker()
        assert await broker.health_check() is True


class TestOrderId:
    @pytest.mark.asyncio
    async def test_order_id_assigned_if_blank(self):
        broker = SimulatedBroker()
        with _mock_storage(150.0):
            order = await broker.submit_order(_buy_order())
        assert order.id != ""
        assert order.broker_order_id.startswith("sim-")

    @pytest.mark.asyncio
    async def test_existing_order_id_preserved(self):
        broker = SimulatedBroker()
        with _mock_storage(150.0):
            o = _buy_order()
            o.id = "my-custom-id"
            order = await broker.submit_order(o)
        assert order.id == "my-custom-id"
