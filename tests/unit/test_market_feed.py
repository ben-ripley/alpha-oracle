"""Tests for the market data feed module."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.data.feeds.base import MarketDataFeed

# ---------------------------------------------------------------------------
# 1. ABC contract enforcement
# ---------------------------------------------------------------------------


def test_abc_cannot_instantiate():
    """MarketDataFeed ABC cannot be instantiated without implementing all methods."""
    with pytest.raises(TypeError):
        MarketDataFeed()


def test_abc_incomplete_subclass():
    """Subclass missing methods raises TypeError."""

    class Incomplete(MarketDataFeed):
        async def start(self):
            ...

    with pytest.raises(TypeError):
        Incomplete()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feed():
    """Create an IBKRMarketFeed with fully mocked ib_async."""
    settings = MagicMock()
    settings.broker.ibkr.host = "127.0.0.1"
    settings.broker.ibkr.port = 4002
    settings.broker.ibkr.client_id = 1
    settings.data.feed.symbols_per_connection = 200
    settings.data.feed.reconnect_delay_seconds = 1
    settings.data.feed.max_reconnect_attempts = 3

    ib_instance = MagicMock()
    ib_instance.isConnected.return_value = False
    mock_ib_module = MagicMock()
    mock_ib_module.IB.return_value = ib_instance

    with patch.dict("sys.modules", {"ib_async": mock_ib_module}):
        from src.data.feeds.ibkr_feed import IBKRMarketFeed
        feed = IBKRMarketFeed(settings=settings)

    return feed


def _make_ticker(
    symbol: str = "AAPL",
    bid: float = 151.40,
    ask: float = 151.50,
    last: float = 151.5,
) -> MagicMock:
    ticker = MagicMock()
    ticker.bid = bid
    ticker.ask = ask
    ticker.last = last
    ticker.open = 150.0
    ticker.high = 152.0
    ticker.low = 149.0
    ticker.volume = 1000000
    ticker.vwap = 150.8
    ticker.bidSize = 100.0
    ticker.askSize = 200.0
    return ticker


# ---------------------------------------------------------------------------
# 2. IBKRMarketFeed stores latest bar on ticker callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ticker_stores_latest_bar():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
        await feed._handle_ticker("AAPL", _make_ticker("AAPL"))

    assert "AAPL" in feed._latest_bars
    bar_data = feed._latest_bars["AAPL"]
    assert bar_data["symbol"] == "AAPL"
    assert bar_data["close"] == 151.5
    assert bar_data["volume"] == 1000000


# ---------------------------------------------------------------------------
# 3. IBKRMarketFeed publishes bar to Redis channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_ticker_publishes_bar_to_redis():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
        await feed._handle_ticker("MSFT", _make_ticker("MSFT"))

    # Should publish to both quote and bar channels
    published_channels = [call[0][0] for call in mock_redis.publish.call_args_list]
    assert "market:bars:MSFT" in published_channels


# ---------------------------------------------------------------------------
# 4. get_latest_quote returns stored quote data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_quote_returns_stored():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
        await feed._handle_ticker("AAPL", _make_ticker("AAPL"))

    result = await feed.get_latest_quote("AAPL")
    assert result is not None
    assert result["symbol"] == "AAPL"
    assert result["bid_price"] == 151.40
    assert result["ask_price"] == 151.50


# ---------------------------------------------------------------------------
# 5. get_spread calculates bid-ask spread correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_spread_calculates_correctly():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
        await feed._handle_ticker("AAPL", _make_ticker("AAPL"))

    spread = await feed.get_spread("AAPL")
    assert spread is not None
    assert abs(spread - 0.10) < 1e-6


# ---------------------------------------------------------------------------
# 6. Graceful handling when not connected (returns None)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_quote_returns_none_when_no_data():
    feed = _make_feed()
    result = await feed.get_latest_quote("UNKNOWN")
    assert result is None


@pytest.mark.asyncio
async def test_get_spread_returns_none_when_no_data():
    feed = _make_feed()
    result = await feed.get_spread("UNKNOWN")
    assert result is None


def test_is_connected_default_false():
    feed = _make_feed()
    assert feed.is_connected() is False
