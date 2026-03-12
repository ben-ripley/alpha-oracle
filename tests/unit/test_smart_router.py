from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from src.core.config import RouterSettings
from src.core.models import Order, OrderSide, OrderType
from src.execution.router import SmartOrderRouter


def _make_order(
    symbol: str = "AAPL",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 100,
    signal_strength: float = 0.7,
    order_type: OrderType = OrderType.LIMIT,
    limit_price: float | None = 150.0,
    metadata: dict | None = None,
) -> Order:
    return Order(
        id=str(uuid.uuid4()),
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        signal_strength=signal_strength,
        strategy_name="test_strategy",
        created_at=datetime.utcnow(),
        metadata=metadata or {},
    )


def _make_feed(
    bid: float = 149.90,
    ask: float = 150.10,
    volume: float = 1_000_000,
    spread: float | None = None,
) -> AsyncMock:
    feed = AsyncMock()
    feed.get_latest_quote.return_value = {
        "bid": bid,
        "ask": ask,
        "last": (bid + ask) / 2,
        "volume": volume,
    }
    if spread is None:
        spread = ask - bid
    feed.get_spread.return_value = spread
    return feed


@pytest.fixture
def settings() -> RouterSettings:
    return RouterSettings(
        size_threshold_small_pct=0.1,
        size_threshold_large_pct=1.0,
        twap_num_slices=5,
        twap_interval_seconds=60,
        wide_spread_threshold_bps=20.0,
    )


@pytest.mark.asyncio
async def test_small_order_uses_limit(settings: RouterSettings) -> None:
    """order qty=100, ADV=1_000_000 -> size=0.01% -> passive LIMIT at bid."""
    feed = _make_feed(bid=149.90, ask=150.10, volume=1_000_000)
    router = SmartOrderRouter(feed=feed, settings=settings)
    order = _make_order(quantity=100, signal_strength=0.5)

    result = await router.route(order)

    assert len(result) == 1
    assert result[0].order_type == OrderType.LIMIT
    assert result[0].limit_price == 149.90  # at bid for small buy


@pytest.mark.asyncio
async def test_large_order_splits_into_twap(settings: RouterSettings) -> None:
    """order qty=15000, ADV=1_000_000 -> size=1.5% -> 5 TWAP slices."""
    feed = _make_feed(bid=149.90, ask=150.10, volume=1_000_000)
    router = SmartOrderRouter(feed=feed, settings=settings)
    order = _make_order(quantity=15000, signal_strength=0.5)

    result = await router.route(order)

    assert len(result) == 5
    for s in result:
        assert s.quantity == 3000
        assert "twap_slice" in s.metadata
        assert s.metadata["twap_total_slices"] == 5


@pytest.mark.asyncio
async def test_wide_spread_triggers_mid_price_limit(settings: RouterSettings) -> None:
    """spread=30bps > threshold=20bps -> limit near midpoint."""
    # spread of 0.45 on mid ~150 => ~30 bps
    feed = _make_feed(bid=149.775, ask=150.225, volume=1_000_000, spread=0.45)
    router = SmartOrderRouter(feed=feed, settings=settings)
    order = _make_order(quantity=5000, signal_strength=0.5)

    result = await router.route(order)

    assert len(result) == 1
    assert result[0].order_type == OrderType.LIMIT
    mid = (149.775 + 150.225) / 2
    # Limit should be near midpoint (within the spread)
    assert 149.775 < result[0].limit_price < 150.225
    assert abs(result[0].limit_price - mid) < (150.225 - 149.775) / 2


@pytest.mark.asyncio
async def test_high_urgency_forces_market(settings: RouterSettings) -> None:
    """signal_strength=0.95 -> MARKET order."""
    feed = _make_feed()
    router = SmartOrderRouter(feed=feed, settings=settings)
    order = _make_order(signal_strength=0.95)

    result = await router.route(order)

    assert len(result) == 1
    assert result[0].order_type == OrderType.MARKET
    assert result[0].limit_price is None


@pytest.mark.asyncio
async def test_no_feed_passes_through(settings: RouterSettings) -> None:
    """No feed available -> order passes through unchanged."""
    router = SmartOrderRouter(feed=None, settings=settings)
    order = _make_order(order_type=OrderType.LIMIT, limit_price=150.0)

    result = await router.route(order)

    assert len(result) == 1
    assert result[0].order_type == OrderType.LIMIT
    assert result[0].limit_price == 150.0


@pytest.mark.asyncio
async def test_twap_slices_sum_to_original_quantity(settings: RouterSettings) -> None:
    """TWAP slices must sum to the original order quantity."""
    feed = _make_feed(volume=1_000_000)
    router = SmartOrderRouter(feed=feed, settings=settings)
    # 15003 doesn't divide evenly by 5
    order = _make_order(quantity=15003, signal_strength=0.5)

    result = await router.route(order)

    total_qty = sum(s.quantity for s in result)
    assert total_qty == 15003


@pytest.mark.asyncio
async def test_buy_limit_at_bid_offset_sell_at_ask_offset(settings: RouterSettings) -> None:
    """Default routing: buy limit above bid, sell limit below ask."""
    feed = _make_feed(bid=100.00, ask=100.10, volume=1_000_000)
    router = SmartOrderRouter(feed=feed, settings=settings)

    # Medium-sized buy (between small and large thresholds)
    buy_order = _make_order(
        quantity=5000, side=OrderSide.BUY, signal_strength=0.5
    )
    buy_result = await router.route(buy_order)
    assert len(buy_result) == 1
    assert buy_result[0].order_type == OrderType.LIMIT
    # Buy limit should be above bid but below ask
    assert 100.00 < buy_result[0].limit_price <= 100.10

    # Medium-sized sell
    sell_order = _make_order(
        quantity=5000, side=OrderSide.SELL, signal_strength=0.5
    )
    sell_result = await router.route(sell_order)
    assert len(sell_result) == 1
    assert sell_result[0].order_type == OrderType.LIMIT
    # Sell limit should be below ask but above bid
    assert 100.00 <= sell_result[0].limit_price < 100.10
