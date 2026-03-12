"""Tests for MLSignalStrategy and ConfidenceCalibrator."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, SignalDirection
from src.signals.confidence import ConfidenceCalibrator
from src.signals.ml.config import MLConfig
from src.signals.ml.pipeline import MLPipeline
from src.signals.ml_strategy import MLSignalStrategy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bars(symbol: str, n: int = 100) -> list[OHLCV]:
    """Create synthetic OHLCV bars."""
    base = datetime(2024, 1, 1)
    rng = np.random.RandomState(42)
    bars = []
    price = 100.0
    for i in range(n):
        change = rng.normal(0, 1)
        price = max(price + change, 5.0)
        bars.append(OHLCV(
            symbol=symbol,
            timestamp=base + timedelta(days=i),
            open=price - 0.5,
            high=price + 1.0,
            low=price - 1.0,
            close=price,
            volume=int(rng.uniform(1e5, 1e6)),
        ))
    return bars


def _train_and_save_model(path, config: MLConfig | None = None) -> MLPipeline:
    """Train a tiny model on synthetic data and save it."""
    cfg = config or MLConfig(min_training_samples=20)
    pipeline = MLPipeline(config=cfg)

    rng = np.random.RandomState(42)
    n = 200
    features = pd.DataFrame({
        f"feat_{i}": rng.randn(n) for i in range(10)
    })
    # Synthetic target: class 0/1/2
    target = pd.Series(rng.choice([0, 1, 2], size=n, p=[0.3, 0.4, 0.3]))
    pipeline.train(features, target)
    pipeline.save_model(path)
    return pipeline


@pytest.fixture
def trained_model_path(tmp_path):
    path = tmp_path / "model.joblib"
    _train_and_save_model(str(path))
    return str(path)


@pytest.fixture
def mock_feature_store(tmp_path):
    """FeatureStore that returns synthetic features matching the trained model."""
    from unittest.mock import MagicMock

    rng = np.random.RandomState(42)
    store = MagicMock()

    def fake_compute(symbol, bars, spy_bars=None, **kwargs):
        df = pd.DataFrame({f"feat_{i}": rng.randn(1) for i in range(10)})
        df["symbol"] = symbol
        return df

    store.compute_features = fake_compute
    return store


# ---------------------------------------------------------------------------
# BaseStrategy interface tests
# ---------------------------------------------------------------------------

class TestMLSignalStrategyInterface:

    def test_is_base_strategy_subclass(self):
        assert issubclass(MLSignalStrategy, BaseStrategy)

    def test_name(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        assert strategy.name == "ml_xgboost_signal"

    def test_description(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        assert "XGBoost" in strategy.description

    def test_min_hold_days(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        assert strategy.min_hold_days >= 2
        assert strategy.min_hold_days == 3

    def test_get_required_data(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        required = strategy.get_required_data()
        assert "ohlcv" in required
        assert "fundamentals" in required
        assert "insider_transactions" in required
        assert "short_interest" in required

    def test_get_parameters(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        params = strategy.get_parameters()
        assert "model_path" in params
        assert "confidence_threshold" in params
        assert "prediction_horizon" in params


# ---------------------------------------------------------------------------
# Signal generation tests
# ---------------------------------------------------------------------------

class TestMLSignalStrategySignals:

    def test_generate_signals_with_trained_model(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        bars = _make_bars("AAPL", 50)
        data = {"AAPL": bars}
        signals = strategy.generate_signals(data)

        assert len(signals) == 1
        sig = signals[0]
        assert sig.symbol == "AAPL"
        assert sig.strategy_name == "ml_xgboost_signal"
        assert 0.0 <= sig.strength <= 1.0
        assert sig.direction in (SignalDirection.LONG, SignalDirection.SHORT, SignalDirection.FLAT)

    def test_signal_metadata_has_probabilities(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        signals = strategy.generate_signals({"AAPL": _make_bars("AAPL", 50)})
        assert len(signals) == 1
        meta = signals[0].metadata
        assert "prob_down" in meta
        assert "prob_flat" in meta
        assert "prob_up" in meta
        assert "pred_class" in meta
        assert meta["model_stale"] is False

    def test_signal_metadata_has_top_features(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        signals = strategy.generate_signals({"AAPL": _make_bars("AAPL", 50)})
        assert len(signals) == 1
        top_features = signals[0].metadata.get("top_features", {})
        assert len(top_features) <= 5
        assert len(top_features) > 0

    def test_multiple_symbols(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        data = {
            "AAPL": _make_bars("AAPL", 50),
            "MSFT": _make_bars("MSFT", 50),
        }
        signals = strategy.generate_signals(data)
        symbols = {s.symbol for s in signals}
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_empty_bars_skipped(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        signals = strategy.generate_signals({"AAPL": []})
        assert signals == []


# ---------------------------------------------------------------------------
# Fallback / stale model tests
# ---------------------------------------------------------------------------

class TestMLSignalStrategyFallback:

    def test_no_model_produces_flat_signals(self, tmp_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=str(tmp_path / "nonexistent.joblib"),
            feature_store=mock_feature_store,
        )
        signals = strategy.generate_signals({"AAPL": _make_bars("AAPL", 10)})
        assert len(signals) == 1
        assert signals[0].direction == SignalDirection.FLAT
        assert signals[0].strength == 0.0
        assert signals[0].metadata["fallback"] is True
        assert signals[0].metadata["model_stale"] is True

    def test_stale_model_produces_flat_signals(self, trained_model_path, mock_feature_store):
        strategy = MLSignalStrategy(
            model_path=trained_model_path, feature_store=mock_feature_store
        )
        # Simulate staleness by backdating model_loaded_at
        strategy._model_loaded_at = datetime.now(UTC) - timedelta(days=30)

        signals = strategy.generate_signals({"AAPL": _make_bars("AAPL", 10)})
        assert len(signals) == 1
        assert signals[0].direction == SignalDirection.FLAT
        assert signals[0].metadata["fallback"] is True
        assert signals[0].metadata["model_stale"] is True

    def test_low_confidence_produces_flat(self, trained_model_path, mock_feature_store):
        config = MLConfig(min_training_samples=20, confidence_threshold=0.99)
        strategy = MLSignalStrategy(
            model_path=trained_model_path,
            feature_store=mock_feature_store,
            config=config,
        )
        signals = strategy.generate_signals({"AAPL": _make_bars("AAPL", 50)})
        assert len(signals) == 1
        # With threshold=0.99, almost all signals should be FLAT
        assert signals[0].direction == SignalDirection.FLAT


# ---------------------------------------------------------------------------
# ConfidenceCalibrator tests
# ---------------------------------------------------------------------------

class TestConfidenceCalibrator:

    def test_unfitted_passthrough(self):
        cal = ConfidenceCalibrator(method="isotonic")
        proba = np.array([[0.2, 0.3, 0.5], [0.1, 0.8, 0.1]])
        result = cal.calibrate(proba)
        np.testing.assert_array_equal(result, proba)

    def test_isotonic_fit_and_calibrate(self):
        rng = np.random.RandomState(42)
        n = 200
        y_true = rng.choice([0, 1, 2], size=n, p=[0.3, 0.4, 0.3])
        y_proba = rng.dirichlet([1, 1, 1], size=n)

        cal = ConfidenceCalibrator(method="isotonic")
        cal.fit(y_true, y_proba)

        result = cal.calibrate(y_proba)
        assert result.shape == y_proba.shape
        # Rows should sum to ~1
        np.testing.assert_allclose(result.sum(axis=1), 1.0, atol=1e-6)
        # All values in [0, 1]
        assert (result >= 0.0).all()
        assert (result <= 1.0).all()

    def test_platt_fit_and_calibrate(self):
        rng = np.random.RandomState(42)
        n = 200
        y_true = rng.choice([0, 1, 2], size=n, p=[0.3, 0.4, 0.3])
        y_proba = rng.dirichlet([1, 1, 1], size=n)

        cal = ConfidenceCalibrator(method="platt")
        cal.fit(y_true, y_proba)

        result = cal.calibrate(y_proba)
        assert result.shape == y_proba.shape
        np.testing.assert_allclose(result.sum(axis=1), 1.0, atol=1e-6)

    def test_save_and_load(self, tmp_path):
        rng = np.random.RandomState(42)
        n = 200
        y_true = rng.choice([0, 1, 2], size=n, p=[0.3, 0.4, 0.3])
        y_proba = rng.dirichlet([1, 1, 1], size=n)

        cal = ConfidenceCalibrator(method="isotonic")
        cal.fit(y_true, y_proba)

        path = tmp_path / "calibrator.joblib"
        cal.save(str(path))

        cal2 = ConfidenceCalibrator()
        cal2.load(str(path))

        result1 = cal.calibrate(y_proba[:5])
        result2 = cal2.calibrate(y_proba[:5])
        np.testing.assert_array_almost_equal(result1, result2)

    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="Unknown calibration method"):
            ConfidenceCalibrator(method="invalid")

    def test_calibrate_with_calibrator_in_strategy(self, trained_model_path, mock_feature_store):
        """Verify the strategy uses the calibrator when provided."""
        rng = np.random.RandomState(42)
        n = 200
        y_true = rng.choice([0, 1, 2], size=n, p=[0.3, 0.4, 0.3])
        y_proba = rng.dirichlet([1, 1, 1], size=n)

        cal = ConfidenceCalibrator(method="isotonic")
        cal.fit(y_true, y_proba)

        strategy = MLSignalStrategy(
            model_path=trained_model_path,
            feature_store=mock_feature_store,
            calibrator=cal,
        )
        signals = strategy.generate_signals({"AAPL": _make_bars("AAPL", 50)})
        assert len(signals) == 1
        assert 0.0 <= signals[0].strength <= 1.0
