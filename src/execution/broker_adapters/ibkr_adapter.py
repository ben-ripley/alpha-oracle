from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog

_MAX_RECONNECT_ATTEMPTS = 3

from src.core.config import Settings
from src.core.interfaces import BrokerAdapter
from src.core.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PortfolioSnapshot,
)

logger = structlog.get_logger(__name__)

# Maps IBKR order status strings to internal OrderStatus values.
# IBKR statuses: ApiPending, ApiCancelled, PreSubmitted, PendingSubmit,
#                PendingCancel, Cancelled, Submitted, Filled, Inactive
_IBKR_STATUS_MAP: dict[str, OrderStatus] = {
    "apipending": OrderStatus.PENDING,
    "pendingsubmit": OrderStatus.PENDING,
    "apicancelled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "presubmitted": OrderStatus.SUBMITTED,
    "pendingcancel": OrderStatus.SUBMITTED,
    "submitted": OrderStatus.SUBMITTED,
    "filled": OrderStatus.FILLED,
    "inactive": OrderStatus.REJECTED,
}

# Account summary tags we care about
_ACCOUNT_TAGS = ("NetLiquidation", "TotalCashValue", "RealizedPnL", "UnrealizedPnL")


class IBKRBrokerAdapter(BrokerAdapter):
    """Interactive Brokers broker adapter using ib_async.

    Requires IB Gateway or Trader Workstation (TWS) running locally.

    Default ports:
        IB Gateway paper:  4002   (recommended — lighter weight)
        IB Gateway live:   4001
        TWS paper:         7497
        TWS live:          7496

    Configure in .env:
        SA_BROKER__IBKR__PORT=4002
        SA_BROKER__IBKR__ACCOUNT_ID=DU123456   # optional; blank = first account
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        ibkr_cfg = settings.broker.ibkr
        self._host = ibkr_cfg.host
        self._port = ibkr_cfg.port
        self._client_id = ibkr_cfg.client_id
        self._account_id = ibkr_cfg.account_id
        self._paper = settings.broker.paper_trading
        # Lazily imported so the package is optional at import time.
        from ib_async import IB  # noqa: PLC0415
        self._ib: IB = IB()
        logger.info(
            "ibkr_adapter_initialized",
            host=self._host,
            port=self._port,
            client_id=self._client_id,
            paper=self._paper,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> None:
        if self._ib.isConnected():
            return

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RECONNECT_ATTEMPTS + 1):
            try:
                await self._ib.connectAsync(
                    host=self._host,
                    port=self._port,
                    clientId=self._client_id,
                )
                logger.info(
                    "ibkr_connected",
                    host=self._host,
                    port=self._port,
                    attempt=attempt,
                )
                return
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RECONNECT_ATTEMPTS:
                    wait = 2 ** attempt  # 2s, 4s, 8s
                    logger.warning(
                        "ibkr_reconnect_attempt",
                        attempt=attempt,
                        wait=wait,
                        error=str(exc),
                    )
                    await asyncio.sleep(wait)

        raise ConnectionError(
            f"IBKR connect failed after {_MAX_RECONNECT_ATTEMPTS} attempts"
        ) from last_exc

    async def disconnect(self) -> None:
        """Disconnect from IB Gateway / TWS. Called during application shutdown."""
        try:
            if self._ib.isConnected():
                self._ib.disconnect()
                logger.info("ibkr_disconnected")
        except Exception:
            logger.warning("ibkr_disconnect_failed", exc_info=True)

    def _make_contract(self, symbol: str):
        from ib_async import Stock  # noqa: PLC0415
        return Stock(symbol, "SMART", "USD")

    def _make_ibkr_order(self, order: Order):
        from ib_async import LimitOrder, MarketOrder, Order as IbOrder, StopOrder  # noqa: PLC0415

        action = "BUY" if order.side == OrderSide.BUY else "SELL"
        qty = order.quantity

        if order.order_type == OrderType.MARKET:
            return MarketOrder(action, qty)

        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("Limit order requires limit_price")
            return LimitOrder(action, qty, order.limit_price)

        if order.order_type == OrderType.STOP:
            if order.stop_price is None:
                raise ValueError("Stop order requires stop_price")
            return StopOrder(action, qty, order.stop_price)

        if order.order_type == OrderType.STOP_LIMIT:
            if order.stop_price is None or order.limit_price is None:
                raise ValueError("Stop-limit order requires both stop_price and limit_price")
            ib_order = IbOrder()
            ib_order.action = action
            ib_order.totalQuantity = qty
            ib_order.orderType = "STP LMT"
            ib_order.lmtPrice = order.limit_price
            ib_order.auxPrice = order.stop_price
            return ib_order

        raise ValueError(f"Unsupported order type: {order.order_type}")

    def _resolve_account(self, summary_items) -> str:
        """Return the configured account ID, or the first account found."""
        if self._account_id:
            return self._account_id
        for item in summary_items:
            if item.account and item.account != "All":
                return item.account
        return ""

    # ------------------------------------------------------------------
    # BrokerAdapter interface
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> Order:
        log = logger.bind(symbol=order.symbol, side=order.side, qty=order.quantity)
        try:
            await self._ensure_connected()
            contract = self._make_contract(order.symbol)
            await self._ib.qualifyContractsAsync(contract)
            ib_order = self._make_ibkr_order(order)
            trade = self._ib.placeOrder(contract, ib_order)
            # Brief yield so the TWS/Gateway acknowledgement can arrive.
            await asyncio.sleep(0.1)
            order.broker_order_id = str(trade.order.orderId)
            order.status = _IBKR_STATUS_MAP.get(
                trade.orderStatus.status.lower(), OrderStatus.SUBMITTED
            )
            if not order.id:
                order.id = str(uuid.uuid4())
            log.info(
                "order_submitted",
                broker_order_id=order.broker_order_id,
                status=order.status,
            )
            return order
        except Exception:
            log.exception("order_submission_failed")
            order.status = OrderStatus.REJECTED
            raise

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._ensure_connected()
            target_id = int(broker_order_id)
            for trade in self._ib.openTrades():
                if trade.order.orderId == target_id:
                    self._ib.cancelOrder(trade.order)
                    logger.info("order_cancelled", broker_order_id=broker_order_id)
                    return True
            logger.warning("order_not_found_for_cancel", broker_order_id=broker_order_id)
            return False
        except Exception:
            logger.exception("order_cancel_failed", broker_order_id=broker_order_id)
            return False

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        try:
            await self._ensure_connected()
            target_id = int(broker_order_id)
            for trade in self._ib.trades():
                if trade.order.orderId == target_id:
                    return _IBKR_STATUS_MAP.get(
                        trade.orderStatus.status.lower(), OrderStatus.SUBMITTED
                    )
            raise ValueError(f"Order {broker_order_id} not found in IBKR trade list")
        except Exception:
            logger.exception("order_status_fetch_failed", broker_order_id=broker_order_id)
            raise

    async def get_positions(self) -> list[Position]:
        try:
            await self._ensure_connected()
            ib_positions = await self._ib.reqPositionsAsync()
            positions: list[Position] = []
            for p in ib_positions:
                # Only US equities; skip options, futures, etc.
                if p.contract.secType != "STK":
                    continue
                qty = float(p.position)
                if qty == 0.0:
                    continue
                positions.append(
                    Position(
                        symbol=p.contract.symbol,
                        quantity=abs(qty),
                        avg_entry_price=float(p.avgCost),
                        side=OrderSide.BUY if qty > 0 else OrderSide.SELL,
                    )
                )
            return positions
        except Exception:
            logger.exception("positions_fetch_failed")
            raise

    async def get_portfolio(self) -> PortfolioSnapshot:
        try:
            await self._ensure_connected()
            summary = await self._ib.reqAccountSummaryAsync()
            account = self._resolve_account(summary)

            values: dict[str, float] = {}
            for item in summary:
                if account and item.account != account:
                    continue
                if item.tag in _ACCOUNT_TAGS:
                    try:
                        values[item.tag] = float(item.value)
                    except (ValueError, TypeError):
                        pass

            total_equity = values.get("NetLiquidation", 0.0)
            cash = values.get("TotalCashValue", 0.0)
            positions = await self.get_positions()
            positions_value = total_equity - cash

            sector_exposure: dict[str, float] = {}
            for pos in positions:
                if pos.sector:
                    sector_exposure[pos.sector] = (
                        sector_exposure.get(pos.sector, 0.0) + pos.market_value
                    )

            return PortfolioSnapshot(
                total_equity=total_equity,
                cash=cash,
                positions_value=positions_value,
                total_pnl=values.get("RealizedPnL", 0.0),
                positions=positions,
                sector_exposure=sector_exposure,
            )
        except Exception:
            logger.exception("portfolio_fetch_failed")
            raise

    async def health_check(self) -> bool:
        try:
            await self._ensure_connected()
            return self._ib.isConnected()
        except Exception:
            logger.exception("health_check_failed")
            return False
