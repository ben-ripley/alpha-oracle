"""Unit tests for IBKRDataAdapter and IBKRMarketFeed."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import OHLCV
from src.data.normalizer import normalize_ibkr_bars
from src.data.adapters.ibkr_data_adapter import (
    IBKRDataAdapter,
    _duration_str,
    _to_utc,
)
from src.data.feeds.ibkr_feed import IBKRMarketFeed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(provider: str = "ibkr") -> MagicMock:
    s = MagicMock()
    s.broker.provider = provider
    s.broker.ibkr.host = "127.0.0.1"
    s.broker.ibkr.port = 4002
    s.broker.ibkr.client_id = 1
    s.broker.ibkr.account_id = ""
    s.data.feed.symbols_per_connection = 200
    s.data.feed.reconnect_delay_seconds = 5
    s.data.feed.max_reconnect_attempts = 10
    return s


def _ib_instance() -> MagicMock:
    ib = MagicMock()
    ib.isConnected.return_value = True
    ib.connectAsync = AsyncMock()
    ib.qualifyContractsAsync = AsyncMock()
    ib.reqHistoricalDataAsync = AsyncMock(return_value=[])
    ib.reqMktData = MagicMock()
    ib.cancelMktData = MagicMock()
    ib.disconnect = MagicMock()
    return ib


def _bar(date, open_=150.0, high=155.0, low=148.0, close=152.0, volume=1_000_000):
    b = MagicMock()
    b.date = date
    b.open = open_
    b.high = high
    b.low = low
    b.close = close
    b.volume = volume
    return b


@pytest.fixture()
def data_ib(request):
    """Yields (IBKRDataAdapter, ib_instance, mock_module)."""
    ib_instance = _ib_instance()
    mock_module = MagicMock()
    mock_module.IB.return_value = ib_instance
    with patch.dict("sys.modules", {"ib_async": mock_module}):
        adapter = IBKRDataAdapter(_settings())
        yield adapter, ib_instance, mock_module


@pytest.fixture()
def feed_ib():
    """Yields (IBKRMarketFeed, ib_instance, mock_module)."""
    ib_instance = _ib_instance()
    mock_module = MagicMock()
    mock_module.IB.return_value = ib_instance
    with patch.dict("sys.modules", {"ib_async": mock_module}):
        feed = IBKRMarketFeed(_settings())
        yield feed, ib_instance, mock_module


# ---------------------------------------------------------------------------
# normalize_ibkr_bars
# ---------------------------------------------------------------------------

class TestNormalizeIbkrBars:
    def test_datetime_bar_mapped_correctly(self):
        bar = _bar(datetime(2024, 1, 15, 0, 0, tzinfo=timezone.utc))
        result = normalize_ibkr_bars([bar], "AAPL")
        assert len(result) == 1
        assert result[0].symbol == "AAPL"
        assert result[0].source == "ibkr"
        assert result[0].close == 152.0
        assert result[0].volume == 1_000_000

    def test_yyyymmdd_string_date_parsed(self):
        bar = _bar("20240115")
        result = normalize_ibkr_bars([bar], "MSFT")
        assert result[0].timestamp == datetime(2024, 1, 15, tzinfo=timezone.utc)

    def test_yyyymmdd_hhmmss_string_date_parsed(self):
        bar = _bar("20240115 09:30:00")
        result = normalize_ibkr_bars([bar], "TSLA")
        assert result[0].timestamp == datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone.utc)

    def test_naive_datetime_gets_utc(self):
        bar = _bar(datetime(2024, 3, 1, 10, 0))  # no tzinfo
        result = normalize_ibkr_bars([bar], "GOOG")
        assert result[0].timestamp.tzinfo == timezone.utc

    def test_date_object_converted(self):
        from datetime import date
        bar = _bar(date(2024, 6, 1))
        result = normalize_ibkr_bars([bar], "JPM")
        assert result[0].timestamp == datetime(2024, 6, 1, tzinfo=timezone.utc)

    def test_empty_list_returns_empty(self):
        assert normalize_ibkr_bars([], "AAPL") == []

    def test_multiple_bars_all_mapped(self):
        bars = [
            _bar(datetime(2024, 1, i, tzinfo=timezone.utc), close=float(150 + i))
            for i in range(1, 6)
        ]
        result = normalize_ibkr_bars(bars, "NVDA")
        assert len(result) == 5
        assert result[-1].close == 155.0

    def test_ohlcv_fields_correct(self):
        bar = _bar(
            datetime(2024, 1, 1, tzinfo=timezone.utc),
            open_=100.0, high=110.0, low=95.0, close=105.0, volume=500_000,
        )
        r = normalize_ibkr_bars([bar], "X")[0]
        assert r.open == 100.0
        assert r.high == 110.0
        assert r.low == 95.0
        assert r.close == 105.0
        assert r.volume == 500_000


# ---------------------------------------------------------------------------
# _duration_str
# ---------------------------------------------------------------------------

class TestDurationStr:
    def test_short_daily_range(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 30, tzinfo=timezone.utc)
        result = _duration_str(start, end, "1Day")
        assert result.endswith(" D")
        assert int(result.split()[0]) >= 29

    def test_long_daily_range_uses_years(self):
        start = datetime(2022, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = _duration_str(start, end, "1Day")
        assert result.endswith(" Y")

    def test_intraday_short_range_uses_seconds(self):
        start = datetime(2024, 1, 15, 9, 30, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc)
        result = _duration_str(start, end, "1Min")
        assert result.endswith(" S") or result.endswith(" D")

    def test_intraday_multi_day_uses_days(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 10, tzinfo=timezone.utc)
        result = _duration_str(start, end, "5Min")
        assert result.endswith(" D") or result.endswith(" S")


# ---------------------------------------------------------------------------
# IBKRDataAdapter — get_historical_bars
# ---------------------------------------------------------------------------

class TestIBKRDataAdapterHistoricalBars:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_bars(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.reqHistoricalDataAsync.return_value = []

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)
        result = await adapter.get_historical_bars("AAPL", start, end)
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_bars_to_requested_range(self, data_ib):
        adapter, ib_instance, _ = data_ib
        start = datetime(2024, 1, 10, tzinfo=timezone.utc)
        end = datetime(2024, 1, 20, tzinfo=timezone.utc)

        # IBKR may return extra bars outside the range
        bars_returned = [
            _bar(datetime(2024, 1, 5, tzinfo=timezone.utc)),   # before range
            _bar(datetime(2024, 1, 15, tzinfo=timezone.utc)),  # in range
            _bar(datetime(2024, 1, 25, tzinfo=timezone.utc)),  # after range
        ]
        ib_instance.reqHistoricalDataAsync.return_value = bars_returned

        result = await adapter.get_historical_bars("AAPL", start, end)
        assert len(result) == 1
        assert result[0].timestamp == datetime(2024, 1, 15, tzinfo=timezone.utc)

    @pytest.mark.asyncio
    async def test_calls_req_with_correct_bar_size(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.reqHistoricalDataAsync.return_value = []

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)
        await adapter.get_historical_bars("TSLA", start, end, timeframe="1Hour")

        call_kwargs = ib_instance.reqHistoricalDataAsync.call_args.kwargs
        assert call_kwargs["barSizeSetting"] == "1 hour"

    @pytest.mark.asyncio
    async def test_uses_trades_as_what_to_show(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.reqHistoricalDataAsync.return_value = []

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)
        await adapter.get_historical_bars("MSFT", start, end)

        call_kwargs = ib_instance.reqHistoricalDataAsync.call_args.kwargs
        assert call_kwargs["whatToShow"] == "TRADES"

    @pytest.mark.asyncio
    async def test_connects_when_not_connected(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.isConnected.return_value = False
        ib_instance.reqHistoricalDataAsync.return_value = []

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)
        await adapter.get_historical_bars("AAPL", start, end)

        ib_instance.connectAsync.assert_awaited_once()


# ---------------------------------------------------------------------------
# IBKRDataAdapter — get_latest_bar
# ---------------------------------------------------------------------------

class TestIBKRDataAdapterLatestBar:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_bars(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.reqHistoricalDataAsync.return_value = []
        result = await adapter.get_latest_bar("AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_last_bar(self, data_ib):
        adapter, ib_instance, _ = data_ib
        bars = [
            _bar(datetime(2024, 1, 14, tzinfo=timezone.utc), close=150.0),
            _bar(datetime(2024, 1, 15, tzinfo=timezone.utc), close=155.0),
        ]
        ib_instance.reqHistoricalDataAsync.return_value = bars
        result = await adapter.get_latest_bar("AAPL")
        assert result is not None
        assert result.close == 155.0

    @pytest.mark.asyncio
    async def test_requests_3_day_duration(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.reqHistoricalDataAsync.return_value = []
        await adapter.get_latest_bar("GOOG")
        call_kwargs = ib_instance.reqHistoricalDataAsync.call_args.kwargs
        assert call_kwargs["durationStr"] == "3 D"

    @pytest.mark.asyncio
    async def test_result_is_ohlcv(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.reqHistoricalDataAsync.return_value = [
            _bar(datetime(2024, 1, 15, tzinfo=timezone.utc))
        ]
        result = await adapter.get_latest_bar("NVDA")
        assert isinstance(result, OHLCV)
        assert result.source == "ibkr"


# ---------------------------------------------------------------------------
# IBKRDataAdapter — get_fundamentals / health_check
# ---------------------------------------------------------------------------

class TestIBKRDataAdapterMisc:
    @pytest.mark.asyncio
    async def test_get_fundamentals_returns_none(self, data_ib):
        adapter, _, _ = data_ib
        result = await adapter.get_fundamentals("AAPL")
        assert result is None

    @pytest.mark.asyncio
    async def test_health_check_returns_true_when_connected(self, data_ib):
        adapter, _, _ = data_ib
        result = await adapter.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_exception(self, data_ib):
        adapter, ib_instance, _ = data_ib
        ib_instance.qualifyContractsAsync.side_effect = RuntimeError("no gateway")
        result = await adapter.health_check()
        assert result is False

    def test_client_id_offset_from_broker(self, data_ib):
        adapter, _, _ = data_ib
        # IBKRBrokerAdapter uses client_id=1; data adapter must use client_id+1=2
        assert adapter._client_id == 2


# ---------------------------------------------------------------------------
# IBKRMarketFeed — start / stop
# ---------------------------------------------------------------------------

class TestIBKRMarketFeedLifecycle:
    @pytest.mark.asyncio
    async def test_start_connects(self, feed_ib):
        feed, ib_instance, _ = feed_ib
        await feed.start()
        ib_instance.connectAsync.assert_awaited_once_with(
            host="127.0.0.1", port=4002, clientId=3
        )
        assert feed.is_connected()

    @pytest.mark.asyncio
    async def test_stop_disconnects(self, feed_ib):
        feed, ib_instance, _ = feed_ib
        await feed.start()
        await feed.stop()
        ib_instance.disconnect.assert_called_once()
        assert not feed.is_connected()

    def test_client_id_offset_from_data_adapter(self, feed_ib):
        feed, _, _ = feed_ib
        # broker=1, data=2, feed=3
        assert feed._client_id == 3


# ---------------------------------------------------------------------------
# IBKRMarketFeed — subscribe / unsubscribe
# ---------------------------------------------------------------------------

class TestIBKRMarketFeedSubscription:
    @pytest.mark.asyncio
    async def test_subscribe_creates_ticker_per_symbol(self, feed_ib):
        feed, ib_instance, mock_module = feed_ib
        mock_ticker = MagicMock()
        mock_ticker.updateEvent = MagicMock()
        ib_instance.reqMktData.return_value = mock_ticker

        await feed.subscribe(["AAPL", "MSFT"])

        assert ib_instance.reqMktData.call_count == 2
        assert "AAPL" in feed._tickers
        assert "MSFT" in feed._tickers

    @pytest.mark.asyncio
    async def test_subscribe_skips_already_subscribed(self, feed_ib):
        feed, ib_instance, _ = feed_ib
        mock_ticker = MagicMock()
        mock_ticker.updateEvent = MagicMock()
        ib_instance.reqMktData.return_value = mock_ticker

        await feed.subscribe(["AAPL"])
        await feed.subscribe(["AAPL"])  # second call should be a no-op

        assert ib_instance.reqMktData.call_count == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_cancels_market_data(self, feed_ib):
        feed, ib_instance, _ = feed_ib
        mock_ticker = MagicMock()
        mock_ticker.updateEvent = MagicMock()
        ib_instance.reqMktData.return_value = mock_ticker

        await feed.subscribe(["AAPL"])
        await feed.unsubscribe(["AAPL"])

        ib_instance.cancelMktData.assert_called_once()
        assert "AAPL" not in feed._tickers

    @pytest.mark.asyncio
    async def test_unsubscribe_clears_cached_data(self, feed_ib):
        feed, ib_instance, _ = feed_ib
        mock_ticker = MagicMock()
        mock_ticker.updateEvent = MagicMock()
        ib_instance.reqMktData.return_value = mock_ticker

        feed._latest_quotes["AAPL"] = {"bid_price": 150.0}
        feed._latest_bars["AAPL"] = {"close": 150.0}
        feed._tickers["AAPL"] = mock_ticker

        await feed.unsubscribe(["AAPL"])

        assert "AAPL" not in feed._latest_quotes
        assert "AAPL" not in feed._latest_bars


# ---------------------------------------------------------------------------
# IBKRMarketFeed — ticker update handling
# ---------------------------------------------------------------------------

class TestIBKRMarketFeedTickerHandling:
    def _make_ticker(self, bid=149.5, ask=150.5, last=150.0,
                     bid_size=100, ask_size=200, volume=500_000,
                     open_=148.0, high=152.0, low=147.0, vwap=None):
        t = MagicMock()
        t.bid = bid
        t.ask = ask
        t.last = last
        t.bidSize = bid_size
        t.askSize = ask_size
        t.volume = volume
        t.open = open_
        t.high = high
        t.low = low
        t.vwap = vwap
        return t

    @pytest.mark.asyncio
    async def test_valid_quote_published_to_redis(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("AAPL", self._make_ticker())

        assert mock_redis.publish.call_count >= 1
        channels = [call.args[0] for call in mock_redis.publish.call_args_list]
        assert "market:quotes:AAPL" in channels

    @pytest.mark.asyncio
    async def test_valid_bar_published_to_redis(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("MSFT", self._make_ticker())

        channels = [call.args[0] for call in mock_redis.publish.call_args_list]
        assert "market:bars:MSFT" in channels

    @pytest.mark.asyncio
    async def test_quote_stored_in_latest_quotes(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("AAPL", self._make_ticker(bid=149.0, ask=151.0))

        quote = feed._latest_quotes.get("AAPL")
        assert quote is not None
        assert quote["bid_price"] == 149.0
        assert quote["ask_price"] == 151.0

    @pytest.mark.asyncio
    async def test_bar_stored_in_latest_bars(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("NVDA", self._make_ticker(last=875.0))

        bar = feed._latest_bars.get("NVDA")
        assert bar is not None
        assert bar["close"] == 875.0

    @pytest.mark.asyncio
    async def test_zero_bid_ask_skips_quote_publish(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("GOOG", self._make_ticker(bid=0, ask=0, last=100.0))

        channels = [call.args[0] for call in mock_redis.publish.call_args_list]
        assert "market:quotes:GOOG" not in channels

    @pytest.mark.asyncio
    async def test_zero_last_price_skips_bar_publish(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("JPM", self._make_ticker(last=0))

        channels = [call.args[0] for call in mock_redis.publish.call_args_list]
        assert "market:bars:JPM" not in channels

    @pytest.mark.asyncio
    async def test_redis_failure_does_not_raise(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()
        mock_redis.publish.side_effect = ConnectionError("redis down")

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            # Should not propagate the exception
            await feed._handle_ticker("AAPL", self._make_ticker())

    @pytest.mark.asyncio
    async def test_published_quote_is_valid_json(self, feed_ib):
        feed, _, _ = feed_ib
        mock_redis = AsyncMock()

        with patch("src.data.feeds.ibkr_feed.get_redis", return_value=mock_redis):
            await feed._handle_ticker("AAPL", self._make_ticker())

        for call in mock_redis.publish.call_args_list:
            channel, payload = call.args
            parsed = json.loads(payload)
            assert "symbol" in parsed
            assert "timestamp" in parsed


# ---------------------------------------------------------------------------
# IBKRMarketFeed — get_latest_quote / get_spread
# ---------------------------------------------------------------------------

class TestIBKRMarketFeedQueries:
    @pytest.mark.asyncio
    async def test_get_latest_quote_returns_stored(self, feed_ib):
        feed, _, _ = feed_ib
        feed._latest_quotes["AAPL"] = {"bid_price": 149.0, "ask_price": 151.0}
        result = await feed.get_latest_quote("AAPL")
        assert result["bid_price"] == 149.0

    @pytest.mark.asyncio
    async def test_get_latest_quote_returns_none_when_missing(self, feed_ib):
        feed, _, _ = feed_ib
        result = await feed.get_latest_quote("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_spread_calculates_correctly(self, feed_ib):
        feed, _, _ = feed_ib
        feed._latest_quotes["AAPL"] = {"bid_price": 149.0, "ask_price": 151.0}
        spread = await feed.get_spread("AAPL")
        assert spread == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_get_spread_returns_none_when_no_quote(self, feed_ib):
        feed, _, _ = feed_ib
        result = await feed.get_spread("UNKNOWN")
        assert result is None
