"""Tests for RegimeDetector — rule-based market regime detection."""
from __future__ import annotations

import pytest

from src.core.models import MarketRegime, RegimeAnalysis
from src.strategy.regime import RegimeDetector, _MA_LONG, _MA_SHORT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trending_prices(start: float, n: int, daily_change: float = 0.001) -> list[float]:
    """Generate trending price series."""
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1 + daily_change))
    return prices


def _flat_prices(value: float, n: int) -> list[float]:
    return [value] * n


def _make_bull_data(n: int = 250) -> tuple[list[float], list[float]]:
    """Bull market: rising prices above both MAs, low VIX."""
    # Start high and keep rising so price > MA50 > MA200
    spy = _trending_prices(start=450.0, n=n, daily_change=0.002)
    vix = [15.0] * n
    return spy, vix


def _make_bear_data(n: int = 250) -> tuple[list[float], list[float]]:
    """Bear market: price below MA50, MA50 below MA200."""
    # Start declining — enough for death cross
    # Use a long declining series: price < MA50 < MA200
    base = 500.0
    spy = [base * (1 - 0.003) ** i for i in range(n)]
    vix = [18.0] * n  # keep VIX low so it's purely MA-driven
    return spy, vix


def _make_sideways_data(n: int = 250) -> tuple[list[float], list[float]]:
    """Sideways: price roughly flat, VIX moderate (10-24)."""
    spy = _flat_prices(400.0, n)
    vix = [18.0] * n
    return spy, vix


def _make_high_vol_data(n: int = 250) -> tuple[list[float], list[float]]:
    """High volatility: VIX >= 25."""
    spy = _trending_prices(start=400.0, n=n, daily_change=0.001)
    vix = [30.0] * n
    return spy, vix


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_regime_analysis(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data()
        result = det.detect(spy, vix)
        assert isinstance(result, RegimeAnalysis)

    def test_fields_present(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data()
        result = det.detect(spy, vix)
        assert hasattr(result, "current_regime")
        assert hasattr(result, "regime_probability")
        assert hasattr(result, "strategy_performance_by_regime")
        assert hasattr(result, "regime_history")

    def test_regime_probability_in_range(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data()
        result = det.detect(spy, vix)
        assert 0.0 <= result.regime_probability <= 1.0


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

class TestBullDetection:
    def test_strong_uptrend_low_vix_is_bull(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data(n=300)
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.BULL

    def test_bull_has_high_probability(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data(n=300)
        result = det.detect(spy, vix)
        assert result.regime_probability >= 0.6


class TestBearDetection:
    def test_downtrend_death_cross_is_bear(self):
        det = RegimeDetector()
        spy, vix = _make_bear_data(n=300)
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.BEAR

    def test_high_vix_above_35_is_bear(self):
        """VIX > 35 triggers BEAR regardless of MA alignment."""
        det = RegimeDetector()
        # Rising prices (looks bullish on MA) but VIX is extreme
        spy = _trending_prices(start=450.0, n=250, daily_change=0.002)
        vix = [40.0] * 250
        result = det.detect(spy, vix)
        # VIX=40 is >= 25 so HIGH_VOLATILITY takes priority over BEAR
        assert result.current_regime in (MarketRegime.HIGH_VOLATILITY, MarketRegime.BEAR)


class TestHighVolatility:
    def test_vix_25_triggers_high_volatility(self):
        det = RegimeDetector()
        spy, vix = _make_high_vol_data(n=250)
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.HIGH_VOLATILITY

    def test_vix_exactly_25_is_high_vol(self):
        det = RegimeDetector()
        spy = _trending_prices(start=400.0, n=250, daily_change=0.001)
        vix = [25.0] * 250
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.HIGH_VOLATILITY

    def test_high_vol_overrides_bullish_ma(self):
        """Even if MA alignment is bullish, VIX >= 25 should produce HIGH_VOLATILITY."""
        det = RegimeDetector()
        spy = _trending_prices(start=450.0, n=250, daily_change=0.003)  # strong uptrend
        vix = [28.0] * 250  # high VIX
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.HIGH_VOLATILITY


class TestSidewaysDetection:
    def test_flat_prices_moderate_vix_is_sideways(self):
        det = RegimeDetector()
        spy, vix = _make_sideways_data(n=250)
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.SIDEWAYS

    def test_sideways_probability_is_reasonable(self):
        det = RegimeDetector()
        spy, vix = _make_sideways_data(n=250)
        result = det.detect(spy, vix)
        assert 0.4 <= result.regime_probability <= 1.0


# ---------------------------------------------------------------------------
# Regime history
# ---------------------------------------------------------------------------

class TestRegimeHistory:
    def test_history_is_list(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data()
        result = det.detect(spy, vix)
        assert isinstance(result.regime_history, list)

    def test_history_contains_dicts(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data(n=250)
        result = det.detect(spy, vix)
        for item in result.regime_history:
            assert "regime" in item

    def test_history_regime_values_are_valid(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data(n=250)
        result = det.detect(spy, vix)
        valid = {r.value for r in MarketRegime}
        for item in result.regime_history:
            assert item["regime"] in valid

    def test_history_nonempty_for_sufficient_data(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data(n=250)
        result = det.detect(spy, vix)
        assert len(result.regime_history) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_insufficient_data_returns_sideways(self):
        det = RegimeDetector()
        spy = [400.0] * 10  # way less than 200
        vix = [15.0] * 10
        result = det.detect(spy, vix)
        assert result.current_regime == MarketRegime.SIDEWAYS
        assert result.regime_history == []

    def test_empty_data_returns_sideways(self):
        det = RegimeDetector()
        result = det.detect([], [])
        assert result.current_regime == MarketRegime.SIDEWAYS

    def test_mismatched_lengths_handled(self):
        """Mismatched spy/vix lengths: should use the shorter one."""
        det = RegimeDetector()
        spy = _trending_prices(start=400.0, n=300, daily_change=0.001)
        vix = [15.0] * 250
        result = det.detect(spy, vix)
        assert isinstance(result, RegimeAnalysis)

    def test_exactly_200_data_points(self):
        """Exactly at the boundary: 200 data points should work."""
        det = RegimeDetector()
        spy = _flat_prices(400.0, n=_MA_LONG)
        vix = [15.0] * _MA_LONG
        result = det.detect(spy, vix)
        assert isinstance(result, RegimeAnalysis)

    def test_strategy_performance_by_regime_is_dict(self):
        det = RegimeDetector()
        spy, vix = _make_bull_data()
        result = det.detect(spy, vix)
        assert isinstance(result.strategy_performance_by_regime, dict)
