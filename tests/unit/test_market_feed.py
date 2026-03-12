"""Tests for the market data feed module."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.data.feeds.base import MarketDataFeed
from src.data.feeds.alpaca_feed import AlpacaMarketFeed


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


def _make_feed() -> AlpacaMarketFeed:
    """Create an AlpacaMarketFeed with mocked settings."""
    settings = MagicMock()
    settings.alpaca_api_key = "test-key"
    settings.alpaca_secret_key = "test-secret"
    settings.data.feed.feed_type = "iex"
    settings.data.feed.symbols_per_connection = 200
    settings.data.feed.reconnect_delay_seconds = 1
    settings.data.feed.max_reconnect_attempts = 3
    return AlpacaMarketFeed(settings=settings)


def _make_bar(symbol: str = "AAPL") -> MagicMock:
    bar = MagicMock()
    bar.symbol = symbol
    bar.timestamp = datetime(2026, 3, 11, 16, 0, 0, tzinfo=timezone.utc)
    bar.open = 150.0
    bar.high = 152.0
    bar.low = 149.0
    bar.close = 151.5
    bar.volume = 1000000
    bar.vwap = 150.8
    return bar


def _make_quote(symbol: str = "AAPL") -> MagicMock:
    quote = MagicMock()
    quote.symbol = symbol
    quote.timestamp = datetime(2026, 3, 11, 16, 0, 0, tzinfo=timezone.utc)
    quote.bid_price = 151.40
    quote.bid_size = 100.0
    quote.ask_price = 151.50
    quote.ask_size = 200.0
    return quote


# ---------------------------------------------------------------------------
# 2. AlpacaMarketFeed stores latest bar on callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_bar_stores_latest():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.alpaca_feed.get_redis", return_value=mock_redis):
        await feed._handle_bar(_make_bar("AAPL"))

    assert "AAPL" in feed._latest_bars
    bar_data = feed._latest_bars["AAPL"]
    assert bar_data["symbol"] == "AAPL"
    assert bar_data["close"] == 151.5
    assert bar_data["volume"] == 1000000


# ---------------------------------------------------------------------------
# 3. AlpacaMarketFeed publishes bar to Redis channel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_bar_publishes_to_redis():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.alpaca_feed.get_redis", return_value=mock_redis):
        await feed._handle_bar(_make_bar("MSFT"))

    mock_redis.publish.assert_called_once()
    channel = mock_redis.publish.call_args[0][0]
    assert channel == "market:bars:MSFT"


# ---------------------------------------------------------------------------
# 4. get_latest_quote returns stored quote data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_quote_returns_stored():
    feed = _make_feed()
    mock_redis = AsyncMock()
    with patch("src.data.feeds.alpaca_feed.get_redis", return_value=mock_redis):
        await feed._handle_quote(_make_quote("AAPL"))

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
    with patch("src.data.feeds.alpaca_feed.get_redis", return_value=mock_redis):
        await feed._handle_quote(_make_quote("AAPL"))

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
