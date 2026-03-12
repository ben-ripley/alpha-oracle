from __future__ import annotations

import copy
import uuid

import structlog

from src.core.config import RouterSettings, get_settings
from src.core.models import Order, OrderSide, OrderType

logger = structlog.get_logger(__name__)


class SmartOrderRouter:
    """Selects order type and sizing based on market conditions."""

    def __init__(
        self,
        feed=None,
        settings: RouterSettings | None = None,
    ) -> None:
        self._feed = feed
        self._settings = settings or get_settings().router

    async def route(self, order: Order) -> list[Order]:
        """Route an order based on size, spread, and urgency.

        Returns list of orders (usually 1, but may be multiple for TWAP slicing).
        """
        if self._feed is None:
            return [order]

        quote = await self._feed.get_latest_quote(order.symbol)
        spread = await self._feed.get_spread(order.symbol)

        if quote is None or spread is None:
            logger.warning("feed_data_unavailable", symbol=order.symbol)
            return [order]

        bid = quote.get("bid", 0.0)
        ask = quote.get("ask", 0.0)

        if bid <= 0 or ask <= 0:
            return [order]

        mid = (bid + ask) / 2.0
        spread_bps = (spread / mid * 10000) if mid > 0 else 0.0

        avg_volume = quote.get("volume", 0.0) or order.metadata.get("avg_daily_volume", 0.0)

        # High urgency: MARKET order
        if order.signal_strength > 0.9:
            order.order_type = OrderType.MARKET
            order.limit_price = None
            logger.info("route_high_urgency", symbol=order.symbol)
            return [order]

        # Wide spread: aggressive limit at mid + small offset
        if spread_bps > self._settings.wide_spread_threshold_bps:
            order = self._adjust_limit_price(order, bid, ask, spread_bps)
            logger.info("route_wide_spread", symbol=order.symbol, spread_bps=spread_bps)
            return [order]

        # Size-based routing
        if avg_volume > 0:
            size_pct = self._calculate_size_pct(order, avg_volume)

            # Large order: TWAP slicing
            if size_pct > self._settings.size_threshold_large_pct:
                slices = self._create_twap_slices(order, self._settings.twap_num_slices)
                logger.info(
                    "route_twap",
                    symbol=order.symbol,
                    size_pct=size_pct,
                    num_slices=len(slices),
                )
                return slices

            # Small order: limit at best bid/ask
            if size_pct < self._settings.size_threshold_small_pct:
                order.order_type = OrderType.LIMIT
                if order.side == OrderSide.BUY:
                    order.limit_price = round(bid, 2)
                else:
                    order.limit_price = round(ask, 2)
                logger.info("route_small_passive", symbol=order.symbol, size_pct=size_pct)
                return [order]

        # Default: limit at bid+offset for buys, ask-offset for sells
        order = self._adjust_limit_price(order, bid, ask, spread_bps)
        return [order]

    def _calculate_size_pct(self, order: Order, avg_volume: float) -> float:
        """Order size as percentage of average daily volume."""
        if avg_volume <= 0:
            return 0.0
        return (order.quantity / avg_volume) * 100.0

    def _create_twap_slices(self, order: Order, num_slices: int) -> list[Order]:
        """Split a large order into equal TWAP slices."""
        if num_slices <= 1:
            return [order]

        base_qty = int(order.quantity // num_slices)
        remainder = int(order.quantity - base_qty * num_slices)

        slices: list[Order] = []
        for i in range(num_slices):
            qty = base_qty + (1 if i < remainder else 0)
            if qty <= 0:
                continue
            slice_order = order.model_copy(deep=True)
            slice_order.id = str(uuid.uuid4())
            slice_order.quantity = float(qty)
            slice_order.metadata = dict(order.metadata)
            slice_order.metadata["twap_slice"] = i + 1
            slice_order.metadata["twap_total_slices"] = num_slices
            slice_order.metadata["twap_interval_seconds"] = self._settings.twap_interval_seconds
            slice_order.metadata["parent_order_id"] = order.id
            slices.append(slice_order)

        return slices

    def _adjust_limit_price(
        self, order: Order, bid: float, ask: float, spread_bps: float
    ) -> Order:
        """Set limit price based on spread conditions."""
        mid = (bid + ask) / 2.0

        if spread_bps > self._settings.wide_spread_threshold_bps:
            # Wide spread: use midpoint with a small offset toward our side
            offset = (ask - bid) * 0.1
            order.order_type = OrderType.LIMIT
            if order.side == OrderSide.BUY:
                order.limit_price = round(mid + offset, 2)
            else:
                order.limit_price = round(mid - offset, 2)
        else:
            # Normal spread: bid+offset for buys, ask-offset for sells
            offset = (ask - bid) * 0.25
            order.order_type = OrderType.LIMIT
            if order.side == OrderSide.BUY:
                order.limit_price = round(bid + offset, 2)
            else:
                order.limit_price = round(ask - offset, 2)

        return order
