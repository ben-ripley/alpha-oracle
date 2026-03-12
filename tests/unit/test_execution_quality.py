"""Tests for ExecutionQualityTracker: slippage, latency, aggregation."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.core.models import (
    ExecutionQualityMetrics,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from src.execution.quality import ExecutionQualityTracker


def _make_order(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 10,
    limit_price: float | None = 100.00,
    filled_price: float | None = 100.05,
    created_at: datetime | None = None,
    filled_at: datetime | None = None,
    metadata: dict | None = None,
) -> Order:
    now = datetime.utcnow()
    return Order(
        id=f"order-{symbol}",
        symbol=symbol,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        limit_price=limit_price,
        filled_price=filled_price,
        created_at=created_at or now,
        filled_at=filled_at or now,
        status=OrderStatus.FILLED,
        strategy_name="TestStrategy",
        metadata=metadata or {},
    )


@pytest.fixture
def tracker():
    return ExecutionQualityTracker()


class TestBuySlippage:
    """Buy slippage: positive means worse fill, negative means improvement."""

    @pytest.mark.asyncio
    async def test_buy_slippage_positive(self, tracker, mock_redis):
        """Filled at 100.05 vs limit 100.00 = +5 bps (adverse)."""
        order = _make_order(
            side=OrderSide.BUY,
            limit_price=100.00,
            filled_price=100.05,
        )

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            metrics = await tracker.record_fill(order)

        assert metrics.slippage_bps == 5.0

    @pytest.mark.asyncio
    async def test_buy_improvement_negative(self, tracker, mock_redis):
        """Filled at 99.95 vs limit 100.00 = -5 bps (improvement)."""
        order = _make_order(
            side=OrderSide.BUY,
            limit_price=100.00,
            filled_price=99.95,
        )

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            metrics = await tracker.record_fill(order)

        assert metrics.slippage_bps == -5.0


class TestSellSlippage:
    """Sell slippage: positive means worse fill."""

    @pytest.mark.asyncio
    async def test_sell_slippage_positive(self, tracker, mock_redis):
        """Filled at 99.95 vs limit 100.00 for sell = +5 bps (adverse)."""
        order = _make_order(
            side=OrderSide.SELL,
            limit_price=100.00,
            filled_price=99.95,
        )

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            metrics = await tracker.record_fill(order)

        assert metrics.slippage_bps == 5.0


class TestLatency:
    """Fill latency tracking."""

    @pytest.mark.asyncio
    async def test_latency_tracking(self, tracker, mock_redis):
        """Signal at t=0, fill at t=2s -> latency_ms=2000."""
        t0 = datetime(2024, 6, 1, 10, 0, 0)
        t1 = t0 + timedelta(seconds=2)
        order = _make_order(created_at=t0, filled_at=t1)

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            metrics = await tracker.record_fill(order)

        assert metrics.fill_latency_ms == 2000.0


class TestArrivalPrice:
    """Missing limit_price falls back to arrival_price from metadata."""

    @pytest.mark.asyncio
    async def test_uses_arrival_price_when_no_limit(self, tracker, mock_redis):
        """When limit_price is None, use metadata arrival_price as expected."""
        order = _make_order(
            limit_price=None,
            filled_price=100.05,
            metadata={"arrival_price": 100.00},
        )

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            metrics = await tracker.record_fill(order)

        assert metrics.expected_price == 100.00
        assert metrics.slippage_bps == 5.0


class TestAggregation:
    """Aggregated metrics across multiple fills."""

    @pytest.mark.asyncio
    async def test_aggregated_metrics(self, tracker, mock_redis):
        """avg, median, p95 across multiple fills."""
        now = datetime.utcnow()
        records = []
        # Create 4 records with slippages: 2, 4, 6, 8 bps
        for i, slip in enumerate([2.0, 4.0, 6.0, 8.0]):
            expected = 100.0
            filled = expected + (slip / 10_000 * expected)
            m = ExecutionQualityMetrics(
                order_id=f"order-{i}",
                symbol="AAPL",
                side=OrderSide.BUY,
                expected_price=expected,
                filled_price=filled,
                slippage_bps=slip,
                arrival_slippage_bps=0.0,
                fill_latency_ms=float(1000 * (i + 1)),
                fill_timestamp=now,
            )
            records.append(m.model_dump_json())

        mock_redis.lrange = AsyncMock(return_value=records)

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            agg = await tracker.get_metrics(days=30)

        assert agg["fill_count"] == 4
        assert agg["avg_slippage_bps"] == 5.0  # (2+4+6+8)/4
        assert agg["median_slippage_bps"] == 5.0  # median of [2,4,6,8]
        assert agg["p95_slippage_bps"] == 8.0  # p95 index = 3
        assert agg["avg_latency_ms"] == 2500.0  # (1000+2000+3000+4000)/4


class TestStoresInRedis:
    """Verify metrics are pushed to Redis."""

    @pytest.mark.asyncio
    async def test_record_fill_pushes_to_redis(self, tracker, mock_redis):
        order = _make_order()

        with patch("src.execution.quality.get_redis", return_value=mock_redis):
            await tracker.record_fill(order)

        mock_redis.rpush.assert_called_once()
        key, payload = mock_redis.rpush.call_args[0]
        assert key == "execution:quality_metrics"
        parsed = ExecutionQualityMetrics.model_validate_json(payload)
        assert parsed.order_id == order.id
