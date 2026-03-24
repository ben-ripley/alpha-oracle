"""Tests for the FINRA short interest adapter."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import ShortInterestData
from src.data.adapters.finra_adapter import FinraAdapter


def _make_settings():
    """Create a minimal mock Settings for FinraAdapter."""
    settings = MagicMock()
    settings.data.finra.base_url = "https://api.finra.org"
    settings.data.finra.rate_limit_per_minute = 10
    settings.data.finra.cache_ttl_seconds = 86400
    return settings


def _make_api_row(
    symbol: str,
    settlement_date: str,
    short_interest: int,
    avg_volume: int,
    days_to_cover: float = 0.0,
) -> dict:
    return {
        "symbolCode": symbol,
        "settlementDate": settlement_date,
        "currentShortPositionQuantity": short_interest,
        "averageDailyVolumeQuantity": avg_volume,
        "daysToCoverQuantity": days_to_cover,
        "revisionFlag": "N",
    }


class TestParseResponse:
    """Test parsing of mocked FINRA API responses."""

    def test_parse_single_row(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [_make_api_row("AAPL", "2026-03-01", 5000000, 2500000)]

        results = adapter._parse_rows(rows, latest_only=True)

        assert len(results) == 1
        r = results[0]
        assert r.symbol == "AAPL"
        assert r.settlement_date == datetime(2026, 3, 1, tzinfo=UTC)
        assert r.short_interest == 5000000
        assert r.avg_daily_volume == 2500000
        assert r.days_to_cover == 2.0
        assert r.change_pct is None  # no previous period

    def test_parse_multiple_symbols(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [
            _make_api_row("AAPL", "2026-03-01", 5000000, 2500000),
            _make_api_row("TSLA", "2026-03-01", 8000000, 4000000),
        ]

        results = adapter._parse_rows(rows, latest_only=True)

        assert len(results) == 2
        symbols = {r.symbol for r in results}
        assert symbols == {"AAPL", "TSLA"}

    def test_parse_all_fields_populated(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [
            _make_api_row("GME", "2026-03-01", 10000000, 5000000),
            _make_api_row("GME", "2026-02-15", 8000000, 4000000),
        ]

        results = adapter._parse_rows(rows, latest_only=False)

        assert len(results) == 2
        latest = next(r for r in results if r.settlement_date.day == 1)
        assert latest.short_interest == 10000000
        assert latest.avg_daily_volume == 5000000
        assert latest.days_to_cover == 2.0
        assert isinstance(latest.change_pct, float)


class TestDaysToCover:
    """Test days-to-cover calculation."""

    def test_normal_calculation(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [_make_api_row("AAPL", "2026-03-01", 1000000, 500000)]

        results = adapter._parse_rows(rows, latest_only=True)

        assert results[0].days_to_cover == 2.0

    def test_zero_volume_returns_zero(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [_make_api_row("AAPL", "2026-03-01", 1000000, 0)]

        results = adapter._parse_rows(rows, latest_only=True)

        assert results[0].days_to_cover == 0


class TestChangePct:
    """Test change_pct calculation between periods."""

    def test_increase(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [
            _make_api_row("AAPL", "2026-03-01", 1200000, 500000),
            _make_api_row("AAPL", "2026-02-15", 1000000, 500000),
        ]

        results = adapter._parse_rows(rows, latest_only=False)

        latest = next(r for r in results if r.settlement_date.day == 1)
        assert latest.change_pct == 20.0

    def test_decrease(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [
            _make_api_row("AAPL", "2026-03-01", 800000, 500000),
            _make_api_row("AAPL", "2026-02-15", 1000000, 500000),
        ]

        results = adapter._parse_rows(rows, latest_only=False)

        latest = next(r for r in results if r.settlement_date.day == 1)
        assert latest.change_pct == -20.0

    def test_no_previous_period(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [_make_api_row("AAPL", "2026-03-01", 1000000, 500000)]

        results = adapter._parse_rows(rows, latest_only=True)

        assert results[0].change_pct is None

    def test_previous_period_zero_short_interest(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [
            _make_api_row("AAPL", "2026-03-01", 1000000, 500000),
            _make_api_row("AAPL", "2026-02-15", 0, 500000),
        ]

        results = adapter._parse_rows(rows, latest_only=False)

        latest = next(r for r in results if r.settlement_date.day == 1)
        assert latest.change_pct is None  # avoid division by zero


@pytest.mark.asyncio
class TestRateLimiting:
    """Test that rate limiter is called."""

    async def test_rate_limiter_acquire_called(self):
        adapter = FinraAdapter(settings=_make_settings())
        adapter._rate_limiter = AsyncMock()
        adapter._rate_limiter.acquire = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[
            _make_api_row("AAPL", "2026-03-01", 5000000, 2500000)
        ])

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        adapter._session = mock_session

        with patch("src.data.adapters.finra_adapter.get_redis") as mock_redis:
            mock_redis.return_value = AsyncMock()
            await adapter._fetch_short_interest(["AAPL"])

        adapter._rate_limiter.acquire.assert_awaited_once()


@pytest.mark.asyncio
class TestCaching:
    """Test Redis cache behavior."""

    async def test_cache_hit_skips_http(self):
        adapter = FinraAdapter(settings=_make_settings())
        cached_data = ShortInterestData(
            symbol="AAPL",
            settlement_date=datetime(2026, 3, 1, tzinfo=UTC),
            short_interest=5000000,
            avg_daily_volume=2500000,
            days_to_cover=2.0,
        )

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(
            return_value=json.dumps(cached_data.model_dump(mode="json"))
        )

        with patch("src.data.adapters.finra_adapter.get_redis", return_value=mock_redis):
            results = await adapter.get_short_interest(["AAPL"], use_cache=True)

        assert len(results) == 1
        assert results[0].symbol == "AAPL"
        assert results[0].short_interest == 5000000
        # Adapter session should not have been created
        assert adapter._session is None

    async def test_cache_miss_triggers_fetch(self):
        adapter = FinraAdapter(settings=_make_settings())
        adapter._rate_limiter = AsyncMock()
        adapter._rate_limiter.acquire = AsyncMock()

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[
            _make_api_row("AAPL", "2026-03-01", 5000000, 2500000)
        ])

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        adapter._session = mock_session

        with patch("src.data.adapters.finra_adapter.get_redis", return_value=mock_redis):
            results = await adapter.get_short_interest(["AAPL"], use_cache=True)

        assert len(results) == 1
        mock_redis.set.assert_awaited_once()


class TestBadData:
    """Test handling of malformed data."""

    def test_bad_date_skips_row(self):
        adapter = FinraAdapter(settings=_make_settings())
        rows = [
            {
                "symbolCode": "AAPL",
                "settlementDate": "not-a-date",
                "currentShortPositionQuantity": 1000,
                "averageDailyVolumeQuantity": 500,
                "daysToCoverQuantity": 2.0,
            }
        ]

        results = adapter._parse_rows(rows, latest_only=True)

        assert results == []


@pytest.mark.asyncio
class TestErrorHandling:
    """Test graceful error handling."""

    async def test_api_error_returns_empty(self):
        adapter = FinraAdapter(settings=_make_settings())
        adapter._rate_limiter = AsyncMock()
        adapter._rate_limiter.acquire = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        adapter._session = mock_session

        results = await adapter._fetch_short_interest(["AAPL"])

        assert results == []

    async def test_empty_response_returns_empty(self):
        adapter = FinraAdapter(settings=_make_settings())
        adapter._rate_limiter = AsyncMock()
        adapter._rate_limiter.acquire = AsyncMock()

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[])

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_resp),
            __aexit__=AsyncMock(return_value=False),
        ))
        adapter._session = mock_session

        results = await adapter._fetch_short_interest(["AAPL"])

        assert results == []

    async def test_exception_in_fetch_returns_empty(self):
        adapter = FinraAdapter(settings=_make_settings())

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("src.data.adapters.finra_adapter.get_redis", return_value=mock_redis):
            with patch.object(adapter, "_fetch_short_interest", side_effect=Exception("network error")):
                results = await adapter.get_short_interest(["AAPL"], use_cache=True)

        assert results == []
