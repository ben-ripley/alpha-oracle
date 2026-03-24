"""Smoke tests for FeatureStore and individual feature calculators.

No database, broker, or external data required — all tests use
synthetic in-memory OHLCV fixtures.

Column budget (with bars only, no optional data sources):
  Technical    25  (ret_1d .. vol_regime_5_20)
  Temporal      8  (day_of_week .. is_quarter_end)
  Cross-asset   8  (spy_beta_60d .. vix_change_5d — NaN when spy_bars=[])
  Alternative   9  (5 insider + 4 short — NaN when no transactions/short data)
  symbol        1  (string label)
  Total        51
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import sin

import numpy as np
import pandas as pd

from src.core.models import OHLCV, FundamentalData
from src.signals.feature_store import FeatureStore
from src.signals.features.cross_asset import CrossAssetFeatureCalculator
from src.signals.features.fundamental import FundamentalFeatureCalculator
from src.signals.features.technical import TechnicalFeatureCalculator
from src.signals.features.temporal import TemporalFeatureCalculator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_START = datetime(2023, 1, 3, tzinfo=UTC)  # Tuesday (market day)
_SYMBOL = "AAPL"
_BASE_PRICE = 150.0


def _make_bars(symbol: str = _SYMBOL, days: int = 60, base: float = _BASE_PRICE) -> list[OHLCV]:
    """Synthetic daily OHLCV with an oscillating price."""
    bars = []
    for i in range(days):
        close = base * (1.0 + 0.03 * sin(i / 8.0))
        bars.append(
            OHLCV(
                symbol=symbol,
                timestamp=_START + timedelta(days=i),
                open=close * 0.99,
                high=close * 1.015,
                low=close * 0.985,
                close=close,
                volume=1_000_000 + i * 500,
            )
        )
    return bars


def _make_fundamental(
    symbol: str = _SYMBOL,
    offset_days: int = 0,
) -> FundamentalData:
    return FundamentalData(
        symbol=symbol,
        timestamp=_START + timedelta(days=offset_days),
        pe_ratio=20.0,
        pb_ratio=4.0,
        ps_ratio=5.0,
        ev_ebitda=12.0,
        roe=0.18,
        revenue_growth=0.10,
        earnings_growth=0.12,
        debt_to_equity=0.5,
        current_ratio=1.8,
        dividend_yield=0.015,
        sector="Technology",
    )


# ---------------------------------------------------------------------------
# TechnicalFeatureCalculator
# ---------------------------------------------------------------------------

class TestTechnicalFeatureCalculator:
    def test_returns_dataframe(self):
        calc = TechnicalFeatureCalculator()
        df = calc.compute(_make_bars())
        assert isinstance(df, pd.DataFrame)

    def test_row_count_matches_input(self):
        bars = _make_bars(days=60)
        df = TechnicalFeatureCalculator().compute(bars)
        assert len(df) == 60

    def test_expected_columns_present(self):
        df = TechnicalFeatureCalculator().compute(_make_bars())
        expected = [
            "ret_1d", "ret_5d", "ret_10d", "ret_20d",
            "sma_5_20_ratio", "sma_10_50_ratio", "ema_12_26_ratio",
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
        for col in expected:
            assert col in df.columns, f"Missing column: {col}"

    def test_no_inf_values(self):
        df = TechnicalFeatureCalculator().compute(_make_bars())
        numeric = df.select_dtypes(include=[np.number])
        assert not np.isinf(numeric.values).any(), "Inf values found in technical features"

    def test_last_rows_have_core_features(self):
        """After sufficient lookback, core features should be non-NaN."""
        df = TechnicalFeatureCalculator().compute(_make_bars(days=60))
        # These features need at most 26 days of history; last 34 rows should be clean
        core_cols = ["ret_1d", "rsi_14", "bb_width", "ema_12_26_ratio", "atr_14"]
        tail = df[core_cols].iloc[-10:]
        assert not tail.isnull().any().any(), (
            f"NaN in core columns at last 10 rows:\n{tail.isnull().sum()}"
        )

    def test_sma_20_200_ratio_nan_with_60_bars(self):
        """sma_20_200_ratio must be NaN when fewer than 200 bars are provided."""
        df = TechnicalFeatureCalculator().compute(_make_bars(days=60))
        assert df["sma_20_200_ratio"].isna().all(), (
            "sma_20_200_ratio should be entirely NaN with only 60 bars"
        )

    def test_ret_1d_nan_only_on_first_row(self):
        df = TechnicalFeatureCalculator().compute(_make_bars(days=60))
        assert df["ret_1d"].isna().sum() == 1
        assert not df["ret_1d"].iloc[1:].isna().any()

    def test_column_count(self):
        df = TechnicalFeatureCalculator().compute(_make_bars())
        assert df.shape[1] >= 25


# ---------------------------------------------------------------------------
# TemporalFeatureCalculator
# ---------------------------------------------------------------------------

class TestTemporalFeatureCalculator:
    def test_returns_dataframe(self):
        calc = TemporalFeatureCalculator()
        dates = [_START + timedelta(days=i) for i in range(30)]
        df = calc.compute(dates)
        assert isinstance(df, pd.DataFrame)

    def test_expected_columns_present(self):
        dates = [_START + timedelta(days=i) for i in range(30)]
        df = TemporalFeatureCalculator().compute(dates)
        for col in ["day_of_week", "month", "quarter", "week_of_year",
                    "days_since_year_start", "is_month_end", "is_month_start",
                    "is_quarter_end"]:
            assert col in df.columns

    def test_no_nan_values(self):
        """Temporal features have no lookback dependency — should never be NaN."""
        dates = [_START + timedelta(days=i) for i in range(60)]
        df = TemporalFeatureCalculator().compute(dates)
        assert not df.isnull().any().any(), "Temporal features should never be NaN"

    def test_empty_dates_returns_empty_df(self):
        df = TemporalFeatureCalculator().compute([])
        assert df.empty

    def test_day_of_week_in_range(self):
        dates = [_START + timedelta(days=i) for i in range(20)]
        df = TemporalFeatureCalculator().compute(dates)
        assert df["day_of_week"].between(0, 6).all()

    def test_month_in_range(self):
        dates = [_START + timedelta(days=i) for i in range(60)]
        df = TemporalFeatureCalculator().compute(dates)
        assert df["month"].between(1, 12).all()


# ---------------------------------------------------------------------------
# CrossAssetFeatureCalculator
# ---------------------------------------------------------------------------

class TestCrossAssetFeatureCalculator:
    def test_no_spy_bars_returns_nan_columns(self):
        calc = CrossAssetFeatureCalculator()
        df = calc.compute(_make_bars(), spy_bars=[])
        assert not df.empty
        assert "spy_beta_60d" in df.columns
        assert df["spy_beta_60d"].isna().all()

    def test_with_spy_bars_computes_features(self):
        calc = CrossAssetFeatureCalculator()
        bars = _make_bars(days=70)
        spy = _make_bars("SPY", days=70, base=400.0)
        df = calc.compute(bars, spy_bars=spy)
        assert "spy_beta_60d" in df.columns
        assert "relative_strength_20d" in df.columns
        # After 60 rows the rolling beta is defined
        assert not df["spy_beta_60d"].iloc[-1:].isna().all()

    def test_column_count(self):
        df = CrossAssetFeatureCalculator().compute(_make_bars(), spy_bars=[])
        assert df.shape[1] == 8


# ---------------------------------------------------------------------------
# FundamentalFeatureCalculator
# ---------------------------------------------------------------------------

class TestFundamentalFeatureCalculator:
    def _make_peers(self, n: int = 5) -> list[FundamentalData]:
        values = [(15 + i * 3, 2 + i * 0.5, 8 + i) for i in range(n)]
        return [
            FundamentalData(
                symbol=f"PEER{i}",
                timestamp=_START,
                pe_ratio=v[0],
                pb_ratio=v[1],
                ev_ebitda=v[2],
                roe=0.10 + i * 0.02,
                current_ratio=1.5 + i * 0.1,
                sector="Technology",
            )
            for i, v in enumerate(values)
        ]

    def test_compute_returns_dict(self):
        target = _make_fundamental()
        peers = self._make_peers()
        features = FundamentalFeatureCalculator().compute(target, peers)
        assert isinstance(features, dict)

    def test_sector_ranks_in_0_1_range(self):
        target = _make_fundamental()
        peers = self._make_peers()
        features = FundamentalFeatureCalculator().compute(target, peers)
        for key, val in features.items():
            if val is not None and "rank" in key:
                assert 0.0 <= val <= 1.0, f"{key}={val} out of [0,1]"

    def test_quality_score_computed(self):
        target = _make_fundamental()
        peers = self._make_peers()
        features = FundamentalFeatureCalculator().compute(target, peers)
        assert features.get("quality_score") is not None


# ---------------------------------------------------------------------------
# FeatureStore — end-to-end compute_features()
# ---------------------------------------------------------------------------

class TestFeatureStore:
    def test_returns_dataframe(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        assert isinstance(df, pd.DataFrame)

    def test_row_count_matches_input(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        bars = _make_bars(days=60)
        df = store.compute_features(_SYMBOL, bars)
        assert len(df) == 60

    def test_empty_bars_returns_empty_df(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, [])
        assert df.empty

    def test_symbol_column_present_with_correct_value(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        assert "symbol" in df.columns
        assert (df["symbol"] == _SYMBOL).all()

    def test_technical_columns_present(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        for col in ["ret_1d", "rsi_14", "bb_width", "atr_14", "obv", "volatility_20d"]:
            assert col in df.columns, f"Missing technical column: {col}"

    def test_temporal_columns_present(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        for col in ["day_of_week", "month", "quarter", "is_month_end"]:
            assert col in df.columns, f"Missing temporal column: {col}"

    def test_cross_asset_columns_present_even_without_spy(self):
        """Cross-asset columns are added as NaN when spy_bars is not provided."""
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        assert "spy_beta_60d" in df.columns
        assert df["spy_beta_60d"].isna().all()

    def test_alternative_columns_present_even_without_data(self):
        """Alternative columns are added as NaN when no transactions/short data."""
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        for col in ["insider_buy_ratio", "short_interest_ratio"]:
            assert col in df.columns

    def test_total_column_count(self):
        """With just bars, expect 51 columns (50 numeric + symbol)."""
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        assert df.shape[1] >= 50, (
            f"Expected >= 50 columns, got {df.shape[1]}. Columns: {list(df.columns)}"
        )

    def test_no_inf_values(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars())
        numeric = df.select_dtypes(include=[np.number])
        assert not np.isinf(numeric.values).any(), "Inf values found in feature output"

    def test_temporal_features_never_nan(self):
        """Temporal features have no lookback — must always be populated."""
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars(days=60))
        temporal_cols = ["day_of_week", "month", "quarter", "week_of_year"]
        assert not df[temporal_cols].isnull().any().any()

    def test_core_technical_non_nan_at_tail(self):
        """After 60 bars, short-lookback technical features should be non-NaN."""
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        df = store.compute_features(_SYMBOL, _make_bars(days=60))
        core = ["ret_1d", "rsi_14", "bb_width", "ema_12_26_ratio", "gap_pct"]
        tail = df[core].iloc[-10:]
        assert not tail.isnull().any().any(), (
            f"NaN in core technical columns at last 10 rows:\n{tail.isnull().sum()}"
        )

    def test_with_spy_bars_populates_cross_asset(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        bars = _make_bars(days=70)
        spy = _make_bars("SPY", days=70, base=400.0)
        df = store.compute_features(_SYMBOL, bars, spy_bars=spy)
        # After 60-bar rolling window, last row should have a real beta
        assert not df["spy_beta_60d"].iloc[-1:].isna().all()

    def test_with_fundamentals_adds_fundamental_columns(self):
        store = FeatureStore(cache_dir="/tmp/test_feature_store_smoke")
        bars = _make_bars(days=60)
        fund = _make_fundamental()
        peers = [
            FundamentalData(
                symbol=f"PEER{i}", timestamp=_START,
                pe_ratio=10.0 + i * 5, pb_ratio=2.0 + i,
                ev_ebitda=8.0 + i, sector="Technology",
            )
            for i in range(4)
        ]
        df = store.compute_features(
            _SYMBOL, bars,
            fundamentals=[fund],
            sector_fundamentals=peers,
        )
        # Fundamental columns should now be present
        assert "pe_sector_rank" in df.columns
        assert "quality_score" in df.columns

    def test_save_and_load_roundtrip(self, tmp_path):
        store = FeatureStore(cache_dir=str(tmp_path))
        bars = _make_bars(days=60)
        df_original = store.compute_features(_SYMBOL, bars)
        store.save(df_original, _SYMBOL)

        df_loaded = store.load(_SYMBOL)
        assert df_loaded is not None
        assert df_loaded.shape == df_original.shape

    def test_load_returns_none_for_missing_symbol(self, tmp_path):
        store = FeatureStore(cache_dir=str(tmp_path))
        result = store.load("NONEXISTENT")
        assert result is None
