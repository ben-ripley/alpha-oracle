"""Unit tests for data normalizers (pure functions, no mocking needed)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.normalizer import (
    normalize_alpaca_bars,
    normalize_av_bars,
    normalize_av_fundamentals,
    normalize_edgar_filing,
)


class TestAlpacaBars:
    """Tests for Alpaca bar normalization."""

    def test_short_key_names_mapped_correctly(self):
        """Short key names (o, h, l, c, v, t) mapped correctly."""
        raw_bars = [
            {
                "t": datetime(2024, 1, 5, 14, 30, tzinfo=timezone.utc),
                "o": 150.0,
                "h": 152.5,
                "l": 149.0,
                "c": 151.0,
                "v": 1_000_000,
            }
        ]

        result = normalize_alpaca_bars(raw_bars, "AAPL")

        assert len(result) == 1
        bar = result[0]
        assert bar.symbol == "AAPL"
        assert bar.open == 150.0
        assert bar.high == 152.5
        assert bar.low == 149.0
        assert bar.close == 151.0
        assert bar.volume == 1_000_000
        assert bar.source == "alpaca"

    def test_long_key_names_mapped_correctly(self):
        """Long key names (open, high, low, close, volume, timestamp) mapped correctly."""
        raw_bars = [
            {
                "timestamp": datetime(2024, 1, 5, 14, 30, tzinfo=timezone.utc),
                "open": 150.0,
                "high": 152.5,
                "low": 149.0,
                "close": 151.0,
                "volume": 1_000_000,
            }
        ]

        result = normalize_alpaca_bars(raw_bars, "MSFT")

        assert len(result) == 1
        bar = result[0]
        assert bar.symbol == "MSFT"
        assert bar.open == 150.0
        assert bar.high == 152.5
        assert bar.low == 149.0
        assert bar.close == 151.0
        assert bar.volume == 1_000_000

    def test_timestamp_string_parsed_correctly(self):
        """Timestamp string parsed correctly (ISO format with Z suffix)."""
        raw_bars = [
            {
                "t": "2024-01-05T14:30:00Z",
                "o": 150.0,
                "h": 152.5,
                "l": 149.0,
                "c": 151.0,
                "v": 1_000_000,
            }
        ]

        result = normalize_alpaca_bars(raw_bars, "GOOG")

        assert len(result) == 1
        bar = result[0]
        assert bar.timestamp.year == 2024
        assert bar.timestamp.month == 1
        assert bar.timestamp.day == 5
        assert bar.timestamp.hour == 14
        assert bar.timestamp.minute == 30


class TestAVBars:
    """Tests for Alpha Vantage bar normalization."""

    def test_numbered_keys_parsed_correctly(self):
        """Numbered keys ("1. open", etc.) parsed correctly."""
        raw_data = {
            "Time Series (Daily)": {
                "2024-01-05": {
                    "1. open": "150.00",
                    "2. high": "152.50",
                    "3. low": "149.00",
                    "4. close": "151.00",
                    "5. adjusted close": "150.80",
                    "6. volume": "1000000",
                }
            }
        }

        result = normalize_av_bars(raw_data, "AAPL")

        assert len(result) == 1
        bar = result[0]
        assert bar.symbol == "AAPL"
        assert bar.open == 150.0
        assert bar.high == 152.5
        assert bar.low == 149.0
        assert bar.close == 151.0
        assert bar.adjusted_close == 150.80
        assert bar.volume == 1_000_000
        assert bar.source == "alpha_vantage"

    def test_results_sorted_by_date(self):
        """Results sorted by date."""
        raw_data = {
            "Time Series (Daily)": {
                "2024-01-03": {
                    "1. open": "148.00",
                    "2. high": "149.00",
                    "3. low": "147.00",
                    "4. close": "148.50",
                    "5. adjusted close": "148.50",
                    "6. volume": "900000",
                },
                "2024-01-05": {
                    "1. open": "150.00",
                    "2. high": "152.50",
                    "3. low": "149.00",
                    "4. close": "151.00",
                    "5. adjusted close": "150.80",
                    "6. volume": "1000000",
                },
                "2024-01-04": {
                    "1. open": "149.00",
                    "2. high": "150.50",
                    "3. low": "148.50",
                    "4. close": "149.80",
                    "5. adjusted close": "149.80",
                    "6. volume": "950000",
                },
            }
        }

        result = normalize_av_bars(raw_data, "MSFT")

        assert len(result) == 3
        # Should be sorted chronologically
        assert result[0].timestamp.day == 3
        assert result[1].timestamp.day == 4
        assert result[2].timestamp.day == 5

    def test_adjusted_close_included(self):
        """Adjusted close included."""
        raw_data = {
            "Time Series (Daily)": {
                "2024-01-05": {
                    "1. open": "150.00",
                    "2. high": "152.50",
                    "3. low": "149.00",
                    "4. close": "151.00",
                    "5. adjusted close": "149.50",
                    "6. volume": "1000000",
                }
            }
        }

        result = normalize_av_bars(raw_data, "TSLA")

        assert result[0].close == 151.0
        assert result[0].adjusted_close == 149.5


class TestAVFundamentals:
    """Tests for Alpha Vantage fundamentals normalization."""

    def test_numeric_values_parsed_to_float(self):
        """Numeric values parsed to float."""
        raw_data = {
            "PERatio": "25.5",
            "PriceToBookRatio": "3.2",
            "PriceToSalesRatioTTM": "2.8",
            "DebtToEquity": "45.2",
            "CurrentRatio": "1.5",
            "Sector": "Technology",
            "Industry": "Software",
        }

        result = normalize_av_fundamentals(raw_data, "AAPL")

        assert result.symbol == "AAPL"
        assert result.pe_ratio == 25.5
        assert result.pb_ratio == 3.2
        assert result.ps_ratio == 2.8
        assert result.debt_to_equity == 45.2
        assert result.current_ratio == 1.5
        assert result.sector == "Technology"
        assert result.industry == "Software"

    def test_none_string_converted_to_none(self):
        """'None' string converted to None."""
        raw_data = {
            "PERatio": "None",
            "PriceToBookRatio": "None",
            "DebtToEquity": "None",
            "Sector": "Technology",
        }

        result = normalize_av_fundamentals(raw_data, "STARTUP")

        assert result.pe_ratio is None
        assert result.pb_ratio is None
        assert result.debt_to_equity is None

    def test_missing_keys_default_to_none(self):
        """Missing keys default to None."""
        raw_data = {
            "Sector": "Healthcare",
            "Industry": "Pharmaceuticals",
        }

        result = normalize_av_fundamentals(raw_data, "BIOTECH")

        assert result.symbol == "BIOTECH"
        assert result.pe_ratio is None
        assert result.pb_ratio is None
        assert result.ps_ratio is None
        assert result.debt_to_equity is None
        assert result.sector == "Healthcare"
        assert result.industry == "Pharmaceuticals"


class TestEdgarFiling:
    """Tests for EDGAR filing normalization."""

    def test_date_string_parsed_correctly(self):
        """Date string parsed correctly."""
        raw = {
            "formType": "10-K",
            "filed": "2024-01-15",
            "url": "https://sec.gov/filing/123",
            "content": "Filing content here",
            "extra": "metadata",
        }

        result = normalize_edgar_filing(raw, "AAPL")

        assert result.symbol == "AAPL"
        assert result.filing_type == "10-K"
        assert result.filed_date.year == 2024
        assert result.filed_date.month == 1
        assert result.filed_date.day == 15
        assert result.url == "https://sec.gov/filing/123"
        assert result.content == "Filing content here"
        assert "extra" in result.metadata
        assert "content" not in result.metadata
        assert "url" not in result.metadata

    def test_invalid_date_falls_back_to_now(self):
        """Invalid date falls back to now."""
        raw = {
            "formType": "8-K",
            "filed": "invalid-date",
            "url": "https://sec.gov/filing/456",
        }

        result = normalize_edgar_filing(raw, "MSFT")

        # Should use current time as fallback
        assert result.filed_date is not None
        # Check it's recent (within last minute)
        now = datetime.now(tz=timezone.utc)
        time_diff = abs((now - result.filed_date).total_seconds())
        assert time_diff < 60

    def test_metadata_excludes_content_url_filed(self):
        """Metadata excludes content/url/filed fields."""
        raw = {
            "formType": "10-Q",
            "filed": "2024-01-15",
            "url": "https://sec.gov/filing/789",
            "content": "Some content",
            "accessionNumber": "0001234567-24-000001",
            "filingDate": "2024-01-15",
            "reportDate": "2023-12-31",
        }

        result = normalize_edgar_filing(raw, "TSLA")

        # These should be in metadata
        assert "accessionNumber" in result.metadata
        assert "filingDate" in result.metadata
        assert "reportDate" in result.metadata

        # These should NOT be in metadata
        assert "content" not in result.metadata
        assert "url" not in result.metadata
        assert "filed" not in result.metadata
        assert "formType" not in result.metadata
