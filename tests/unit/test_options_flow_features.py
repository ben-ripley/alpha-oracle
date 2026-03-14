"""Tests for the OptionsFlowFeatureCalculator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from src.core.models import OptionsFlowRecord
from src.signals.features.options_flow import OptionsFlowFeatureCalculator


def _record(
    symbol: str = "AAPL",
    days_ago: int = 0,
    put_vol: int = 5000,
    call_vol: int = 10000,
    unusual: bool = False,
) -> OptionsFlowRecord:
    pcr = put_vol / call_vol if call_vol > 0 else 0.0
    return OptionsFlowRecord(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
        put_volume=put_vol,
        call_volume=call_vol,
        put_call_ratio=pcr,
        unusual_activity=unusual,
    )


class TestEmptyAndNoneInputs:
    """Graceful degradation tests."""

    def test_none_returns_nan_columns(self):
        calc = OptionsFlowFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        assert "put_call_ratio" in df.columns
        assert df["put_call_ratio"].isna().all()

    def test_empty_records_returns_nan_columns(self):
        calc = OptionsFlowFeatureCalculator()
        df = calc.compute([], [datetime(2026, 1, 1)])
        assert df["unusual_options_activity"].isna().all()

    def test_empty_dates_returns_empty_df(self):
        calc = OptionsFlowFeatureCalculator()
        df = calc.compute([_record()], [])
        assert df.empty

    def test_all_expected_columns_present(self):
        calc = OptionsFlowFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        for col in ["put_call_ratio", "put_call_ratio_zscore",
                    "unusual_options_activity", "options_volume_ratio"]:
            assert col in df.columns


class TestFeatureValues:
    """Test correct feature computation."""

    def test_put_call_ratio_from_latest(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=1, put_vol=5000, call_vol=10000)]
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        assert df["put_call_ratio"].iloc[0] == pytest.approx(0.5)

    def test_unusual_activity_flag_true(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=1, unusual=True)]
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        assert df["unusual_options_activity"].iloc[0] == 1.0

    def test_unusual_activity_flag_false(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=1, unusual=False)]
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        assert df["unusual_options_activity"].iloc[0] == 0.0

    def test_options_volume_ratio_computed(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=1, put_vol=3000, call_vol=7000)]
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        # put / (put + call) = 3000 / 10000 = 0.3
        assert df["options_volume_ratio"].iloc[0] == pytest.approx(0.3)

    def test_pcr_zscore_computed_with_multiple_records(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=i, put_vol=5000, call_vol=10000) for i in range(10)]
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        # All same PCR -> zscore should be 0
        assert df["put_call_ratio_zscore"].iloc[0] == pytest.approx(0.0)

    def test_pcr_zscore_nan_with_single_record(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=1)]
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        assert np.isnan(df["put_call_ratio_zscore"].iloc[0])

    def test_pit_excludes_future_records(self):
        calc = OptionsFlowFeatureCalculator()
        records = [
            _record(days_ago=-5, put_vol=20000, call_vol=5000),  # future
            _record(days_ago=1, put_vol=5000, call_vol=10000),   # past
        ]
        as_of = datetime.now().replace(tzinfo=None)
        df = calc.compute(records, [as_of])
        assert df["put_call_ratio"].iloc[0] == pytest.approx(0.5)

    def test_no_records_in_window_returns_nan(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=60)]  # outside 30d lookback
        df = calc.compute(records, [datetime.now().replace(tzinfo=None)])
        assert np.isnan(df["put_call_ratio"].iloc[0])

    def test_result_indexed_by_date(self):
        calc = OptionsFlowFeatureCalculator()
        df = calc.compute(None, [datetime(2026, 1, 1)])
        assert df.index.name == "date"

    def test_multiple_dates_computed(self):
        calc = OptionsFlowFeatureCalculator()
        records = [_record(days_ago=i) for i in range(10)]
        dates = [
            datetime.now().replace(tzinfo=None) - timedelta(days=5),
            datetime.now().replace(tzinfo=None),
        ]
        df = calc.compute(records, dates)
        assert len(df) == 2
