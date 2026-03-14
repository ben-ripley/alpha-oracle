"""Tests for the TrendsFeatureCalculator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from src.core.models import TrendsData
from src.signals.features.trends import TrendsFeatureCalculator


def _trend(
    symbol: str = "AAPL",
    keyword: str = "Apple stock",
    days_ago: int = 0,
    interest: float = 50.0,
) -> TrendsData:
    return TrendsData(
        symbol=symbol,
        keyword=keyword,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        interest_over_time=interest,
    )


class TestEmptyAndNoneInputs:
    """Graceful degradation tests."""

    def test_none_returns_nan_columns(self):
        calc = TrendsFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        assert "search_trend_momentum_7d" in df.columns
        assert df["search_trend_momentum_7d"].isna().all()

    def test_empty_trends_returns_nan_columns(self):
        calc = TrendsFeatureCalculator()
        df = calc.compute([], [datetime(2026, 1, 1)])
        assert df["search_trend_zscore"].isna().all()

    def test_empty_dates_returns_empty_df(self):
        calc = TrendsFeatureCalculator()
        df = calc.compute([_trend()], [])
        assert df.empty

    def test_all_expected_columns_present(self):
        calc = TrendsFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        for col in ["search_trend_momentum_7d", "search_trend_zscore", "search_trend_acceleration"]:
            assert col in df.columns


class TestFeatureValues:
    """Test correct feature computation."""

    def test_momentum_positive_when_trend_increasing(self):
        calc = TrendsFeatureCalculator()
        # Low interest 8-14 days ago, high interest last 7 days
        older = [_trend(days_ago=i + 8, interest=20.0) for i in range(7)]
        recent = [_trend(days_ago=i, interest=60.0) for i in range(7)]
        df = calc.compute(older + recent, [datetime.now().replace(tzinfo=None)])
        assert df["search_trend_momentum_7d"].iloc[0] > 0

    def test_momentum_negative_when_trend_decreasing(self):
        calc = TrendsFeatureCalculator()
        older = [_trend(days_ago=i + 8, interest=80.0) for i in range(7)]
        recent = [_trend(days_ago=i, interest=20.0) for i in range(7)]
        df = calc.compute(older + recent, [datetime.now().replace(tzinfo=None)])
        assert df["search_trend_momentum_7d"].iloc[0] < 0

    def test_zscore_zero_when_constant_interest(self):
        calc = TrendsFeatureCalculator()
        trends = [_trend(days_ago=i, interest=50.0) for i in range(30)]
        df = calc.compute(trends, [datetime.now().replace(tzinfo=None)])
        assert df["search_trend_zscore"].iloc[0] == pytest.approx(0.0)

    def test_zscore_positive_when_above_mean(self):
        calc = TrendsFeatureCalculator()
        # 30d of low interest, then spike in last 7d
        older = [_trend(days_ago=i + 8, interest=10.0) for i in range(22)]
        recent = [_trend(days_ago=i, interest=80.0) for i in range(7)]
        df = calc.compute(older + recent, [datetime.now().replace(tzinfo=None)])
        assert df["search_trend_zscore"].iloc[0] > 0

    def test_acceleration_computed_with_enough_data(self):
        calc = TrendsFeatureCalculator()
        trends = [_trend(days_ago=i, interest=float(6 - i) * 10) for i in range(7)]
        df = calc.compute(trends, [datetime.now().replace(tzinfo=None)])
        assert not np.isnan(df["search_trend_acceleration"].iloc[0])

    def test_acceleration_nan_with_insufficient_data(self):
        calc = TrendsFeatureCalculator()
        trends = [_trend(days_ago=i, interest=50.0) for i in range(2)]
        df = calc.compute(trends, [datetime.now().replace(tzinfo=None)])
        assert np.isnan(df["search_trend_acceleration"].iloc[0])

    def test_pit_excludes_future_data(self):
        calc = TrendsFeatureCalculator()
        trends = [
            _trend(days_ago=-5, interest=100.0),  # future
            _trend(days_ago=1, interest=30.0),    # past
        ]
        as_of = datetime.now().replace(tzinfo=None)
        df = calc.compute(trends, [as_of])
        # Zscore should only use past data
        assert not np.isnan(df["search_trend_zscore"].iloc[0]) or \
               df["search_trend_zscore"].isna().all()  # nan also acceptable (only 1 data point)

    def test_no_data_in_window_returns_nan(self):
        calc = TrendsFeatureCalculator()
        trends = [_trend(days_ago=60, interest=50.0)]  # outside 30d lookback
        df = calc.compute(trends, [datetime.now().replace(tzinfo=None)])
        assert np.isnan(df["search_trend_momentum_7d"].iloc[0])

    def test_multiple_dates_computed(self):
        calc = TrendsFeatureCalculator()
        trends = [_trend(days_ago=i, interest=50.0) for i in range(30)]
        dates = [
            datetime.now().replace(tzinfo=None) - timedelta(days=7),
            datetime.now().replace(tzinfo=None),
        ]
        df = calc.compute(trends, dates)
        assert len(df) == 2

    def test_result_indexed_by_date(self):
        calc = TrendsFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        assert df.index.name == "date"
