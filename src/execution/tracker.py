from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta

import structlog

from src.core.interfaces import BrokerAdapter
from src.core.models import (
    Order,
    OrderStatus,
    TradeRecord,
)
from src.core.redis import get_redis

logger = structlog.get_logger(__name__)

FILL_EVENTS_CHANNEL = "execution:fill_events"
TRADE_HISTORY_KEY = "execution:trade_history"
OPEN_ORDERS_KEY = "execution:open_orders"
DAY_TRADES_KEY = "execution:day_trades"

_TERMINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
}


class ExecutionTracker:
    """Tracks orders from submission through fill, records trades, and monitors execution quality."""

    def __init__(self, broker: BrokerAdapter, poll_interval: float = 2.0) -> None:
        self._broker = broker
        self._poll_interval = poll_interval
        self._monitoring_tasks: dict[str, asyncio.Task] = {}

    async def monitor_order(self, order: Order) -> None:
        """Begin polling an order's status until it reaches a terminal state."""
        if order.broker_order_id and order.status not in _TERMINAL_STATUSES:
            redis = await get_redis()
            await redis.hset(OPEN_ORDERS_KEY, order.id, order.model_dump_json())

            task = asyncio.create_task(self._poll_order(order))
            self._monitoring_tasks[order.id] = task
            logger.info(
                "order_monitoring_started",
                order_id=order.id,
                broker_order_id=order.broker_order_id,
            )

    async def _poll_order(self, order: Order) -> None:
        log = logger.bind(order_id=order.id, broker_order_id=order.broker_order_id)
        try:
            while True:
                await asyncio.sleep(self._poll_interval)
                try:
                    status = await self._broker.get_order_status(order.broker_order_id)
                except Exception:
                    log.exception("status_poll_failed")
                    continue

                if status != order.status:
                    log.info("order_status_changed", old=order.status, new=status)
                    order.status = status

                    redis = await get_redis()
                    await redis.hset(OPEN_ORDERS_KEY, order.id, order.model_dump_json())

                if status == OrderStatus.FILLED:
                    order.filled_at = datetime.utcnow()
                    await self.on_fill(order)
                    break

                if status in _TERMINAL_STATUSES:
                    log.info("order_reached_terminal_status", status=status)
                    redis = await get_redis()
                    await redis.hdel(OPEN_ORDERS_KEY, order.id)
                    break
        finally:
            self._monitoring_tasks.pop(order.id, None)

    async def on_fill(self, order: Order) -> None:
        """Handle a filled order: record trade, publish event, check PDT."""
        log = logger.bind(order_id=order.id, symbol=order.symbol)
        redis = await get_redis()

        # Remove from open orders
        await redis.hdel(OPEN_ORDERS_KEY, order.id)

        filled_price = order.filled_price or order.limit_price or 0.0
        filled_qty = order.filled_quantity or order.quantity

        trade = TradeRecord(
            id=str(uuid.uuid4()),
            symbol=order.symbol,
            side=order.side,
            quantity=filled_qty,
            entry_price=filled_price,
            entry_time=order.filled_at or datetime.utcnow(),
            strategy_name=order.strategy_name,
        )

        # Check for day trade
        is_day_trade = await self._check_day_trade(order, redis)
        trade.is_day_trade = is_day_trade

        # Store trade record
        await redis.rpush(
            f"{TRADE_HISTORY_KEY}:{order.symbol}",
            trade.model_dump_json(),
        )
        await redis.rpush(TRADE_HISTORY_KEY, trade.model_dump_json())

        # Track day trades for PDT
        if is_day_trade:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            await redis.rpush(f"{DAY_TRADES_KEY}:{today}", trade.model_dump_json())
            log.warning("day_trade_detected", symbol=order.symbol)

        # Publish fill event
        fill_event = {
            "event_type": "fill",
            "order": json.loads(order.model_dump_json()),
            "trade": json.loads(trade.model_dump_json()),
            "is_day_trade": is_day_trade,
        }
        await redis.publish(FILL_EVENTS_CHANNEL, json.dumps(fill_event))

        # Calculate slippage if we have both expected and filled prices
        slippage = self._calculate_slippage(order)
        if slippage is not None:
            log.info("fill_recorded", price=filled_price, qty=filled_qty, slippage_pct=slippage)
        else:
            log.info("fill_recorded", price=filled_price, qty=filled_qty)

    async def _check_day_trade(self, order: Order, redis) -> bool:
        """Check if this fill creates a same-day round trip (day trade)."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        raw_trades = await redis.lrange(f"{TRADE_HISTORY_KEY}:{order.symbol}", 0, -1)

        for raw in raw_trades:
            past_trade = TradeRecord.model_validate_json(raw)
            if (
                past_trade.side != order.side
                and past_trade.entry_time.strftime("%Y-%m-%d") == today
            ):
                return True
        return False

    async def get_open_orders(self) -> list[Order]:
        redis = await get_redis()
        raw_orders = await redis.hgetall(OPEN_ORDERS_KEY)
        return [Order.model_validate_json(raw) for raw in raw_orders.values()]

    async def get_trade_history(
        self,
        symbol: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[TradeRecord]:
        redis = await get_redis()

        if symbol:
            raw_trades = await redis.lrange(f"{TRADE_HISTORY_KEY}:{symbol}", 0, -1)
        else:
            raw_trades = await redis.lrange(TRADE_HISTORY_KEY, 0, -1)

        from datetime import timezone as _tz

        def _aware(dt: datetime) -> datetime:
            return dt if dt.tzinfo else dt.replace(tzinfo=_tz.utc)

        trades: list[TradeRecord] = []
        for raw in raw_trades:
            trade = TradeRecord.model_validate_json(raw)
            entry = _aware(trade.entry_time)
            if start and entry < _aware(start):
                continue
            if end and entry > _aware(end):
                continue
            trades.append(trade)

        if limit:
            trades = trades[:limit]
        return trades

    async def get_execution_metrics(self) -> dict:
        """Calculate execution quality metrics across recent trades."""
        trades = await self.get_trade_history()
        if not trades:
            return {"total_trades": 0, "fill_rate": 0.0, "avg_slippage_pct": 0.0}

        redis = await get_redis()
        open_orders = await redis.hlen(OPEN_ORDERS_KEY)
        total_orders = len(trades) + open_orders
        fill_rate = len(trades) / total_orders if total_orders > 0 else 0.0

        return {
            "total_trades": len(trades),
            "open_orders": open_orders,
            "fill_rate": fill_rate,
        }

    @staticmethod
    def _calculate_slippage(order: Order) -> float | None:
        """Calculate slippage as percentage between expected and filled price."""
        if order.filled_price is None or order.limit_price is None:
            return None
        if order.limit_price == 0:
            return None

        slippage = abs(order.filled_price - order.limit_price) / order.limit_price * 100
        return round(slippage, 4)

    async def stop(self) -> None:
        """Cancel all monitoring tasks."""
        for task in self._monitoring_tasks.values():
            task.cancel()
        if self._monitoring_tasks:
            await asyncio.gather(
                *self._monitoring_tasks.values(), return_exceptions=True
            )
        self._monitoring_tasks.clear()
        logger.info("execution_tracker_stopped")
