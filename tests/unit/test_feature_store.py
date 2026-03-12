"""Tests for the Feature Store with point-in-time joins."""
from __future__ import annotations

import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.core.models import (
    FundamentalData,
    InsiderTransaction,
    OHLCV,
    ShortInterestData,
)
from src.signals.feature_store import FeatureStore


# ---------------------------------------------------------------------------
# Synthetic data generators
# ---------------------------------------------------------------------------

def _make_bars(symbol: str, n: int, start: datetime | None = None) -> list[OHLCV]:
    """Generate n days of synthetic OHLCV bars."""
    start = start or datetime(2024, 1, 2)
    bars = []
    price = 100.0
    for i in range(n):
        dt = start + timedelta(days=i)
        # Skip weekends
        if dt.weekday() >= 5:
            continue
        change = np.random.uniform(-0.03, 0.03)
        close = price * (1 + change)
        bars.append(
            OHLCV(
                symbol=symbol,
                timestamp=dt,
                open=price,
                high=max(price, close) * 1.01,
                low=min(price, close) * 0.99,
                close=close,
                volume=int(np.random.uniform(1e6, 5e6)),
                source="test",
            )
        )
        price = close
    return bars


def _make_fundamentals(
    symbol: str, n: int, start: datetime | None = None, sector: str = "Technology"
) -> list[FundamentalData]:
    """Generate n quarterly fundamental filings."""
    start = start or datetime(2024, 1, 15)
    funds = []
    for i in range(n):
        dt = start + timedelta(days=90 * i)
        funds.append(
            FundamentalData(
                symbol=symbol,
                timestamp=dt,
                pe_ratio=15.0 + i,
                pb_ratio=2.0 + i * 0.1,
                ps_ratio=3.0,
                ev_ebitda=10.0,
                debt_to_equity=0.5,
                current_ratio=1.8,
                roe=0.15 + i * 0.01,
                revenue_growth=0.10,
                earnings_growth=0.12,
                dividend_yield=0.02,
                market_cap=1e10,
                sector=sector,
            )
        )
    return funds


def _make_insider_transactions(
    symbol: str, n: int, start: datetime | None = None
) -> list[InsiderTransaction]:
    start = start or datetime(2024, 2, 1)
    txns = []
    for i in range(n):
        txns.append(
            InsiderTransaction(
                symbol=symbol,
                filed_date=start + timedelta(days=14 * i),
                insider_name=f"Insider {i}",
                transaction_type="P" if i % 3 != 0 else "S",
                shares=1000.0,
                price_per_share=100.0,
            )
        )
    return txns


def _make_short_interest(
    symbol: str, n: int, start: datetime | None = None
) -> list[ShortInterestData]:
    start = start or datetime(2024, 1, 15)
    data = []
    for i in range(n):
        data.append(
            ShortInterestData(
                symbol=symbol,
                settlement_date=start + timedelta(days=14 * i),
                short_interest=int(1e6 + i * 1e5),
                avg_daily_volume=int(5e6),
                days_to_cover=2.0 + i * 0.1,
                short_pct_float=0.05 + i * 0.005,
                change_pct=0.01 * ((-1) ** i),
            )
        )
    return data


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_cache(tmp_path):
    """Provide a temporary cache directory."""
    return str(tmp_path / "features")


@pytest.fixture
def store(tmp_cache):
    return FeatureStore(cache_dir=tmp_cache)


@pytest.fixture
def bars_100():
    """100 business-day bars (will generate ~140 calendar days to get ~100 bars)."""
    return _make_bars("AAPL", 140)


@pytest.fixture
def spy_bars():
    return _make_bars("SPY", 140)


@pytest.fixture
def vix_bars():
    return _make_bars("VIX", 140, start=datetime(2024, 1, 2))


@pytest.fixture
def fundamentals():
    return _make_fundamentals("AAPL", 4)


@pytest.fixture
def sector_fundamentals():
    """Sector peers for point-in-time fundamental ranking."""
    peers = []
    for sym in ("MSFT", "GOOG", "META"):
        peers.extend(_make_fundamentals(sym, 4, sector="Technology"))
    return peers


@pytest.fixture
def insider_txns():
    return _make_insider_transactions("AAPL", 8)


@pytest.fixture
def short_data():
    return _make_short_interest("AAPL", 8)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFeatureMatrixShape:
    def test_output_has_50_plus_features(
        self, store, bars_100, spy_bars, vix_bars, fundamentals,
        sector_fundamentals, insider_txns, short_data,
    ):
        """Given 100 bars of synthetic data, output has (100, 50+) features."""
        df = store.compute_features(
            symbol="AAPL",
            bars=bars_100,
            spy_bars=spy_bars,
            vix_bars=vix_bars,
            fundamentals=fundamentals,
            sector_fundamentals=sector_fundamentals,
            insider_transactions=insider_txns,
            short_interest=short_data,
        )
        assert len(df) == len(bars_100)
        # Exclude the 'symbol' column from feature count
        feature_cols = [c for c in df.columns if c != "symbol"]
        assert len(feature_cols) >= 50, (
            f"Expected >= 50 feature columns, got {len(feature_cols)}: {feature_cols}"
        )

    def test_feature_count_minimum(self, store, bars_100):
        """Even with only technical + temporal, should have 25+ features."""
        df = store.compute_features(symbol="AAPL", bars=bars_100)
        feature_cols = [c for c in df.columns if c != "symbol"]
        assert len(feature_cols) >= 25


class TestNoFutureDataLeakage:
    def test_fundamentals_pit_safety(self, store, bars_100, fundamentals):
        """Feature at date T has no info from T+1.

        Verify fundamental features don't change until a new fundamental is filed.
        """
        df = store.compute_features(
            symbol="AAPL",
            bars=bars_100,
            fundamentals=fundamentals,
        )
        # fundamentals[0].timestamp is the first filing date
        fund_dates = sorted(f.timestamp for f in fundamentals)

        # Get a fundamental feature column (pe_sector_rank)
        if "pe_sector_rank" not in df.columns:
            pytest.skip("pe_sector_rank not in output (no sector peers)")

        # Between two filing dates, the fundamental features should be constant
        if len(fund_dates) >= 2:
            mask = (df.index > fund_dates[0]) & (df.index < fund_dates[1])
            segment = df.loc[mask, "pe_sector_rank"]
            if len(segment) > 1:
                # All values should be identical (same fundamental used)
                assert segment.nunique() == 1, (
                    "Fundamental features changed between filing dates - possible look-ahead bias"
                )

    def test_no_future_fundamental_before_first_filing(self, store):
        """Bars before any fundamental filing should have NaN fundamental features."""
        bars = _make_bars("TEST", 30, start=datetime(2024, 1, 2))
        # Fundamental filed on day 20
        fund = _make_fundamentals("TEST", 1, start=datetime(2024, 1, 25))

        df = store.compute_features(
            symbol="TEST", bars=bars, fundamentals=fund,
        )
        # Before the filing date, fundamental features should be NaN
        before = df[df.index < datetime(2024, 1, 25)]
        if "pe_sector_rank" in df.columns and len(before) > 0:
            assert before["pe_sector_rank"].isna().all(), (
                "Fundamental features present before filing date - look-ahead bias"
            )


class TestGracefulDegradation:
    def test_missing_fundamentals(self, store, bars_100):
        """Missing fundamental data still yields technical + temporal features."""
        df = store.compute_features(symbol="AAPL", bars=bars_100)
        assert "ret_1d" in df.columns
        assert "day_of_week" in df.columns
        assert len(df) == len(bars_100)

    def test_missing_cross_asset(self, store, bars_100, fundamentals):
        """Missing cross-asset data (no SPY bars) still yields other features."""
        df = store.compute_features(
            symbol="AAPL", bars=bars_100, fundamentals=fundamentals,
        )
        assert "ret_1d" in df.columns
        assert "day_of_week" in df.columns
        assert len(df) == len(bars_100)

    def test_empty_bars_returns_empty(self, store):
        """Empty bars input returns empty DataFrame."""
        df = store.compute_features(symbol="AAPL", bars=[])
        assert df.empty


class TestCachePersistence:
    def test_save_load_roundtrip(self, store, bars_100):
        """Save features, load them back, verify identical."""
        df = store.compute_features(symbol="AAPL", bars=bars_100)
        store.save(df, "AAPL")

        loaded = store.load("AAPL")
        assert loaded is not None
        pd.testing.assert_frame_equal(df, loaded)

    def test_load_with_date_filter(self, store, bars_100):
        """Load with start/end filters returns subset."""
        df = store.compute_features(symbol="AAPL", bars=bars_100)
        store.save(df, "AAPL")

        mid_date = df.index[len(df) // 2]
        loaded = store.load("AAPL", start=str(mid_date.date()))
        assert loaded is not None
        assert loaded.index.min() >= mid_date

    def test_load_nonexistent_returns_none(self, store):
        """Loading a non-existent symbol returns None."""
        assert store.load("NONEXISTENT") is None


class TestIncrementalUpdate:
    def test_incremental_compute(self, store):
        """Compute 50 dates, save, then compute 60 dates -- cache has all 60."""
        bars_70 = _make_bars("INCR", 70)  # ~50 business days
        bars_85 = _make_bars("INCR", 85)  # ~60 business days

        df1 = store.compute_features(symbol="INCR", bars=bars_70)
        store.save(df1, "INCR")

        df2 = store.compute_features(symbol="INCR", bars=bars_85)
        store.save(df2, "INCR")

        loaded = store.load("INCR")
        assert loaded is not None
        assert len(loaded) == len(bars_85)
        # The new frame should contain all dates from the larger set
        assert set(df1.index).issubset(set(loaded.index))


class TestSymbolColumn:
    def test_symbol_column_present(self, store, bars_100):
        """Output DataFrame has a symbol column."""
        df = store.compute_features(symbol="AAPL", bars=bars_100)
        assert "symbol" in df.columns
        assert (df["symbol"] == "AAPL").all()
