"""Tests for S&P 500 symbol universe manager."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.data.universe import SymbolUniverse

FAKE_MAPPING = {
    "AAPL": "Information Technology",
    "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary",
    "GOOGL": "Communication Services",
    "JPM": "Financials",
}

FAKE_CSV_CONTENT = (
    "Symbol,Name,Sector\n"
    "AAPL,Apple Inc,Information Technology\n"
    "MSFT,Microsoft Corp,Information Technology\n"
    "AMZN,Amazon.com Inc,Consumer Discretionary\n"
)


def _mock_redis(cached_data=None):
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=cached_data)
    redis.set = AsyncMock()
    return redis


@pytest.fixture
def universe():
    return SymbolUniverse()


@pytest.mark.asyncio
class TestGetSymbols:
    async def test_returns_symbols_from_wikipedia(self, universe):
        """get_symbols returns entries when Wikipedia scrape succeeds."""
        import pandas as pd

        fake_df = pd.DataFrame(
            {
                "Symbol": ["AAPL", "MSFT", "AMZN", "GOOGL", "JPM"],
                "Security": ["Apple", "Microsoft", "Amazon", "Alphabet", "JPMorgan"],
                "GICS Sector": [
                    "Information Technology",
                    "Information Technology",
                    "Consumer Discretionary",
                    "Communication Services",
                    "Financials",
                ],
            }
        )

        redis = _mock_redis(cached_data=None)
        with (
            patch("src.data.universe.get_redis", return_value=redis),
            patch("pandas.read_html", return_value=[fake_df]),
        ):
            symbols = await universe.get_symbols()

        assert len(symbols) == 5
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert symbols == sorted(symbols)

    async def test_get_sector_returns_correct_sector(self, universe):
        """get_sector returns correct GICS sector for a known symbol."""
        redis = _mock_redis(cached_data=json.dumps(FAKE_MAPPING))
        with patch("src.data.universe.get_redis", return_value=redis):
            sector = await universe.get_sector("AAPL")

        assert sector == "Information Technology"

    async def test_get_sector_returns_none_for_unknown(self, universe):
        """get_sector returns None for an unknown symbol."""
        redis = _mock_redis(cached_data=json.dumps(FAKE_MAPPING))
        with patch("src.data.universe.get_redis", return_value=redis):
            sector = await universe.get_sector("ZZZZ")

        assert sector is None

    async def test_cache_hit_skips_http_fetch(self, universe):
        """When Redis has cached data, Wikipedia is not fetched."""
        redis = _mock_redis(cached_data=json.dumps(FAKE_MAPPING))
        with (
            patch("src.data.universe.get_redis", return_value=redis),
            patch("pandas.read_html") as mock_read_html,
        ):
            symbols = await universe.get_symbols()

        mock_read_html.assert_not_called()
        assert len(symbols) == 5

    async def test_network_error_falls_back_to_csv(self, universe, tmp_path):
        """When Wikipedia fetch fails, data is loaded from CSV."""
        csv_file = tmp_path / "sp500_fallback.csv"
        csv_file.write_text(FAKE_CSV_CONTENT)

        redis = _mock_redis(cached_data=None)
        with (
            patch("src.data.universe.get_redis", return_value=redis),
            patch("pandas.read_html", side_effect=Exception("Network error")),
            patch.object(universe, "_settings") as mock_settings,
        ):
            mock_settings.cache_ttl_seconds = 86400
            mock_settings.fallback_csv = str(csv_file)
            mock_settings.indices = ["sp500"]
            symbols = await universe.get_symbols()

        assert len(symbols) == 3
        assert "AAPL" in symbols
        assert "MSFT" in symbols
        assert "AMZN" in symbols

    async def test_is_active_true_for_known_symbol(self, universe):
        """is_active returns True for a symbol in the universe."""
        redis = _mock_redis(cached_data=json.dumps(FAKE_MAPPING))
        with patch("src.data.universe.get_redis", return_value=redis):
            assert await universe.is_active("AAPL") is True

    async def test_is_active_false_for_unknown_symbol(self, universe):
        """is_active returns False for a symbol not in the universe."""
        redis = _mock_redis(cached_data=json.dumps(FAKE_MAPPING))
        with patch("src.data.universe.get_redis", return_value=redis):
            assert await universe.is_active("ZZZZ") is False

    async def test_refresh_returns_count(self, universe):
        """refresh forces a fetch and returns symbol count."""
        import pandas as pd

        fake_df = pd.DataFrame(
            {
                "Symbol": ["AAPL", "MSFT"],
                "Security": ["Apple", "Microsoft"],
                "GICS Sector": ["Information Technology", "Information Technology"],
            }
        )

        redis = _mock_redis()
        with (
            patch("src.data.universe.get_redis", return_value=redis),
            patch("pandas.read_html", return_value=[fake_df]),
        ):
            count = await universe.refresh()

        assert count == 2
        redis.set.assert_called_once()
