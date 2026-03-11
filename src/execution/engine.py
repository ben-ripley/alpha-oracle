from __future__ import annotations

import json
import uuid

import structlog

from src.core.interfaces import BrokerAdapter, RiskManager
from src.core.models import (
    Order,
    OrderStatus,
    PortfolioSnapshot,
    RiskAction,
    Signal,
    SignalDirection,
)
from src.core.redis import get_redis
from src.execution.order_generator import OrderGenerator
from src.execution.tracker import ExecutionTracker

logger = structlog.get_logger(__name__)

PENDING_ORDERS_KEY = "execution:pending_approvals"
ORDER_EVENTS_CHANNEL = "execution:order_events"


class ExecutionEngine:
    """Main orchestrator for order execution.

    Processes signals through risk checks and submits to broker,
    with support for manual approval workflows.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        risk_manager: RiskManager,
        order_generator: OrderGenerator | None = None,
        tracker: ExecutionTracker | None = None,
    ) -> None:
        self._broker = broker
        self._risk = risk_manager
        self._order_gen = order_generator or OrderGenerator()
        self.tracker = tracker or ExecutionTracker(broker=broker)

    async def process_signal(self, signal: Signal) -> Order | None:
        log = logger.bind(symbol=signal.symbol, strategy=signal.strategy_name)

        if signal.direction == SignalDirection.FLAT:
            log.info("signal_skipped_flat")
            return None

        if await self._risk.is_kill_switch_active():
            log.warning("signal_rejected_kill_switch_active")
            return None

        portfolio = await self._broker.get_portfolio()

        try:
            order = self._order_gen.generate_order(signal, portfolio)
        except ValueError as exc:
            log.warning("order_generation_failed", error=str(exc))
            return None

        log = log.bind(order_id=order.id, qty=order.quantity, side=order.side)

        risk_result = await self._risk.check_pre_trade(order, portfolio)
        log.info("risk_check_result", action=risk_result.action, reasons=risk_result.reasons)

        return await self._handle_risk_action(order, portfolio, risk_result, log)

    async def _handle_risk_action(
        self,
        order: Order,
        portfolio: PortfolioSnapshot,
        risk_result,
        log,
        reduce_attempts: int = 0,
    ) -> Order | None:
        if risk_result.action == RiskAction.APPROVE:
            return await self._submit_order(order, log)

        elif risk_result.action == RiskAction.REQUIRE_HUMAN_APPROVAL:
            return await self._queue_for_approval(order, risk_result.reasons, log)

        elif risk_result.action == RiskAction.REJECT:
            log.warning("order_rejected_by_risk", reasons=risk_result.reasons)
            order.status = OrderStatus.REJECTED
            order.metadata["rejection_reasons"] = risk_result.reasons
            await self._publish_order_event(order, "rejected")
            return None

        elif risk_result.action == RiskAction.REDUCE_SIZE:
            if reduce_attempts >= 3:
                log.warning("order_rejected_max_reduce_attempts")
                order.status = OrderStatus.REJECTED
                await self._publish_order_event(order, "rejected")
                return None

            if risk_result.adjusted_quantity is not None and risk_result.adjusted_quantity > 0:
                order.quantity = risk_result.adjusted_quantity
                log.info("order_size_reduced", new_qty=order.quantity)
                new_risk = await self._risk.check_pre_trade(order, portfolio)
                return await self._handle_risk_action(
                    order, portfolio, new_risk, log, reduce_attempts + 1
                )
            else:
                log.warning("order_rejected_no_valid_reduced_size")
                order.status = OrderStatus.REJECTED
                await self._publish_order_event(order, "rejected")
                return None

        log.error("unknown_risk_action", action=risk_result.action)
        return None

    async def _submit_order(self, order: Order, log) -> Order:
        try:
            order = await self._broker.submit_order(order)
            log.info("order_submitted_to_broker", broker_id=order.broker_order_id)
            await self._publish_order_event(order, "submitted")
            return order
        except Exception:
            log.exception("broker_submission_failed")
            order.status = OrderStatus.REJECTED
            await self._publish_order_event(order, "submission_failed")
            raise

    async def _queue_for_approval(
        self, order: Order, reasons: list[str], log
    ) -> Order:
        order.status = OrderStatus.PENDING
        order.metadata["approval_reasons"] = reasons

        redis = await get_redis()
        await redis.hset(
            PENDING_ORDERS_KEY,
            order.id,
            order.model_dump_json(),
        )
        log.info("order_queued_for_approval", reasons=reasons)
        await self._publish_order_event(order, "pending_approval")
        return order

    async def approve_pending_order(self, order_id: str) -> Order:
        log = logger.bind(order_id=order_id)
        redis = await get_redis()

        raw = await redis.hget(PENDING_ORDERS_KEY, order_id)
        if raw is None:
            raise ValueError(f"No pending order found: {order_id}")

        order = Order.model_validate_json(raw)
        await redis.hdel(PENDING_ORDERS_KEY, order_id)

        log.info("pending_order_approved")
        return await self._submit_order(order, log)

    async def reject_pending_order(self, order_id: str, reason: str) -> None:
        log = logger.bind(order_id=order_id)
        redis = await get_redis()

        raw = await redis.hget(PENDING_ORDERS_KEY, order_id)
        if raw is None:
            raise ValueError(f"No pending order found: {order_id}")

        order = Order.model_validate_json(raw)
        await redis.hdel(PENDING_ORDERS_KEY, order_id)

        order.status = OrderStatus.REJECTED
        order.metadata["manual_rejection_reason"] = reason

        log.info("pending_order_rejected", reason=reason)
        await self._publish_order_event(order, "manually_rejected")

    async def get_pending_approvals(self) -> list[Order]:
        redis = await get_redis()
        raw_orders = await redis.hgetall(PENDING_ORDERS_KEY)
        orders: list[Order] = []
        for raw in raw_orders.values():
            orders.append(Order.model_validate_json(raw))
        return orders

    async def cancel_all_orders(self) -> int:
        """Cancel all open orders. Returns count of cancelled orders."""
        log = logger.bind()
        portfolio = await self._broker.get_portfolio()
        # Cancel pending approvals
        redis = await get_redis()
        pending = await redis.hgetall(PENDING_ORDERS_KEY)
        await redis.delete(PENDING_ORDERS_KEY)
        cancelled = len(pending)

        for raw in pending.values():
            order = Order.model_validate_json(raw)
            order.status = OrderStatus.CANCELLED
            await self._publish_order_event(order, "cancelled")

        log.warning("all_orders_cancelled", count=cancelled)
        return cancelled

    async def _publish_order_event(self, order: Order, event_type: str) -> None:
        try:
            redis = await get_redis()
            event = {
                "event_type": event_type,
                "order": json.loads(order.model_dump_json()),
            }
            await redis.publish(ORDER_EVENTS_CHANNEL, json.dumps(event))
        except Exception:
            logger.exception("failed_to_publish_order_event", order_id=order.id)
