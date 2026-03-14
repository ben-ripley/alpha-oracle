"""Tests for the EstimatesFeatureCalculator."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from src.core.models import AnalystEstimate
from src.signals.features.estimates import EstimatesFeatureCalculator


def _estimate(
    symbol: str = "AAPL",
    fiscal_date: str = "2025-12-31",
    consensus: float = 2.0,
    actual: float | None = 2.1,
    surprise_pct: float | None = 5.0,
    num_analysts: int = 10,
) -> AnalystEstimate:
    return AnalystEstimate(
        symbol=symbol,
        fiscal_date_ending=fiscal_date,
        consensus_estimate=consensus,
        actual=actual,
        surprise_pct=surprise_pct,
        num_analysts=num_analysts,
    )


class TestEmptyAndNoneInputs:
    """Graceful degradation tests."""

    def test_none_estimates_returns_nan_columns(self):
        calc = EstimatesFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        assert "earnings_surprise_pct" in df.columns
        assert df["earnings_surprise_pct"].isna().all()

    def test_empty_estimates_returns_nan_columns(self):
        calc = EstimatesFeatureCalculator()
        df = calc.compute([], [datetime(2026, 1, 1)])
        assert df["analyst_coverage_count"].isna().all()

    def test_empty_dates_returns_empty_df(self):
        calc = EstimatesFeatureCalculator()
        df = calc.compute([_estimate()], [])
        assert df.empty

    def test_all_expected_columns_present(self):
        calc = EstimatesFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        for col in ["earnings_surprise_pct", "earnings_revision_momentum",
                    "revenue_surprise_pct", "analyst_coverage_count", "estimate_dispersion"]:
            assert col in df.columns


class TestFeatureValues:
    """Test correct feature computation."""

    def test_earnings_surprise_pct_from_latest(self):
        calc = EstimatesFeatureCalculator()
        estimates = [_estimate(fiscal_date="2025-12-31", surprise_pct=6.36)]
        df = calc.compute(estimates, [datetime(2026, 1, 15)])
        assert df["earnings_surprise_pct"].iloc[0] == pytest.approx(6.36)

    def test_analyst_coverage_count(self):
        calc = EstimatesFeatureCalculator()
        estimates = [_estimate(num_analysts=15)]
        df = calc.compute(estimates, [datetime(2026, 1, 15)])
        assert df["analyst_coverage_count"].iloc[0] == 15.0

    def test_pit_correctness_excludes_future(self):
        calc = EstimatesFeatureCalculator()
        estimates = [
            _estimate(fiscal_date="2025-12-31", surprise_pct=5.0),
            _estimate(fiscal_date="2026-03-31", surprise_pct=10.0),  # future
        ]
        df = calc.compute(estimates, [datetime(2026, 1, 15)])
        # Should only use 2025-12-31 estimate
        assert df["earnings_surprise_pct"].iloc[0] == pytest.approx(5.0)

    def test_revision_momentum_computed(self):
        calc = EstimatesFeatureCalculator()
        estimates = [
            _estimate(fiscal_date="2025-06-30", surprise_pct=2.0),
            _estimate(fiscal_date="2025-09-30", surprise_pct=5.0),
        ]
        df = calc.compute(estimates, [datetime(2025, 12, 1)])
        assert df["earnings_revision_momentum"].iloc[0] == pytest.approx(3.0)

    def test_revision_momentum_nan_with_single_estimate(self):
        calc = EstimatesFeatureCalculator()
        estimates = [_estimate(fiscal_date="2025-12-31", surprise_pct=5.0)]
        df = calc.compute(estimates, [datetime(2026, 1, 1)])
        assert np.isnan(df["earnings_revision_momentum"].iloc[0])

    def test_estimate_dispersion_computed(self):
        calc = EstimatesFeatureCalculator()
        estimates = [
            _estimate(fiscal_date=f"2025-{m:02d}-30", consensus=float(i), surprise_pct=1.0)
            for i, m in enumerate([3, 6, 9, 12], start=1)
        ]
        df = calc.compute(estimates, [datetime(2026, 1, 1)])
        assert not np.isnan(df["estimate_dispersion"].iloc[0])
        assert df["estimate_dispersion"].iloc[0] > 0

    def test_no_estimates_before_date_returns_nan(self):
        calc = EstimatesFeatureCalculator()
        estimates = [_estimate(fiscal_date="2026-06-30", surprise_pct=5.0)]
        df = calc.compute(estimates, [datetime(2026, 1, 1)])
        assert np.isnan(df["earnings_surprise_pct"].iloc[0])

    def test_surprise_pct_none_maps_to_nan(self):
        calc = EstimatesFeatureCalculator()
        estimates = [_estimate(fiscal_date="2025-12-31", surprise_pct=None)]
        df = calc.compute(estimates, [datetime(2026, 1, 1)])
        assert np.isnan(df["earnings_surprise_pct"].iloc[0])

    def test_multiple_dates_all_computed(self):
        calc = EstimatesFeatureCalculator()
        estimates = [_estimate(fiscal_date="2025-06-30", surprise_pct=3.0)]
        dates = [datetime(2025, 9, 1), datetime(2026, 1, 1)]
        df = calc.compute(estimates, dates)
        assert len(df) == 2
        assert np.allclose(df["earnings_surprise_pct"].values, 3.0)

    def test_result_indexed_by_date(self):
        calc = EstimatesFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        assert df.index.name == "date"
