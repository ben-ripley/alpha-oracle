"""Rule-based market regime detection using SPY moving averages and VIX levels."""
from __future__ import annotations

import structlog

from src.core.models import MarketRegime, RegimeAnalysis

logger = structlog.get_logger(__name__)

# VIX thresholds
_VIX_HIGH_VOLATILITY = 25.0
_VIX_BEAR = 35.0
_VIX_BULL_MAX = 20.0

# MA windows
_MA_SHORT = 50
_MA_LONG = 200

# Minimum data required for a regime call
_MIN_DATA_POINTS = _MA_LONG


class RegimeDetector:
    """Rule-based market regime detection using SPY moving averages and VIX levels.

    Rules (evaluated in priority order):
    1. HIGH_VOLATILITY: VIX >= 25 (overrides BULL/BEAR/SIDEWAYS)
    2. BEAR: SPY < 50-day MA < 200-day MA, OR VIX > 35
    3. BULL: SPY > 50-day MA > 200-day MA AND VIX < 20
    4. SIDEWAYS: otherwise
    """

    def detect(
        self,
        spy_prices: list[float],
        vix_values: list[float],
    ) -> RegimeAnalysis:
        """Detect current regime and return history of recent regime detections.

        Args:
            spy_prices: Daily SPY closing prices (oldest first).
            vix_values: Daily VIX closing values aligned with spy_prices.

        Returns:
            RegimeAnalysis with current_regime, regime_probability, and regime_history.
        """
        if len(spy_prices) < _MIN_DATA_POINTS or len(vix_values) < _MIN_DATA_POINTS:
            logger.warning(
                "regime_insufficient_data",
                spy_len=len(spy_prices),
                vix_len=len(vix_values),
                required=_MIN_DATA_POINTS,
            )
            return RegimeAnalysis(
                current_regime=MarketRegime.SIDEWAYS,
                regime_probability=0.5,
                strategy_performance_by_regime={},
                regime_history=[],
            )

        # Align lengths
        n = min(len(spy_prices), len(vix_values))
        spy_prices = spy_prices[-n:]
        vix_values = vix_values[-n:]

        # Detect regime at the latest point
        current_regime, current_prob = self._classify(spy_prices, vix_values, idx=n - 1)

        # Build regime history by stepping back through the series (one point per day)
        history: list[dict] = []
        step = max(1, n // 50)  # sample at most 50 history points
        for i in range(_MA_LONG - 1, n, step):
            regime, _ = self._classify(spy_prices, vix_values, idx=i)
            history.append({"day_index": i, "regime": regime.value})

        logger.info(
            "regime_detected",
            current_regime=current_regime.value,
            regime_probability=round(current_prob, 3),
            history_points=len(history),
        )

        return RegimeAnalysis(
            current_regime=current_regime,
            regime_probability=current_prob,
            strategy_performance_by_regime={},
            regime_history=history,
        )

    def _classify(
        self,
        spy_prices: list[float],
        vix_values: list[float],
        idx: int,
    ) -> tuple[MarketRegime, float]:
        """Classify regime at position idx using available history."""
        current_price = spy_prices[idx]
        current_vix = vix_values[idx]

        # Compute MAs using data up to and including idx
        available = spy_prices[: idx + 1]
        ma50 = self._compute_ma(available, _MA_SHORT)
        ma200 = self._compute_ma(available, _MA_LONG)

        # Rule 1: HIGH_VOLATILITY overrides everything
        if current_vix >= _VIX_HIGH_VOLATILITY:
            # Confidence scales with distance above threshold
            prob = min(1.0, 0.5 + (current_vix - _VIX_HIGH_VOLATILITY) / 30.0)
            return MarketRegime.HIGH_VOLATILITY, round(prob, 3)

        # Rule 2a: BEAR — death cross (price confirmation)
        if ma50 > 0 and current_price < ma50 < ma200:
            gap = (ma50 - current_price) / ma50
            prob = 0.6 + min(gap * 5, 0.4)
            return MarketRegime.BEAR, round(prob, 3)

        # Rule 2b: BEAR — extreme VIX alone (lower confidence, no price confirmation)
        if current_vix > _VIX_BEAR:
            prob = 0.7
            return MarketRegime.BEAR, round(prob, 3)

        # Rule 3: BULL — golden cross with low VIX
        if ma50 > 0 and current_price > ma50 > ma200 and current_vix < _VIX_BULL_MAX:
            gap = (current_price - ma50) / ma50
            prob = 0.6 + min(gap * 5, 0.4)
            return MarketRegime.BULL, round(prob, 3)

        # Rule 4: SIDEWAYS — everything else
        return MarketRegime.SIDEWAYS, 0.6

    @staticmethod
    def _compute_ma(prices: list[float], window: int) -> float:
        """Compute simple moving average over the last `window` prices.

        Fallback behavior when insufficient data is available:
          - Fewer than `window` prices: use the mean of all available prices.
          - Empty price list: return 0.0 (callers treat ma50==0 or ma200==0 as
            "data unavailable" and skip the corresponding regime rule).
        """
        if len(prices) < window:
            return float(sum(prices)) / len(prices) if prices else 0.0
        return float(sum(prices[-window:])) / window
