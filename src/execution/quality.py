"""Execution quality tracking: slippage, latency, and aggregated metrics."""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

import structlog

from src.core.models import ExecutionQualityMetrics, Order, OrderSide
from src.core.redis import get_redis

logger = structlog.get_logger(__name__)

QUALITY_KEY = "execution:quality_metrics"


class ExecutionQualityTracker:
    """Tracks and aggregates execution quality metrics."""

    async def record_fill(self, order: Order) -> ExecutionQualityMetrics:
        """Calculate and store execution quality for a filled order."""
        expected_price = self._get_expected_price(order)
        filled_price = order.filled_price or expected_price or 0.0

        slippage_bps = 0.0
        if expected_price and expected_price > 0:
            raw = (filled_price - expected_price) / expected_price * 10_000
            slippage_bps = raw if order.side == OrderSide.BUY else -raw

        arrival_price = order.metadata.get("arrival_price")
        arrival_slippage_bps = 0.0
        if arrival_price and arrival_price > 0:
            raw = (filled_price - arrival_price) / arrival_price * 10_000
            arrival_slippage_bps = raw if order.side == OrderSide.BUY else -raw

        fill_latency_ms = 0.0
        if order.filled_at and order.created_at:
            fill_latency_ms = (order.filled_at - order.created_at).total_seconds() * 1000

        signal_timestamp = order.metadata.get("signal_timestamp")
        if isinstance(signal_timestamp, str):
            signal_timestamp = datetime.fromisoformat(signal_timestamp)

        metrics = ExecutionQualityMetrics(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            expected_price=expected_price or 0.0,
            filled_price=filled_price,
            slippage_bps=round(slippage_bps, 2),
            arrival_slippage_bps=round(arrival_slippage_bps, 2),
            fill_latency_ms=round(fill_latency_ms, 2),
            signal_timestamp=signal_timestamp,
            fill_timestamp=order.filled_at,
        )

        redis = await get_redis()
        await redis.rpush(QUALITY_KEY, metrics.model_dump_json())

        logger.info(
            "execution_quality_recorded",
            order_id=order.id,
            symbol=order.symbol,
            slippage_bps=metrics.slippage_bps,
            latency_ms=metrics.fill_latency_ms,
        )

        return metrics

    async def get_metrics(
        self, symbol: str | None = None, days: int = 30
    ) -> dict:
        """Get aggregated execution quality metrics."""
        redis = await get_redis()
        raw_items = await redis.lrange(QUALITY_KEY, 0, -1)

        cutoff = datetime.utcnow() - timedelta(days=days)
        records: list[ExecutionQualityMetrics] = []
        for raw in raw_items:
            m = ExecutionQualityMetrics.model_validate_json(raw)
            if symbol and m.symbol != symbol:
                continue
            if m.fill_timestamp and m.fill_timestamp < cutoff:
                continue
            records.append(m)

        if not records:
            return {
                "fill_count": 0,
                "avg_slippage_bps": 0.0,
                "median_slippage_bps": 0.0,
                "p95_slippage_bps": 0.0,
                "avg_latency_ms": 0.0,
                "total_slippage_cost": 0.0,
            }

        slippages = [r.slippage_bps for r in records]
        latencies = [r.fill_latency_ms for r in records]
        sorted_slippages = sorted(slippages)
        p95_idx = min(int(len(sorted_slippages) * 0.95), len(sorted_slippages) - 1)

        total_slippage_cost = sum(
            (r.filled_price - r.expected_price) * (1 if r.side == OrderSide.BUY else -1)
            for r in records
            if r.expected_price > 0
        )

        return {
            "fill_count": len(records),
            "avg_slippage_bps": round(statistics.mean(slippages), 2),
            "median_slippage_bps": round(statistics.median(slippages), 2),
            "p95_slippage_bps": round(sorted_slippages[p95_idx], 2),
            "avg_latency_ms": round(statistics.mean(latencies), 2),
            "total_slippage_cost": round(total_slippage_cost, 4),
        }

    async def get_recent(self, limit: int = 50) -> list[ExecutionQualityMetrics]:
        """Get recent execution quality records."""
        redis = await get_redis()
        raw_items = await redis.lrange(QUALITY_KEY, -limit, -1)
        return [ExecutionQualityMetrics.model_validate_json(raw) for raw in raw_items]

    @staticmethod
    def _get_expected_price(order: Order) -> float | None:
        """Determine the expected price for an order."""
        if order.limit_price is not None:
            return order.limit_price
        arrival = order.metadata.get("arrival_price")
        if arrival is not None:
            return float(arrival)
        signal = order.metadata.get("signal_price")
        if signal is not None:
            return float(signal)
        return None
