"""Tests for TechnicalFeatureCalculator."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.core.models import OHLCV
from src.signals.features.technical import TechnicalFeatureCalculator


EXPECTED_COLUMNS = [
    "ret_1d", "ret_5d", "ret_10d", "ret_20d",
    "sma_5_20_ratio", "sma_10_50_ratio", "sma_20_200_ratio",
    "ema_12_26_ratio",
    "rsi_14",
    "macd_line", "macd_signal", "macd_histogram",
    "bb_width", "bb_position",
    "atr_14", "atr_pct",
    "obv", "obv_sma_ratio",
    "volume_ratio_20d",
    "volatility_20d",
    "gap_pct",
    "high_low_range_pct",
    "momentum_10d",
    "close_sma20_pct",
    "vol_regime_5_20",
]


def _make_bars(n: int, seed: int = 42) -> list[OHLCV]:
    """Generate synthetic OHLCV bars as a random walk with realistic prices."""
    rng = np.random.default_rng(seed)
    price = 100.0
    bars: list[OHLCV] = []
    base_time = datetime(2024, 1, 2, 16, 0, 0)
    for i in range(n):
        ret = rng.normal(0.0005, 0.02)
        close = price * (1 + ret)
        high = close * (1 + abs(rng.normal(0, 0.01)))
        low = close * (1 - abs(rng.normal(0, 0.01)))
        open_ = price * (1 + rng.normal(0, 0.005))
        vol = int(rng.integers(500_000, 5_000_000))
        bars.append(OHLCV(
            symbol="TEST",
            timestamp=base_time + timedelta(days=i),
            open=round(open_, 2),
            high=round(high, 2),
            low=round(low, 2),
            close=round(close, 2),
            volume=vol,
            source="synthetic",
        ))
        price = close
    return bars


@pytest.fixture
def calculator() -> TechnicalFeatureCalculator:
    return TechnicalFeatureCalculator()


@pytest.fixture
def bars_200() -> list[OHLCV]:
    return _make_bars(200)


@pytest.fixture
def bars_30() -> list[OHLCV]:
    return _make_bars(30)


class TestAllColumnsPresent:
    def test_200_bars_has_all_columns(self, calculator: TechnicalFeatureCalculator, bars_200: list[OHLCV]):
        df = calculator.compute(bars_200)
        assert isinstance(df, pd.DataFrame)
        for col in EXPECTED_COLUMNS:
            assert col in df.columns, f"Missing column: {col}"
        assert len(df.columns) >= 25

    def test_row_count_matches_input(self, calculator: TechnicalFeatureCalculator, bars_200: list[OHLCV]):
        df = calculator.compute(bars_200)
        assert len(df) == 200


class TestNoLookAheadBias:
    def test_features_at_row_i_depend_only_on_past(self, calculator: TechnicalFeatureCalculator, bars_200: list[OHLCV]):
        full_df = calculator.compute(bars_200)
        # Compute on truncated data (first 100 bars)
        truncated_df = calculator.compute(bars_200[:100])
        # Features at row 99 (last row of truncated) should match full at same timestamp
        ts = truncated_df.index[-1]
        for col in EXPECTED_COLUMNS:
            val_trunc = truncated_df.loc[ts, col]
            val_full = full_df.loc[ts, col]
            if pd.isna(val_trunc) and pd.isna(val_full):
                continue
            assert np.isclose(val_trunc, val_full, rtol=1e-10), (
                f"Look-ahead bias in {col}: truncated={val_trunc}, full={val_full}"
            )


class TestShortHistory:
    def test_30_bars_fills_nan_gracefully(self, calculator: TechnicalFeatureCalculator, bars_30: list[OHLCV]):
        df = calculator.compute(bars_30)
        assert len(df) == 30
        # Long lookback features (sma_20_200_ratio needs 200 bars) should be NaN
        assert df["sma_20_200_ratio"].isna().any()
        # Short lookback features should have some non-NaN values
        assert df["ret_1d"].notna().any()
        assert df["high_low_range_pct"].notna().any()


class TestRSIValues:
    def test_rsi_between_0_and_100(self, calculator: TechnicalFeatureCalculator, bars_200: list[OHLCV]):
        df = calculator.compute(bars_200)
        rsi_vals = df["rsi_14"].dropna()
        assert len(rsi_vals) > 0
        assert (rsi_vals >= 0).all(), "RSI has values below 0"
        assert (rsi_vals <= 100).all(), "RSI has values above 100"


class TestSMARatioSpotCheck:
    def test_sma_5_20_ratio_matches_manual(self, calculator: TechnicalFeatureCalculator, bars_200: list[OHLCV]):
        df = calculator.compute(bars_200)
        # Reconstruct manually from close prices
        close = pd.Series(
            [b.close for b in sorted(bars_200, key=lambda b: b.timestamp)],
            index=[b.timestamp for b in sorted(bars_200, key=lambda b: b.timestamp)],
        )
        expected = close.rolling(5).mean() / close.rolling(20).mean()
        # Compare at rows where both are non-NaN
        valid = df["sma_5_20_ratio"].notna() & expected.notna()
        np.testing.assert_allclose(
            df.loc[valid, "sma_5_20_ratio"].values,
            expected[valid].values,
            rtol=1e-6,
        )


class TestNaNHandling:
    def test_gap_in_data_still_produces_features(self, calculator: TechnicalFeatureCalculator):
        bars = _make_bars(100, seed=99)
        # Remove bars 40-49 to create a gap
        gapped = bars[:40] + bars[50:]
        df = calculator.compute(gapped)
        assert len(df) == 90
        # Features should still be computed (some may be NaN around the gap, that's fine)
        assert df["ret_1d"].notna().any()
        assert df["close" if "close" in df.columns else "high_low_range_pct"].notna().any()
