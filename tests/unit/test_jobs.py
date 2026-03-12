"""Unit tests for scheduling job helpers and job implementations."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.scheduling.jobs import (
    biweekly_altdata_job,
    daily_bars_job,
    is_market_hours_request_safe,
    weekly_fundamentals_job,
)

_ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(symbol: str = "AAPL") -> MagicMock:
    bar = MagicMock()
    bar.symbol = symbol
    return bar


def _make_fundamental(symbol: str = "AAPL") -> MagicMock:
    fd = MagicMock()
    fd.symbol = symbol
    return fd


def _make_short_interest(symbol: str = "AAPL") -> MagicMock:
    si = MagicMock()
    si.symbol = symbol
    return si


def _make_insider_tx(symbol: str = "AAPL") -> MagicMock:
    tx = MagicMock()
    tx.symbol = symbol
    return tx


def _mock_redis(*, is_member: bool = False, last_run: str | None = None) -> AsyncMock:
    """Return an AsyncMock that looks like a redis.asyncio.Redis client."""
    redis = AsyncMock()
    redis.sismember = AsyncMock(return_value=is_member)
    redis.sadd = AsyncMock()
    redis.expire = AsyncMock()
    redis.get = AsyncMock(return_value=last_run)
    redis.set = AsyncMock()
    return redis


# ---------------------------------------------------------------------------
# is_market_hours_request_safe — daily / weekly / monthly timeframes
# ---------------------------------------------------------------------------

class TestDailyAndLongerTimeframesAlwaysSafe:
    def test_daily_bars_always_safe(self):
        assert is_market_hours_request_safe("1Day") is True

    def test_weekly_bars_always_safe(self):
        assert is_market_hours_request_safe("1Week") is True

    def test_monthly_bars_always_safe(self):
        assert is_market_hours_request_safe("1Month") is True

    def test_unknown_timeframe_treated_as_safe(self):
        # Any non-intraday timeframe should default to safe.
        assert is_market_hours_request_safe("4Hour") is True
        assert is_market_hours_request_safe("2Day") is True


# ---------------------------------------------------------------------------
# is_market_hours_request_safe — intraday on weekends
# ---------------------------------------------------------------------------

class TestIntradayUnsafeOnWeekends:
    # 2024-01-06 = Saturday, 2024-01-07 = Sunday

    def test_1min_unsafe_on_saturday(self):
        saturday_noon = datetime(2024, 1, 6, 12, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=saturday_noon):
            assert is_market_hours_request_safe("1Min") is False

    def test_5min_unsafe_on_saturday(self):
        saturday_noon = datetime(2024, 1, 6, 12, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=saturday_noon):
            assert is_market_hours_request_safe("5Min") is False

    def test_15min_unsafe_on_saturday(self):
        saturday_noon = datetime(2024, 1, 6, 12, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=saturday_noon):
            assert is_market_hours_request_safe("15Min") is False

    def test_1hour_unsafe_on_saturday(self):
        saturday_noon = datetime(2024, 1, 6, 12, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=saturday_noon):
            assert is_market_hours_request_safe("1Hour") is False

    def test_all_intraday_unsafe_on_sunday(self):
        sunday_2pm = datetime(2024, 1, 7, 14, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=sunday_2pm):
            for tf in ("1Min", "5Min", "15Min", "1Hour"):
                assert is_market_hours_request_safe(tf) is False, f"{tf} should be unsafe on Sunday"

    def test_daily_safe_on_weekend(self):
        saturday_noon = datetime(2024, 1, 6, 12, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=saturday_noon):
            assert is_market_hours_request_safe("1Day") is True


# ---------------------------------------------------------------------------
# is_market_hours_request_safe — intraday on weekdays
# ---------------------------------------------------------------------------

class TestIntradayWeekdayWindows:
    # 2024-01-09 = Tuesday

    def test_safe_at_market_open(self):
        open_time = datetime(2024, 1, 9, 9, 30, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=open_time):
            assert is_market_hours_request_safe("1Min") is True

    def test_safe_at_midday(self):
        midday = datetime(2024, 1, 9, 13, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=midday):
            assert is_market_hours_request_safe("5Min") is True

    def test_safe_at_market_close(self):
        close_time = datetime(2024, 1, 9, 17, 30, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=close_time):
            assert is_market_hours_request_safe("1Min") is True

    def test_unsafe_before_market_open(self):
        pre_market = datetime(2024, 1, 9, 7, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=pre_market):
            assert is_market_hours_request_safe("1Min") is False

    def test_unsafe_one_minute_before_open(self):
        just_before = datetime(2024, 1, 9, 9, 29, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=just_before):
            assert is_market_hours_request_safe("1Min") is False

    def test_unsafe_after_market_close(self):
        evening = datetime(2024, 1, 9, 20, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=evening):
            assert is_market_hours_request_safe("1Min") is False

    def test_safe_all_intraday_timeframes_during_hours(self):
        midday = datetime(2024, 1, 9, 14, 0, tzinfo=_ET)
        with patch("src.scheduling.jobs._now_et", return_value=midday):
            for tf in ("1Min", "5Min", "15Min", "1Hour"):
                assert is_market_hours_request_safe(tf) is True, f"{tf} should be safe at midday"


# ---------------------------------------------------------------------------
# Helpers for patching job dependencies
# ---------------------------------------------------------------------------

def _patch_daily_bars(
    symbols: list[str],
    bars_per_symbol: list | None = None,
    redis: AsyncMock | None = None,
    av_side_effects: list | None = None,
):
    """Return a tuple of context managers for daily_bars_job dependencies."""
    mock_universe = AsyncMock()
    mock_universe.get_symbols.return_value = symbols

    mock_av = AsyncMock()
    if av_side_effects is not None:
        mock_av.get_historical_bars.side_effect = av_side_effects
    else:
        mock_av.get_historical_bars.return_value = (
            bars_per_symbol if bars_per_symbol is not None else [_make_ohlcv()]
        )

    mock_storage = AsyncMock()
    mock_storage.store_ohlcv.return_value = 1

    mock_redis = redis or _mock_redis()

    return mock_universe, mock_av, mock_storage, mock_redis


def _patch_fundamentals(
    symbols: list[str],
    fundamental: MagicMock | None = None,
    redis: AsyncMock | None = None,
    av_side_effects: list | None = None,
):
    mock_universe = AsyncMock()
    mock_universe.get_symbols.return_value = symbols

    mock_av = AsyncMock()
    if av_side_effects is not None:
        mock_av.get_fundamentals.side_effect = av_side_effects
    else:
        mock_av.get_fundamentals.return_value = fundamental or _make_fundamental()

    mock_storage = AsyncMock()
    mock_redis = redis or _mock_redis()

    return mock_universe, mock_av, mock_storage, mock_redis


# ---------------------------------------------------------------------------
# daily_bars_job
# ---------------------------------------------------------------------------

class TestDailyBarsJob:
    @pytest.mark.asyncio
    async def test_fetches_and_stores_bars_for_each_symbol(self):
        mu, mav, ms, mr = _patch_daily_bars(["AAPL", "MSFT"])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()

        assert mav.get_historical_bars.call_count == 2
        assert ms.store_ohlcv.call_count == 2

    @pytest.mark.asyncio
    async def test_symbols_marked_done_in_redis(self):
        mu, mav, ms, mr = _patch_daily_bars(["AAPL"])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()

        mr.sadd.assert_awaited()
        mr.expire.assert_awaited()

    @pytest.mark.asyncio
    async def test_already_done_symbol_is_skipped(self):
        mr = _mock_redis(is_member=True)
        mu, mav, ms, _ = _patch_daily_bars(["AAPL", "MSFT"], redis=mr)

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()

        mav.get_historical_bars.assert_not_called()
        ms.store_ohlcv.assert_not_called()

    @pytest.mark.asyncio
    async def test_continues_after_symbol_error(self):
        mu, mav, ms, mr = _patch_daily_bars(
            ["AAPL", "MSFT", "GOOG"],
            av_side_effects=[
                RuntimeError("API down"),
                [_make_ohlcv("MSFT")],
                [_make_ohlcv("GOOG")],
            ],
        )

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()  # must not raise

        # Only 2 of 3 symbols succeeded
        assert ms.store_ohlcv.call_count == 2

    @pytest.mark.asyncio
    async def test_no_bars_returned_does_not_call_store(self):
        mu, mav, ms, mr = _patch_daily_bars(["AAPL"], bars_per_symbol=[])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()

        ms.store_ohlcv.assert_not_called()
        # Symbol is still marked done (fetch succeeded, just no new bars)
        mr.sadd.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_empty_universe_completes_without_error(self):
        mu, mav, ms, mr = _patch_daily_bars([])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()

        mav.get_historical_bars.assert_not_called()

    @pytest.mark.asyncio
    async def test_uses_7_day_lookback_window(self):
        mu, mav, ms, mr = _patch_daily_bars(["AAPL"])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await daily_bars_job()

        start, end = mav.get_historical_bars.call_args.args[1:3]
        delta = end - start
        assert 6 <= delta.days <= 8  # 7-day window ±1 for seconds


# ---------------------------------------------------------------------------
# weekly_fundamentals_job
# ---------------------------------------------------------------------------

class TestWeeklyFundamentalsJob:
    @pytest.mark.asyncio
    async def test_fetches_and_stores_fundamentals_for_each_symbol(self):
        mu, mav, ms, mr = _patch_fundamentals(["AAPL", "MSFT"])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await weekly_fundamentals_job()

        assert mav.get_fundamentals.call_count == 2
        assert ms.store_fundamentals.call_count == 2

    @pytest.mark.asyncio
    async def test_already_done_symbol_is_skipped(self):
        mr = _mock_redis(is_member=True)
        mu, mav, ms, _ = _patch_fundamentals(["AAPL", "MSFT"], redis=mr)

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await weekly_fundamentals_job()

        mav.get_fundamentals.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_fundamentals_not_stored(self):
        mu, mav, ms, mr = _patch_fundamentals(["AAPL"])
        mav.get_fundamentals.return_value = None

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await weekly_fundamentals_job()

        ms.store_fundamentals.assert_not_called()
        mr.sadd.assert_awaited_once()  # still marked done

    @pytest.mark.asyncio
    async def test_continues_after_symbol_error(self):
        mu, mav, ms, mr = _patch_fundamentals(
            ["AAPL", "MSFT"],
            av_side_effects=[RuntimeError("timeout"), _make_fundamental("MSFT")],
        )

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await weekly_fundamentals_job()  # must not raise

        assert ms.store_fundamentals.call_count == 1

    @pytest.mark.asyncio
    async def test_symbols_marked_done_in_redis(self):
        mu, mav, ms, mr = _patch_fundamentals(["AAPL"])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.alpha_vantage_adapter.AlphaVantageAdapter", return_value=mav), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await weekly_fundamentals_job()

        mr.sadd.assert_awaited_once()
        mr.expire.assert_awaited_once()


# ---------------------------------------------------------------------------
# biweekly_altdata_job
# ---------------------------------------------------------------------------

class TestBiweeklyAltdataJob:
    def _setup(
        self,
        symbols: list[str] = None,
        short_data: list | None = None,
        insider_data: list | None = None,
        last_run: str | None = None,
        edgar_side_effects: list | None = None,
        finra_side_effects: Exception | None = None,
    ):
        symbols = symbols or ["AAPL", "MSFT"]

        mock_universe = AsyncMock()
        mock_universe.get_symbols.return_value = symbols

        mock_finra = AsyncMock()
        if finra_side_effects is not None:
            mock_finra.get_short_interest.side_effect = finra_side_effects
        else:
            mock_finra.get_short_interest.return_value = (
                short_data if short_data is not None else [_make_short_interest()]
            )

        mock_edgar = AsyncMock()
        if edgar_side_effects is not None:
            mock_edgar.get_insider_transactions.side_effect = edgar_side_effects
        else:
            mock_edgar.get_insider_transactions.return_value = (
                insider_data if insider_data is not None else [_make_insider_tx()]
            )

        mock_storage = AsyncMock()
        mock_redis = _mock_redis(last_run=last_run)

        return mock_universe, mock_finra, mock_edgar, mock_storage, mock_redis

    @pytest.mark.asyncio
    async def test_happy_path_stores_short_interest_and_insider_tx(self):
        mu, mf, me, ms, mr = self._setup()

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()

        ms.store_short_interest.assert_awaited_once()
        assert ms.store_insider_transactions.await_count == 2  # once per symbol

    @pytest.mark.asyncio
    async def test_last_run_key_updated_after_success(self):
        mu, mf, me, ms, mr = self._setup()

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()

        # jobs:altdata:last_run must be set to an ISO-8601 timestamp
        set_call = mr.set.await_args
        assert set_call is not None
        key, value = set_call.args
        assert key == "jobs:altdata:last_run"
        # Value must be a parseable ISO timestamp
        parsed = datetime.fromisoformat(value)
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_uses_last_run_as_start_for_insider_fetch(self):
        last_run_iso = "2024-01-01T00:00:00+00:00"
        mu, mf, me, ms, mr = self._setup(last_run=last_run_iso)

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()

        # start_dt passed to edgar should be the last_run timestamp
        first_call_args = me.get_insider_transactions.await_args_list[0].args
        start_dt = first_call_args[1]
        assert start_dt == datetime.fromisoformat(last_run_iso)

    @pytest.mark.asyncio
    async def test_falls_back_to_14_days_when_no_last_run(self):
        mu, mf, me, ms, mr = self._setup(last_run=None)

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()

        first_call_args = me.get_insider_transactions.await_args_list[0].args
        start_dt = first_call_args[1]
        now_approx = datetime.now(timezone.utc)
        # start_dt should be ~14 days ago (within a minute of test execution)
        delta = now_approx - start_dt
        assert 13 <= delta.days <= 15

    @pytest.mark.asyncio
    async def test_continues_after_individual_edgar_error(self):
        mu, mf, me, ms, mr = self._setup(
            symbols=["AAPL", "MSFT", "GOOG"],
            edgar_side_effects=[
                RuntimeError("EDGAR timeout"),
                [_make_insider_tx("MSFT")],
                [_make_insider_tx("GOOG")],
            ],
        )

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()  # must not raise

        # Only 2 of 3 edgar calls succeeded; last_run still updated
        assert ms.store_insider_transactions.await_count == 2
        mr.set.assert_awaited()  # last_run still written

    @pytest.mark.asyncio
    async def test_short_interest_error_does_not_abort_insider_fetch(self):
        mu, mf, me, ms, mr = self._setup(
            finra_side_effects=RuntimeError("FINRA down"),
        )

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()

        ms.store_short_interest.assert_not_called()
        # Insider fetches still ran for both symbols
        assert me.get_insider_transactions.await_count == 2

    @pytest.mark.asyncio
    async def test_empty_short_interest_not_stored(self):
        mu, mf, me, ms, mr = self._setup(short_data=[])

        with patch("src.data.universe.SymbolUniverse", return_value=mu), \
             patch("src.data.adapters.finra_adapter.FinraAdapter", return_value=mf), \
             patch("src.data.adapters.edgar_adapter.EdgarAdapter", return_value=me), \
             patch("src.data.storage.TimeSeriesStorage", return_value=ms), \
             patch("src.core.redis.get_redis", new=AsyncMock(return_value=mr)):
            await biweekly_altdata_job()

        ms.store_short_interest.assert_not_called()
