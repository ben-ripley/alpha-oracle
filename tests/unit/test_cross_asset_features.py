"""Tests for CrossAssetFeatureCalculator."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.core.models import OHLCV
from src.signals.features.cross_asset import CrossAssetFeatureCalculator


def _make_bars(
    symbol: str,
    n: int,
    base_price: float = 100.0,
    daily_returns: list[float] | None = None,
    start: datetime | None = None,
) -> list[OHLCV]:
    """Generate synthetic OHLCV bars."""
    start = start or datetime(2024, 1, 1)
    bars = []
    price = base_price
    for i in range(n):
        if daily_returns is not None and i < len(daily_returns):
            price = price * (1 + daily_returns[i])
        elif i > 0 and daily_returns is None:
            price = price * (1 + np.random.normal(0, 0.01))
        bars.append(
            OHLCV(
                symbol=symbol,
                timestamp=start + timedelta(days=i),
                open=price * 0.999,
                high=price * 1.005,
                low=price * 0.995,
                close=price,
                volume=1_000_000,
            )
        )
    return bars


@pytest.fixture
def calc():
    return CrossAssetFeatureCalculator()


class TestSPYBeta:
    def test_beta_approx_2x(self, calc):
        """Stock that moves 2x SPY should have beta near 2.0."""
        np.random.seed(42)
        n = 120
        spy_returns = [0.0] + [np.random.normal(0, 0.01) for _ in range(n - 1)]
        sym_returns = [r * 2 for r in spy_returns]

        spy_bars = _make_bars("SPY", n, daily_returns=spy_returns)
        sym_bars = _make_bars("AAPL", n, daily_returns=sym_returns)

        features = calc.compute(sym_bars, spy_bars)
        # Last value should be close to 2.0 (after 60-day window fills)
        beta = features["spy_beta_60d"].dropna().iloc[-1]
        assert 1.8 <= beta <= 2.2, f"Expected beta ~2.0, got {beta}"

    def test_correlation_perfectly_correlated(self, calc):
        """Stock perfectly correlated with SPY should have correlation near 1.0."""
        np.random.seed(42)
        n = 120
        spy_returns = [0.0] + [np.random.normal(0, 0.01) for _ in range(n - 1)]
        sym_returns = [r * 1.5 for r in spy_returns]  # Scaled but perfectly correlated

        spy_bars = _make_bars("SPY", n, daily_returns=spy_returns)
        sym_bars = _make_bars("AAPL", n, daily_returns=sym_returns)

        features = calc.compute(sym_bars, spy_bars)
        corr = features["spy_correlation_60d"].dropna().iloc[-1]
        assert corr > 0.95, f"Expected correlation ~1.0, got {corr}"


class TestVIXRegime:
    def test_vix_regimes(self, calc):
        """VIX levels map to correct regime categories."""
        n = 80
        start = datetime(2024, 1, 1)
        sym_bars = _make_bars("AAPL", n, start=start)
        spy_bars = _make_bars("SPY", n, start=start)

        # Create VIX bars at specific levels: 12, 20, 30, 40
        vix_levels = [12.0] * 20 + [20.0] * 20 + [30.0] * 20 + [40.0] * 20
        vix_bars = [
            OHLCV(
                symbol="VIX",
                timestamp=start + timedelta(days=i),
                open=vix_levels[i],
                high=vix_levels[i],
                low=vix_levels[i],
                close=vix_levels[i],
                volume=0,
            )
            for i in range(n)
        ]

        features = calc.compute(sym_bars, spy_bars, vix_bars=vix_bars)

        regimes = features["vix_regime"].dropna()
        # VIX=12 -> regime 0 (low)
        assert regimes.iloc[0] == 0.0
        # VIX=20 -> regime 1 (medium)
        assert regimes.iloc[20] == 1.0
        # VIX=30 -> regime 2 (high)
        assert regimes.iloc[40] == 2.0
        # VIX=40 -> regime 3 (extreme)
        assert regimes.iloc[60] == 3.0


class TestSectorRelativeStrength:
    def test_sector_rs(self, calc):
        """Stock gained 5%, sector gained 3% -> RS = 2%."""
        n = 80
        start = datetime(2024, 1, 1)

        # Build returns: flat for first 59 days, then specific 20-day returns
        flat = [0.0] * 60
        # 5% over 20 days for stock
        sym_daily = 0.05 / 20
        sym_returns = flat + [sym_daily] * 20
        # 3% over 20 days for sector
        sec_daily = 0.03 / 20
        sec_returns = flat + [sec_daily] * 20

        sym_bars = _make_bars("AAPL", n, daily_returns=sym_returns)
        spy_bars = _make_bars("SPY", n, start=start)
        sec_bars = _make_bars("XLK", n, daily_returns=sec_returns)

        features = calc.compute(sym_bars, spy_bars, sector_bars=sec_bars)
        rs = features["sector_relative_strength_20d"].dropna().iloc[-1]
        assert abs(rs - 0.02) < 0.005, f"Expected RS ~0.02, got {rs}"


class TestEmptyInput:
    def test_empty_spy_bars(self, calc):
        """Empty SPY bars produces NaN columns."""
        sym_bars = _make_bars("AAPL", 30)
        features = calc.compute(sym_bars, [])
        assert all(features[col].isna().all() for col in features.columns)
        assert len(features) == 30

    def test_empty_both(self, calc):
        """Empty both inputs produces empty DataFrame."""
        features = calc.compute([], [])
        assert features.empty
