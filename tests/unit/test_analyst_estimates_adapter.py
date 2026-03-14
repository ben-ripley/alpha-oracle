"""Tests for the Alpha Vantage analyst estimates adapter."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import AnalystEstimate
from src.data.adapters.analyst_estimates_adapter import AnalystEstimatesAdapter


def _make_settings():
    settings = MagicMock()
    settings.alpha_vantage_api_key = "test_key"
    settings.data.alpha_vantage.rate_limit_per_minute = 5
    settings.data.alpha_vantage.cache_ttl_hours = 24
    return settings


_DEFAULT_QUARTERLY = [
    {
        "fiscalDateEnding": "2025-12-31",
        "reportedDate": "2026-01-28",
        "reportedEPS": "2.34",
        "estimatedEPS": "2.20",
        "surprise": "0.14",
        "surprisePercentage": "6.36",
    }
]


def _make_earnings_data(quarterly: list[dict] | None = None, use_default: bool = True) -> dict:
    if quarterly is None and use_default:
        quarterly = _DEFAULT_QUARTERLY
    elif quarterly is None:
        quarterly = []
    return {
        "symbol": "AAPL",
        "annualEarnings": [],
        "quarterlyEarnings": quarterly,
    }


class TestParseEstimates:
    """Test _parse_estimates without network calls."""

    def test_parse_single_quarter(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        data = _make_earnings_data()

        estimates = adapter._parse_estimates("AAPL", data, num_analysts=5)

        assert len(estimates) == 1
        e = estimates[0]
        assert e.symbol == "AAPL"
        assert e.fiscal_date_ending == "2025-12-31"
        assert e.consensus_estimate == pytest.approx(2.20)
        assert e.actual == pytest.approx(2.34)
        assert e.surprise_pct == pytest.approx(6.36)
        assert e.num_analysts == 5

    def test_none_strings_become_none(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        data = _make_earnings_data(quarterly=[{
            "fiscalDateEnding": "2025-09-30",
            "reportedEPS": "None",
            "estimatedEPS": "1.50",
            "surprisePercentage": "None",
        }])

        estimates = adapter._parse_estimates("AAPL", data, num_analysts=0)

        assert len(estimates) == 1
        assert estimates[0].actual is None
        assert estimates[0].surprise_pct is None

    def test_missing_consensus_estimate_skipped(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        data = _make_earnings_data(quarterly=[{
            "fiscalDateEnding": "2025-09-30",
            "reportedEPS": "1.50",
            "estimatedEPS": "None",  # no consensus = skip
        }])

        estimates = adapter._parse_estimates("AAPL", data, num_analysts=0)

        assert len(estimates) == 0

    def test_empty_quarterly_returns_empty(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        data = _make_earnings_data(quarterly=[], use_default=False)

        estimates = adapter._parse_estimates("AAPL", data, num_analysts=0)

        assert estimates == []

    def test_multiple_quarters(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        quarters = [
            {
                "fiscalDateEnding": f"2025-{(i*3):02d}-30" if i > 0 else "2025-03-31",
                "reportedEPS": str(1.0 + i * 0.1),
                "estimatedEPS": str(0.9 + i * 0.1),
                "surprisePercentage": "5.0",
            }
            for i in range(4)
        ]
        data = _make_earnings_data(quarterly=quarters)

        estimates = adapter._parse_estimates("AAPL", data, num_analysts=3)

        assert len(estimates) == 4
        for e in estimates:
            assert e.num_analysts == 3


class TestGetEstimates:
    """Test get_estimates with mocked Redis and HTTP."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        cached = AnalystEstimate(
            symbol="AAPL",
            fiscal_date_ending="2025-12-31",
            consensus_estimate=2.20,
            actual=2.34,
            surprise_pct=6.36,
            num_analysts=5,
        )
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps([cached.model_dump(mode="json")])

        with patch("src.data.adapters.analyst_estimates_adapter.get_redis", return_value=mock_redis):
            results = await adapter.get_estimates("AAPL")

        assert len(results) == 1
        assert results[0].fiscal_date_ending == "2025-12-31"

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch("src.data.adapters.analyst_estimates_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"Error Message": "Invalid API key"}
            results = await adapter.get_estimates("AAPL")

        assert results == []

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch("src.data.adapters.analyst_estimates_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {}
            results = await adapter.get_estimates("AAPL")

        assert results == []

    @pytest.mark.asyncio
    async def test_successful_fetch_stores_cache(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        earnings = _make_earnings_data()
        overview = {"Symbol": "AAPL", "AnalystRatingsBuy": "10", "AnalystRatingsHold": "5"}

        with patch("src.data.adapters.analyst_estimates_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.side_effect = [earnings, overview]
            results = await adapter.get_estimates("AAPL")

        assert len(results) == 1
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_returns_empty(self):
        adapter = AnalystEstimatesAdapter(settings=_make_settings())
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch("src.data.adapters.analyst_estimates_adapter.get_redis", return_value=mock_redis), \
             patch.object(adapter, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"Note": "API call frequency exceeded"}
            results = await adapter.get_estimates("AAPL")

        assert results == []


class TestOptionsFlowStub:
    """Test the options flow stub adapter."""

    @pytest.mark.asyncio
    async def test_returns_five_records(self):
        from src.data.adapters.options_flow_adapter import OptionsFlowAdapter
        adapter = OptionsFlowAdapter()
        records = await adapter.get_options_flow("AAPL")
        assert len(records) == 5

    @pytest.mark.asyncio
    async def test_records_have_correct_symbol(self):
        from src.data.adapters.options_flow_adapter import OptionsFlowAdapter
        adapter = OptionsFlowAdapter()
        records = await adapter.get_options_flow("TSLA")
        assert all(r.symbol == "TSLA" for r in records)

    @pytest.mark.asyncio
    async def test_put_call_ratio_computed(self):
        from src.data.adapters.options_flow_adapter import OptionsFlowAdapter
        adapter = OptionsFlowAdapter()
        records = await adapter.get_options_flow("MSFT")
        for r in records:
            assert r.put_call_ratio >= 0.0
            assert r.put_volume >= 0
            assert r.call_volume >= 0

    @pytest.mark.asyncio
    async def test_unusual_activity_flag(self):
        from src.data.adapters.options_flow_adapter import OptionsFlowAdapter
        adapter = OptionsFlowAdapter()
        records = await adapter.get_options_flow("AAPL")
        # Should have boolean flags
        assert all(isinstance(r.unusual_activity, bool) for r in records)


class TestGoogleTrendsStub:
    """Test the Google Trends stub adapter."""

    @pytest.mark.asyncio
    async def test_returns_records_per_keyword(self):
        from src.data.adapters.google_trends_adapter import GoogleTrendsAdapter
        adapter = GoogleTrendsAdapter()
        records = await adapter.get_trends("AAPL", ["Apple stock", "iPhone"])
        # 7 days * 2 keywords
        assert len(records) == 14

    @pytest.mark.asyncio
    async def test_correct_symbol(self):
        from src.data.adapters.google_trends_adapter import GoogleTrendsAdapter
        adapter = GoogleTrendsAdapter()
        records = await adapter.get_trends("TSLA", ["Tesla"])
        assert all(r.symbol == "TSLA" for r in records)

    @pytest.mark.asyncio
    async def test_defaults_to_symbol_keyword(self):
        from src.data.adapters.google_trends_adapter import GoogleTrendsAdapter
        adapter = GoogleTrendsAdapter()
        records = await adapter.get_trends("GOOG", [])
        assert len(records) == 7  # 7 days * 1 default keyword
        assert all(r.keyword == "GOOG" for r in records)

    @pytest.mark.asyncio
    async def test_interest_in_valid_range(self):
        from src.data.adapters.google_trends_adapter import GoogleTrendsAdapter
        adapter = GoogleTrendsAdapter()
        records = await adapter.get_trends("AAPL", ["Apple"])
        for r in records:
            assert 0.0 <= r.interest_over_time <= 100.0
