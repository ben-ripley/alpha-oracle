"""Unit tests for IBKRBrokerAdapter."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import Order, OrderSide, OrderStatus, OrderType
from src.execution.broker_adapters.ibkr_adapter import (
    _IBKR_STATUS_MAP,
    _MAX_RECONNECT_ATTEMPTS,
    IBKRBrokerAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_settings(account_id: str = "") -> MagicMock:
    settings = MagicMock()
    settings.broker.ibkr.host = "127.0.0.1"
    settings.broker.ibkr.port = 4002
    settings.broker.ibkr.client_id = 1
    settings.broker.ibkr.account_id = account_id
    settings.broker.paper_trading = True
    return settings


def _make_ib_instance() -> MagicMock:
    """Return a MagicMock wired up to look like an ib_async.IB client."""
    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.connectAsync = AsyncMock()
    ib.qualifyContractsAsync = AsyncMock()
    ib.placeOrder = MagicMock()
    ib.cancelOrder = MagicMock()
    ib.openTrades.return_value = []
    ib.trades.return_value = []
    ib.reqPositionsAsync = AsyncMock(return_value=[])
    ib.reqAccountSummaryAsync = AsyncMock(return_value=[])
    return ib


@pytest.fixture()
def ib(request):
    """Yields (adapter, ib_instance, mock_module) with ib_async fully mocked."""
    ib_instance = _make_ib_instance()
    account_id = getattr(request, "param", "")
    mock_module = MagicMock()
    mock_module.IB.return_value = ib_instance

    with patch.dict("sys.modules", {"ib_async": mock_module}):
        adapter = IBKRBrokerAdapter(_make_settings(account_id=account_id))
        yield adapter, ib_instance, mock_module


def _make_trade(order_id: int, status: str, filled_price: float = 0.0) -> MagicMock:
    trade = MagicMock()
    trade.order.orderId = order_id
    trade.orderStatus.status = status
    trade.orderStatus.avgFillPrice = filled_price
    return trade


def _make_ib_position(
    symbol: str,
    sec_type: str,
    qty: float,
    avg_cost: float,
) -> MagicMock:
    pos = MagicMock()
    pos.contract.symbol = symbol
    pos.contract.secType = sec_type
    pos.position = qty
    pos.avgCost = avg_cost
    return pos


def _make_summary_item(account: str, tag: str, value: str) -> MagicMock:
    item = MagicMock()
    item.account = account
    item.tag = tag
    item.value = value
    return item


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------

class TestStatusMapping:
    def test_all_ibkr_statuses_map_to_valid_order_status(self):
        known = [
            "apipending", "pendingsubmit", "apicancelled", "cancelled",
            "presubmitted", "pendingcancel", "submitted", "filled", "inactive",
        ]
        for status in known:
            mapped = _IBKR_STATUS_MAP.get(status)
            assert mapped is not None, f"Status '{status}' has no mapping"
            assert isinstance(mapped, OrderStatus)

    def test_unknown_status_defaults_to_submitted(self):
        result = _IBKR_STATUS_MAP.get("totally_unknown", OrderStatus.SUBMITTED)
        assert result == OrderStatus.SUBMITTED

    def test_terminal_statuses_mapped_correctly(self):
        assert _IBKR_STATUS_MAP["filled"] == OrderStatus.FILLED
        assert _IBKR_STATUS_MAP["cancelled"] == OrderStatus.CANCELLED
        assert _IBKR_STATUS_MAP["apicancelled"] == OrderStatus.CANCELLED
        assert _IBKR_STATUS_MAP["inactive"] == OrderStatus.REJECTED

    def test_pending_statuses_mapped_correctly(self):
        assert _IBKR_STATUS_MAP["apipending"] == OrderStatus.PENDING
        assert _IBKR_STATUS_MAP["pendingsubmit"] == OrderStatus.PENDING

    def test_in_flight_statuses_mapped_to_submitted(self):
        for status in ("presubmitted", "pendingcancel", "submitted"):
            assert _IBKR_STATUS_MAP[status] == OrderStatus.SUBMITTED


# ---------------------------------------------------------------------------
# _ensure_connected
# ---------------------------------------------------------------------------

class TestEnsureConnected:
    @pytest.mark.asyncio
    async def test_skips_connect_when_already_connected(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.isConnected.return_value = True
        await adapter._ensure_connected()
        ib_instance.connectAsync.assert_not_called()

    @pytest.mark.asyncio
    async def test_connects_when_not_connected(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.isConnected.return_value = False
        await adapter._ensure_connected()
        ib_instance.connectAsync.assert_awaited_once_with(
            host="127.0.0.1", port=4002, clientId=1
        )

    @pytest.mark.asyncio
    async def test_retries_on_first_failure_then_succeeds(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = False
        # First attempt raises; second attempt succeeds (no side_effect = returns None).
        ib_instance.connectAsync.side_effect = [ConnectionError("timeout"), None]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await adapter._ensure_connected()

        assert ib_instance.connectAsync.await_count == 2

    @pytest.mark.asyncio
    async def test_raises_connection_error_after_max_retries(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = False
        ib_instance.connectAsync.side_effect = ConnectionError("gateway down")

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ConnectionError, match="IBKR connect failed"):
                await adapter._ensure_connected()

        assert ib_instance.connectAsync.await_count == _MAX_RECONNECT_ATTEMPTS

    @pytest.mark.asyncio
    async def test_exponential_backoff_between_attempts(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = False
        ib_instance.connectAsync.side_effect = ConnectionError("gateway down")

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ConnectionError):
                await adapter._ensure_connected()

        # sleep is called between attempts: N-1 times for N attempts
        assert mock_sleep.await_count == _MAX_RECONNECT_ATTEMPTS - 1
        # Verify exponential growth: first sleep=2^1=2, second=2^2=4
        sleep_args = [call.args[0] for call in mock_sleep.await_args_list]
        assert sleep_args == [2 ** i for i in range(1, _MAX_RECONNECT_ATTEMPTS)]

    @pytest.mark.asyncio
    async def test_no_sleep_when_first_attempt_succeeds(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = False
        # connectAsync has no side_effect — succeeds immediately.

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await adapter._ensure_connected()

        mock_sleep.assert_not_awaited()


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_calls_ib_disconnect_when_connected(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = True

        await adapter.disconnect()

        ib_instance.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_skips_when_not_connected(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = False

        await adapter.disconnect()

        ib_instance.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_swallows_exception(self, ib):
        adapter, ib_instance, _ = ib
        ib_instance.isConnected.return_value = True
        ib_instance.disconnect.side_effect = RuntimeError("IB internal error")

        # Must not propagate.
        await adapter.disconnect()


# ---------------------------------------------------------------------------
# submit_order
# ---------------------------------------------------------------------------

class TestSubmitOrder:
    def _trade(self, order_id: int = 42, status: str = "Submitted") -> MagicMock:
        return _make_trade(order_id, status)

    @pytest.mark.asyncio
    async def test_market_buy_order_submitted(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=10, status="Submitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=5)
        result = await adapter.submit_order(order)

        ib_instance.placeOrder.assert_called_once()
        assert result.broker_order_id == "10"
        assert result.status == OrderStatus.SUBMITTED
        assert result.id != ""

    @pytest.mark.asyncio
    async def test_market_sell_order_submitted(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=11, status="Submitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(symbol="TSLA", side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=3)
        result = await adapter.submit_order(order)

        # Verify MarketOrder was constructed with action="SELL"
        action, _qty = mock_module.MarketOrder.call_args[0]
        assert action == "SELL"
        assert result.broker_order_id == "11"

    @pytest.mark.asyncio
    async def test_limit_buy_order_submitted(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=20, status="PreSubmitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(
            symbol="MSFT", side=OrderSide.BUY, order_type=OrderType.LIMIT,
            quantity=10, limit_price=420.0,
        )
        result = await adapter.submit_order(order)

        # Verify LimitOrder was constructed with the correct limit price
        _action, _qty, limit_price = mock_module.LimitOrder.call_args[0]
        assert limit_price == 420.0
        assert result.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_limit_order_without_price_raises(self, ib):
        adapter, ib_instance, mock_module = ib
        order = Order(
            symbol="GOOG", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=2
        )
        with pytest.raises(ValueError, match="limit_price"):
            await adapter.submit_order(order)

    @pytest.mark.asyncio
    async def test_stop_order_submitted(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=30, status="Submitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(
            symbol="NVDA", side=OrderSide.SELL, order_type=OrderType.STOP,
            quantity=5, stop_price=800.0,
        )
        result = await adapter.submit_order(order)

        # Verify StopOrder was constructed with the correct stop price
        _action, _qty, stop_price = mock_module.StopOrder.call_args[0]
        assert stop_price == 800.0
        assert result.broker_order_id == "30"

    @pytest.mark.asyncio
    async def test_stop_order_without_price_raises(self, ib):
        adapter, ib_instance, mock_module = ib
        order = Order(
            symbol="NVDA", side=OrderSide.SELL, order_type=OrderType.STOP, quantity=5
        )
        with pytest.raises(ValueError, match="stop_price"):
            await adapter.submit_order(order)

    @pytest.mark.asyncio
    async def test_stop_limit_order_submitted(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=40, status="Submitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(
            symbol="AMZN", side=OrderSide.BUY, order_type=OrderType.STOP_LIMIT,
            quantity=2, stop_price=185.0, limit_price=186.0,
        )
        result = await adapter.submit_order(order)

        _, ib_order = ib_instance.placeOrder.call_args[0]
        assert ib_order.orderType == "STP LMT"
        assert ib_order.auxPrice == 185.0
        assert ib_order.lmtPrice == 186.0
        assert result.broker_order_id == "40"

    @pytest.mark.asyncio
    async def test_stop_limit_missing_stop_price_raises(self, ib):
        adapter, ib_instance, mock_module = ib
        order = Order(
            symbol="AMZN", side=OrderSide.BUY, order_type=OrderType.STOP_LIMIT,
            quantity=2, limit_price=186.0,
        )
        with pytest.raises(ValueError, match="both"):
            await adapter.submit_order(order)

    @pytest.mark.asyncio
    async def test_stop_limit_missing_limit_price_raises(self, ib):
        adapter, ib_instance, mock_module = ib
        order = Order(
            symbol="AMZN", side=OrderSide.BUY, order_type=OrderType.STOP_LIMIT,
            quantity=2, stop_price=185.0,
        )
        with pytest.raises(ValueError, match="both"):
            await adapter.submit_order(order)

    @pytest.mark.asyncio
    async def test_filled_status_mapped_correctly(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=50, status="Filled")
        ib_instance.placeOrder.return_value = trade

        order = Order(symbol="JPM", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
        result = await adapter.submit_order(order)
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_broker_exception_sets_rejected_and_reraises(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.placeOrder.side_effect = RuntimeError("gateway error")

        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
        with pytest.raises(RuntimeError):
            await adapter.submit_order(order)
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_order_id_assigned_when_blank(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=99, status="Submitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1)
        assert order.id == ""
        result = await adapter.submit_order(order)
        assert result.id != ""

    @pytest.mark.asyncio
    async def test_existing_order_id_preserved(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = self._trade(order_id=99, status="Submitted")
        ib_instance.placeOrder.return_value = trade

        order = Order(
            id="my-existing-id", symbol="AAPL",
            side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1,
        )
        result = await adapter.submit_order(order)
        assert result.id == "my-existing-id"


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------

class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancels_found_order_and_returns_true(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = _make_trade(order_id=77, status="Submitted")
        ib_instance.openTrades.return_value = [trade]

        result = await adapter.cancel_order("77")

        ib_instance.cancelOrder.assert_called_once_with(trade.order)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_order_not_found(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.openTrades.return_value = []

        result = await adapter.cancel_order("999")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.openTrades.side_effect = RuntimeError("connection lost")

        result = await adapter.cancel_order("77")
        assert result is False

    @pytest.mark.asyncio
    async def test_does_not_cancel_wrong_order_id(self, ib):
        adapter, ib_instance, mock_module = ib
        trade = _make_trade(order_id=100, status="Submitted")
        ib_instance.openTrades.return_value = [trade]

        result = await adapter.cancel_order("200")
        ib_instance.cancelOrder.assert_not_called()
        assert result is False


# ---------------------------------------------------------------------------
# get_order_status
# ---------------------------------------------------------------------------

class TestGetOrderStatus:
    @pytest.mark.asyncio
    async def test_returns_submitted_for_in_flight_order(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.trades.return_value = [_make_trade(order_id=55, status="Submitted")]

        status = await adapter.get_order_status("55")
        assert status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_returns_filled_for_completed_order(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.trades.return_value = [_make_trade(order_id=56, status="Filled")]

        status = await adapter.get_order_status("56")
        assert status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_returns_cancelled(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.trades.return_value = [_make_trade(order_id=57, status="Cancelled")]

        status = await adapter.get_order_status("57")
        assert status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_raises_when_order_not_found(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.trades.return_value = []

        with pytest.raises(Exception):
            await adapter.get_order_status("9999")

    @pytest.mark.asyncio
    async def test_finds_correct_order_among_multiple(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.trades.return_value = [
            _make_trade(order_id=1, status="Submitted"),
            _make_trade(order_id=2, status="Filled"),
            _make_trade(order_id=3, status="Cancelled"),
        ]

        assert await adapter.get_order_status("1") == OrderStatus.SUBMITTED
        assert await adapter.get_order_status("2") == OrderStatus.FILLED
        assert await adapter.get_order_status("3") == OrderStatus.CANCELLED


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------

class TestGetPositions:
    @pytest.mark.asyncio
    async def test_maps_long_position_correctly(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqPositionsAsync.return_value = [
            _make_ib_position("AAPL", "STK", 10.0, 178.50)
        ]

        positions = await adapter.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "AAPL"
        assert pos.quantity == 10.0
        assert pos.avg_entry_price == 178.50
        assert pos.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_maps_short_position_correctly(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqPositionsAsync.return_value = [
            _make_ib_position("TSLA", "STK", -5.0, 250.0)
        ]

        positions = await adapter.get_positions()

        assert len(positions) == 1
        assert positions[0].quantity == 5.0
        assert positions[0].side == OrderSide.SELL

    @pytest.mark.asyncio
    async def test_filters_out_non_stk_positions(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqPositionsAsync.return_value = [
            _make_ib_position("AAPL", "STK", 10.0, 178.0),
            _make_ib_position("AAPL240119C00185000", "OPT", 2.0, 3.50),
            _make_ib_position("ES", "FUT", 1.0, 4800.0),
        ]

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_filters_out_zero_quantity_positions(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqPositionsAsync.return_value = [
            _make_ib_position("AAPL", "STK", 0.0, 178.0),
            _make_ib_position("MSFT", "STK", 5.0, 420.0),
        ]

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "MSFT"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_positions(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqPositionsAsync.return_value = []

        positions = await adapter.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_multiple_positions_all_mapped(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqPositionsAsync.return_value = [
            _make_ib_position("AAPL", "STK", 10.0, 178.0),
            _make_ib_position("MSFT", "STK", 5.0, 420.0),
            _make_ib_position("JPM", "STK", 20.0, 195.0),
        ]

        positions = await adapter.get_positions()
        assert len(positions) == 3
        symbols = {p.symbol for p in positions}
        assert symbols == {"AAPL", "MSFT", "JPM"}


# ---------------------------------------------------------------------------
# get_portfolio
# ---------------------------------------------------------------------------

class TestGetPortfolio:
    @pytest.mark.asyncio
    async def test_maps_account_values_correctly(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqAccountSummaryAsync.return_value = [
            _make_summary_item("DU123", "NetLiquidation", "25000.0"),
            _make_summary_item("DU123", "TotalCashValue", "15000.0"),
            _make_summary_item("DU123", "RealizedPnL", "500.0"),
        ]

        portfolio = await adapter.get_portfolio()

        assert portfolio.total_equity == 25000.0
        assert portfolio.cash == 15000.0
        assert portfolio.positions_value == 10000.0
        assert portfolio.total_pnl == 500.0

    @pytest.mark.asyncio
    async def test_positions_value_is_equity_minus_cash(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqAccountSummaryAsync.return_value = [
            _make_summary_item("DU123", "NetLiquidation", "30000.0"),
            _make_summary_item("DU123", "TotalCashValue", "20000.0"),
        ]

        portfolio = await adapter.get_portfolio()
        assert portfolio.positions_value == 10000.0

    @pytest.mark.asyncio
    async def test_missing_tags_default_to_zero(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqAccountSummaryAsync.return_value = []

        portfolio = await adapter.get_portfolio()
        assert portfolio.total_equity == 0.0
        assert portfolio.cash == 0.0
        assert portfolio.total_pnl == 0.0

    @pytest.mark.asyncio
    async def test_positions_included_in_snapshot(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqAccountSummaryAsync.return_value = [
            _make_summary_item("DU1", "NetLiquidation", "20000.0"),
            _make_summary_item("DU1", "TotalCashValue", "10000.0"),
        ]
        ib_instance.reqPositionsAsync.return_value = [
            _make_ib_position("AAPL", "STK", 10.0, 178.0),
        ]

        portfolio = await adapter.get_portfolio()
        assert len(portfolio.positions) == 1
        assert portfolio.positions[0].symbol == "AAPL"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ib", ["DU999"], indirect=True)
    async def test_filters_to_configured_account_id(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqAccountSummaryAsync.return_value = [
            _make_summary_item("DU999", "NetLiquidation", "25000.0"),
            _make_summary_item("DU999", "TotalCashValue", "15000.0"),
            _make_summary_item("DU111", "NetLiquidation", "99999.0"),  # wrong account
            _make_summary_item("DU111", "TotalCashValue", "99999.0"),
        ]

        portfolio = await adapter.get_portfolio()
        assert portfolio.total_equity == 25000.0
        assert portfolio.cash == 15000.0

    @pytest.mark.asyncio
    async def test_uses_first_account_when_none_configured(self, ib):
        adapter, ib_instance, mock_module = ib
        # account_id="" (default fixture), so first account wins
        ib_instance.reqAccountSummaryAsync.return_value = [
            _make_summary_item("DU001", "NetLiquidation", "12345.0"),
            _make_summary_item("DU001", "TotalCashValue", "5000.0"),
        ]

        portfolio = await adapter.get_portfolio()
        assert portfolio.total_equity == 12345.0

    @pytest.mark.asyncio
    async def test_sector_exposure_aggregated(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.reqAccountSummaryAsync.return_value = [
            _make_summary_item("DU1", "NetLiquidation", "20000.0"),
            _make_summary_item("DU1", "TotalCashValue", "10000.0"),
        ]
        # Positions with manually set sector values (via the Position model)
        from src.core.models import Position
        ib_instance.reqPositionsAsync.return_value = []
        # patch get_positions to return positions with sectors
        tech_pos = Position(
            symbol="AAPL", quantity=10, avg_entry_price=178.0,
            market_value=1780.0, sector="Technology",
        )
        msft_pos = Position(
            symbol="MSFT", quantity=5, avg_entry_price=420.0,
            market_value=2100.0, sector="Technology",
        )
        fin_pos = Position(
            symbol="JPM", quantity=20, avg_entry_price=195.0,
            market_value=3900.0, sector="Financials",
        )
        adapter.get_positions = AsyncMock(return_value=[tech_pos, msft_pos, fin_pos])

        portfolio = await adapter.get_portfolio()

        assert portfolio.sector_exposure["Technology"] == pytest.approx(3880.0)
        assert portfolio.sector_exposure["Financials"] == pytest.approx(3900.0)


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_returns_true_when_connected(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.isConnected.return_value = True

        assert await adapter.health_check() is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_connected_after_attempt(self, ib):
        adapter, ib_instance, mock_module = ib
        # isConnected is checked twice: once inside _ensure_connected, once at the end.
        # First call (in _ensure_connected) returns False → triggers connect.
        # Second call (health_check return value) also returns False.
        ib_instance.isConnected.side_effect = [False, False]

        result = await adapter.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, ib):
        adapter, ib_instance, mock_module = ib
        ib_instance.isConnected.side_effect = RuntimeError("TWS not running")

        result = await adapter.health_check()
        assert result is False
