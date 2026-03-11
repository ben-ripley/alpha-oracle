from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import OrderType as AlpacaOrderType
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import (
    GetOrderByIdRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
)

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

_ALPACA_STATUS_MAP: dict[str, OrderStatus] = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "pending_new": OrderStatus.PENDING,
    "accepted_for_bidding": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "done_for_day": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "expired": OrderStatus.EXPIRED,
    "replaced": OrderStatus.SUBMITTED,
    "pending_cancel": OrderStatus.SUBMITTED,
    "pending_replace": OrderStatus.SUBMITTED,
    "stopped": OrderStatus.FILLED,
    "rejected": OrderStatus.REJECTED,
    "suspended": OrderStatus.REJECTED,
    "calculated": OrderStatus.SUBMITTED,
    "held": OrderStatus.SUBMITTED,
}


class AlpacaBrokerAdapter(BrokerAdapter):
    """Alpaca broker adapter supporting both paper and live trading."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._paper = settings.broker.paper_trading
        self._client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=self._paper,
        )
        logger.info(
            "alpaca_adapter_initialized",
            paper=self._paper,
        )

    async def submit_order(self, order: Order) -> Order:
        log = logger.bind(symbol=order.symbol, side=order.side, qty=order.quantity)
        try:
            alpaca_side = (
                AlpacaOrderSide.BUY
                if order.side == OrderSide.BUY
                else AlpacaOrderSide.SELL
            )

            if order.order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                )
            elif order.order_type == OrderType.LIMIT:
                if order.limit_price is None:
                    raise ValueError("Limit order requires limit_price")
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                    limit_price=order.limit_price,
                )
            elif order.order_type == OrderType.STOP:
                if order.stop_price is None:
                    raise ValueError("Stop order requires stop_price")
                request = StopOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                    stop_price=order.stop_price,
                )
            elif order.order_type == OrderType.STOP_LIMIT:
                if order.stop_price is None or order.limit_price is None:
                    raise ValueError("Stop-limit order requires both prices")
                request = StopLimitOrderRequest(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                    stop_price=order.stop_price,
                    limit_price=order.limit_price,
                )
            else:
                raise ValueError(f"Unsupported order type: {order.order_type}")

            alpaca_order = self._client.submit_order(request)

            order.broker_order_id = str(alpaca_order.id)
            order.status = _ALPACA_STATUS_MAP.get(
                str(alpaca_order.status).lower(), OrderStatus.SUBMITTED
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
            self._client.cancel_order_by_id(broker_order_id)
            logger.info("order_cancelled", broker_order_id=broker_order_id)
            return True
        except Exception:
            logger.exception("order_cancel_failed", broker_order_id=broker_order_id)
            return False

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        try:
            alpaca_order = self._client.get_order_by_id(broker_order_id)
            status = _ALPACA_STATUS_MAP.get(
                str(alpaca_order.status).lower(), OrderStatus.SUBMITTED
            )
            return status
        except Exception:
            logger.exception(
                "order_status_fetch_failed", broker_order_id=broker_order_id
            )
            raise

    async def get_positions(self) -> list[Position]:
        try:
            alpaca_positions = self._client.get_all_positions()
            positions: list[Position] = []
            for p in alpaca_positions:
                qty = float(p.qty)
                side = OrderSide.BUY if qty > 0 else OrderSide.SELL
                positions.append(
                    Position(
                        symbol=p.symbol,
                        quantity=abs(qty),
                        avg_entry_price=float(p.avg_entry_price),
                        current_price=float(p.current_price),
                        market_value=float(p.market_value),
                        unrealized_pnl=float(p.unrealized_pl),
                        unrealized_pnl_pct=float(p.unrealized_plpc) * 100,
                        side=side,
                    )
                )
            return positions
        except Exception:
            logger.exception("positions_fetch_failed")
            raise

    async def get_portfolio(self) -> PortfolioSnapshot:
        try:
            account = self._client.get_account()
            positions = await self.get_positions()

            total_equity = float(account.equity)
            cash = float(account.cash)
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
                daily_pnl=float(account.equity) - float(account.last_equity),
                daily_pnl_pct=(
                    (float(account.equity) - float(account.last_equity))
                    / float(account.last_equity)
                    * 100
                    if float(account.last_equity) > 0
                    else 0.0
                ),
                positions=positions,
                sector_exposure=sector_exposure,
            )
        except Exception:
            logger.exception("portfolio_fetch_failed")
            raise

    async def health_check(self) -> bool:
        try:
            account = self._client.get_account()
            is_active = str(account.status).lower() == "active"
            logger.debug("health_check_passed", account_status=str(account.status))
            return is_active
        except Exception:
            logger.exception("health_check_failed")
            return False
