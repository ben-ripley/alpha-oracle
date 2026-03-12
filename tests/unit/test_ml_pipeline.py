"""Tests for the XGBoost ML training pipeline."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.signals.ml.config import MLConfig
from src.signals.ml.pipeline import MLPipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> MLConfig:
    defaults = dict(prediction_horizon=5, up_threshold=0.01, down_threshold=-0.01, min_training_samples=500)
    defaults.update(overrides)
    return MLConfig(**defaults)


def _synthetic_features_and_target(n_rows: int = 700, n_features: int = 10, seed: int = 42):
    """Generate random features and a balanced 3-class target."""
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n_rows, freq="B")
    features = pd.DataFrame(
        rng.randn(n_rows, n_features),
        index=dates,
        columns=[f"feat_{i}" for i in range(n_features)],
    )
    target = pd.Series(rng.choice([0, 1, 2], size=n_rows), index=dates)
    return features, target


# ---------------------------------------------------------------------------
# Target preparation
# ---------------------------------------------------------------------------

class TestPrepareTarget:
    def test_target_uses_forward_return(self):
        """Target at T uses return from T to T+horizon."""
        config = _make_config(prediction_horizon=3, up_threshold=0.01, down_threshold=-0.01)
        pipe = MLPipeline(config)

        # Simple ascending prices: each step +1%
        prices = [100.0 * (1.01 ** i) for i in range(20)]
        df = pd.DataFrame({"close": prices}, index=pd.date_range("2020-01-01", periods=20, freq="B"))

        target = pipe.prepare_target(df)

        # All non-NaN targets should be UP (3-day return of ~3.03% > 1%)
        valid = target.dropna().astype(int)
        assert (valid == 2).all(), f"Expected all UP, got {valid.value_counts().to_dict()}"

        # Last 3 should be NaN
        assert target.iloc[-3:].isna().all()

    def test_target_labels_up_down_flat(self):
        """Verify correct labeling for different return patterns."""
        config = _make_config(prediction_horizon=1, up_threshold=0.01, down_threshold=-0.01)
        pipe = MLPipeline(config)

        # Construct prices so forward returns are known
        # T0->T1: +2%, T1->T2: -2%, T2->T3: +0.1% (flat)
        prices = [100.0, 102.0, 99.96, 100.06]
        df = pd.DataFrame({"close": prices}, index=pd.date_range("2020-01-01", periods=4, freq="B"))

        target = pipe.prepare_target(df)

        assert int(target.iloc[0]) == 2   # UP (+2%)
        assert int(target.iloc[1]) == 0   # DOWN (-2%)
        assert int(target.iloc[2]) == 1   # FLAT (+0.1%)
        assert pd.isna(target.iloc[3])    # last row is NaN

    def test_last_horizon_rows_are_nan(self):
        config = _make_config(prediction_horizon=5)
        pipe = MLPipeline(config)

        df = pd.DataFrame({"close": np.linspace(100, 110, 30)}, index=pd.date_range("2020-01-01", periods=30, freq="B"))
        target = pipe.prepare_target(df)

        assert target.iloc[-5:].isna().all()
        assert target.iloc[:-5].notna().all()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class TestTrain:
    def test_train_produces_model(self):
        """Training on synthetic data produces a usable model."""
        config = _make_config(min_training_samples=100)
        pipe = MLPipeline(config)
        features, target = _synthetic_features_and_target(n_rows=600)

        metrics = pipe.train(features, target)

        assert pipe.is_trained
        assert "accuracy" in metrics
        assert "log_loss" in metrics
        assert metrics["n_samples"] == 600
        assert metrics["n_features"] == 10
        assert 0.0 <= metrics["accuracy"] <= 1.0

    def test_train_insufficient_samples_raises(self):
        """Training with fewer than min_training_samples raises ValueError."""
        config = _make_config(min_training_samples=500)
        pipe = MLPipeline(config)
        features, target = _synthetic_features_and_target(n_rows=100)

        with pytest.raises(ValueError, match="Insufficient training samples"):
            pipe.train(features, target)


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

class TestPredict:
    def test_predict_returns_probabilities(self):
        """Predictions include class probabilities summing to ~1.0."""
        config = _make_config(min_training_samples=100)
        pipe = MLPipeline(config)
        features, target = _synthetic_features_and_target(n_rows=600)
        pipe.train(features, target)

        result = pipe.predict(features.iloc[:10])

        assert set(result.columns) == {"pred_class", "prob_down", "prob_flat", "prob_up"}
        assert len(result) == 10
        row_sums = result[["prob_down", "prob_flat", "prob_up"]].sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_predict_fails_without_training(self):
        pipe = MLPipeline()
        features, _ = _synthetic_features_and_target(n_rows=10)
        with pytest.raises(RuntimeError, match="not trained"):
            pipe.predict(features)

    def test_predict_fails_on_feature_mismatch(self):
        """Predict raises if feature columns don't match training."""
        config = _make_config(min_training_samples=100)
        pipe = MLPipeline(config)
        features, target = _synthetic_features_and_target(n_rows=600, n_features=10)
        pipe.train(features, target)

        bad_features = features.rename(columns={"feat_0": "wrong_name"})
        with pytest.raises(ValueError, match="Feature mismatch"):
            pipe.predict(bad_features)


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

class TestFeatureImportance:
    def test_feature_importance_has_all_names(self):
        config = _make_config(min_training_samples=100)
        pipe = MLPipeline(config)
        features, target = _synthetic_features_and_target(n_rows=600, n_features=10)
        pipe.train(features, target)

        importance = pipe.feature_importance()

        assert set(importance.keys()) == set(features.columns)
        assert all(isinstance(v, float) for v in importance.values())


# ---------------------------------------------------------------------------
# Save / Load roundtrip
# ---------------------------------------------------------------------------

class TestSaveLoad:
    def test_save_load_roundtrip(self, tmp_path):
        """Train, save, load, predict — results should be identical."""
        config = _make_config(min_training_samples=100)
        pipe = MLPipeline(config)
        features, target = _synthetic_features_and_target(n_rows=600)
        pipe.train(features, target)

        test_input = features.iloc[:5]
        original_preds = pipe.predict(test_input)

        model_path = tmp_path / "model.joblib"
        pipe.save_model(model_path)

        pipe2 = MLPipeline()
        pipe2.load_model(model_path)
        loaded_preds = pipe2.predict(test_input)

        pd.testing.assert_frame_equal(original_preds, loaded_preds)

    def test_save_fails_without_model(self, tmp_path):
        pipe = MLPipeline()
        with pytest.raises(RuntimeError, match="not trained"):
            pipe.save_model(tmp_path / "model.joblib")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestMLConfig:
    def test_defaults(self):
        config = MLConfig()
        assert config.prediction_horizon == 5
        assert config.up_threshold == 0.01
        assert config.down_threshold == -0.01
        assert config.min_training_samples == 500
        assert config.classification_labels == {0: "DOWN", 1: "FLAT", 2: "UP"}

    def test_from_settings(self):
        """from_settings extracts ML fields from Settings object."""
        from unittest.mock import MagicMock

        mock_settings = MagicMock()
        mock_settings.ml.prediction_horizon = 10
        mock_settings.ml.up_threshold = 0.02
        mock_settings.ml.down_threshold = -0.02
        mock_settings.ml.min_training_samples = 1000

        config = MLConfig.from_settings(mock_settings)

        assert config.prediction_horizon == 10
        assert config.up_threshold == 0.02
        assert config.min_training_samples == 1000
