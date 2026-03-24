"""In-memory simulated broker for end-to-end testing without IB Gateway.

Fills orders at the latest stored OHLCV close ± 0.05% slippage.
All state is in-memory and resets on process restart.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog

from src.core.interfaces import BrokerAdapter
from src.core.models import (
    Order,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
    Position,
)

logger = structlog.get_logger(__name__)

_BUY_SLIPPAGE = 1.0005
_SELL_SLIPPAGE = 0.9995
_PRICE_LOOKBACK_DAYS = 3


class SimulatedBroker(BrokerAdapter):
    """BrokerAdapter backed entirely by in-memory state.

    Fill price comes from the most recent OHLCV bar stored in TimescaleDB
    (3-day lookback window).  If no stored bar is found, the order's
    ``limit_price`` is used as a fallback.  If neither is available the
    order is rejected.

    Activate via ``SA_BROKER__PROVIDER=simulated`` in ``.env``.
    """

    def __init__(self, initial_cash: float = 20_000.0) -> None:
        self._cash: float = initial_cash
        self._initial_cash: float = initial_cash
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, Order] = {}
        logger.info("simulated_broker_initialized", initial_cash=initial_cash)

    # ------------------------------------------------------------------
    # BrokerAdapter interface
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> Order:
        if not order.id:
            order.id = str(uuid.uuid4())

        fill_price = await self._resolve_fill_price(order)
        if fill_price is None:
            order.status = OrderStatus.REJECTED
            order.metadata["rejection_reason"] = (
                "No price data available and no limit_price set"
            )
            logger.warning(
                "simulated_broker.order_rejected",
                symbol=order.symbol,
                reason="no_price",
            )
            return order

        # Apply slippage
        if order.side == OrderSide.BUY:
            fill_price = fill_price * _BUY_SLIPPAGE
        else:
            fill_price = fill_price * _SELL_SLIPPAGE

        # Validate sell quantity
        if order.side == OrderSide.SELL:
            held = self._positions.get(order.symbol)
            held_qty = held.quantity if held else 0.0
            if order.quantity > held_qty:
                order.status = OrderStatus.REJECTED
                order.metadata["rejection_reason"] = (
                    f"insufficient position: have {held_qty}, need {order.quantity}"
                )
                logger.warning(
                    "simulated_broker.order_rejected",
                    symbol=order.symbol,
                    reason="insufficient_position",
                    held=held_qty,
                    requested=order.quantity,
                )
                return order

        # Execute the fill
        self._apply_fill(order, fill_price)

        order.status = OrderStatus.FILLED
        order.filled_price = fill_price
        order.filled_quantity = order.quantity
        order.filled_at = datetime.now(UTC)
        order.broker_order_id = f"sim-{order.id}"

        self._orders[order.id] = order
        logger.info(
            "simulated_broker.order_filled",
            symbol=order.symbol,
            side=order.side,
            qty=order.quantity,
            fill_price=fill_price,
        )
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        for order in self._orders.values():
            if order.broker_order_id == broker_order_id:
                if order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.CANCELLED
                    return True
                return False
        return False

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        for order in self._orders.values():
            if order.broker_order_id == broker_order_id:
                return order.status
        return OrderStatus.REJECTED

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_portfolio(self) -> PortfolioSnapshot:
        positions = await self._positions_with_current_prices()
        positions_value = sum(p.market_value for p in positions)
        total_equity = self._cash + positions_value
        total_pnl = total_equity - self._initial_cash
        total_pnl_pct = (total_pnl / self._initial_cash * 100) if self._initial_cash else 0.0

        sector_exposure: dict[str, float] = {}
        for p in positions:
            if p.sector:
                sector_exposure[p.sector] = (
                    sector_exposure.get(p.sector, 0.0) + p.market_value
                )

        return PortfolioSnapshot(
            total_equity=total_equity,
            cash=self._cash,
            positions_value=positions_value,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            positions=positions,
            sector_exposure=sector_exposure,
        )

    async def health_check(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _resolve_fill_price(self, order: Order) -> float | None:
        """Return fill price from latest stored bar, falling back to limit_price."""
        try:
            from src.data.storage import TimeSeriesStorage

            now = datetime.now(UTC)
            start = now - timedelta(days=_PRICE_LOOKBACK_DAYS)
            storage = TimeSeriesStorage()
            bars = await storage.get_ohlcv(order.symbol, start, now)
            if bars:
                return bars[-1].close
        except Exception:
            logger.warning(
                "simulated_broker.price_lookup_failed",
                symbol=order.symbol,
                exc_info=True,
            )

        if order.limit_price is not None:
            return order.limit_price

        return None

    def _apply_fill(self, order: Order, fill_price: float) -> None:
        """Update in-memory positions and cash after a fill."""
        if order.side == OrderSide.BUY:
            existing = self._positions.get(order.symbol)
            if existing is None:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    avg_entry_price=fill_price,
                    current_price=fill_price,
                    market_value=order.quantity * fill_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    side=OrderSide.BUY,
                    strategy_name=order.strategy_name,
                    entry_date=datetime.now(UTC),
                )
            else:
                new_qty = existing.quantity + order.quantity
                new_avg = (
                    existing.quantity * existing.avg_entry_price
                    + order.quantity * fill_price
                ) / new_qty
                existing.quantity = new_qty
                existing.avg_entry_price = new_avg
                existing.current_price = fill_price
                existing.market_value = new_qty * fill_price
                existing.unrealized_pnl = (fill_price - new_avg) * new_qty
                existing.unrealized_pnl_pct = (
                    (fill_price - new_avg) / new_avg * 100 if new_avg else 0.0
                )

            self._cash -= order.quantity * fill_price

        else:  # SELL
            existing = self._positions[order.symbol]
            new_qty = existing.quantity - order.quantity

            if new_qty <= 0:
                del self._positions[order.symbol]
            else:
                existing.quantity = new_qty
                existing.current_price = fill_price
                existing.market_value = new_qty * fill_price
                existing.unrealized_pnl = (
                    fill_price - existing.avg_entry_price
                ) * new_qty
                existing.unrealized_pnl_pct = (
                    (fill_price - existing.avg_entry_price)
                    / existing.avg_entry_price
                    * 100
                    if existing.avg_entry_price
                    else 0.0
                )

            self._cash += order.quantity * fill_price

    async def _positions_with_current_prices(self) -> list[Position]:
        """Return positions updated with the latest stored close prices."""
        try:
            from src.data.storage import TimeSeriesStorage

            now = datetime.now(UTC)
            start = now - timedelta(days=_PRICE_LOOKBACK_DAYS)
            storage = TimeSeriesStorage()

            updated: list[Position] = []
            for pos in self._positions.values():
                bars = await storage.get_ohlcv(pos.symbol, start, now)
                if bars:
                    price = bars[-1].close
                    pos.current_price = price
                    pos.market_value = pos.quantity * price
                    pos.unrealized_pnl = (price - pos.avg_entry_price) * pos.quantity
                    pos.unrealized_pnl_pct = (
                        (price - pos.avg_entry_price) / pos.avg_entry_price * 100
                        if pos.avg_entry_price
                        else 0.0
                    )
                updated.append(pos)
            return updated
        except Exception:
            logger.warning("simulated_broker.portfolio_price_refresh_failed", exc_info=True)
            return list(self._positions.values())
