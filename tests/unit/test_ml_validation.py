"""Tests for walk-forward validation and ML metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.signals.ml.config import MLConfig
from src.signals.ml.metrics import (
    directional_accuracy,
    log_loss_score,
    profit_weighted_accuracy,
    signal_max_drawdown,
)
from src.signals.ml.pipeline import MLPipeline
from src.signals.ml.validation import WalkForwardValidator, _apply_params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_dataset(n: int = 1200, n_features: int = 10, seed: int = 42):
    """Generate synthetic features + target for testing."""
    rng = np.random.RandomState(seed)
    X = pd.DataFrame(
        rng.randn(n, n_features),
        columns=[f"feat_{i}" for i in range(n_features)],
    )
    # Target: 0=DOWN, 1=FLAT, 2=UP — with a weak learnable pattern
    raw = X["feat_0"] + 0.5 * X["feat_1"] + rng.randn(n) * 0.5
    target = pd.Series(np.where(raw > 0.5, 2, np.where(raw < -0.5, 0, 1)))
    close = pd.Series(100.0 + np.cumsum(rng.randn(n) * 0.5))
    return X, target, close


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

class TestDirectionalAccuracy:
    def test_perfect(self):
        y = np.array([0, 1, 2, 0, 1])
        assert directional_accuracy(y, y) == 1.0

    def test_none_correct(self):
        y_true = np.array([0, 0, 0])
        y_pred = np.array([2, 2, 2])
        assert directional_accuracy(y_true, y_pred) == 0.0

    def test_partial(self):
        y_true = np.array([0, 1, 2, 0])
        y_pred = np.array([0, 1, 0, 2])
        assert directional_accuracy(y_true, y_pred) == 0.5

    def test_empty(self):
        assert directional_accuracy(np.array([]), np.array([])) == 0.0


class TestProfitWeightedAccuracy:
    def test_all_correct(self):
        y = np.array([0, 1, 2])
        returns = np.array([-0.02, 0.0, 0.03])
        # All correct: weighted sum = sum of abs returns
        assert profit_weighted_accuracy(y, y, returns) == pytest.approx(1.0)

    def test_weighted_by_magnitude(self):
        y_true = np.array([0, 2])
        y_pred = np.array([0, 0])  # second wrong
        returns = np.array([-0.01, 0.05])
        # correct weight = 0.01, total weight = 0.06
        assert profit_weighted_accuracy(y_true, y_pred, returns) == pytest.approx(0.01 / 0.06)

    def test_zero_returns(self):
        y = np.array([0, 1])
        returns = np.array([0.0, 0.0])
        assert profit_weighted_accuracy(y, y, returns) == 0.0


class TestSignalMaxDrawdown:
    def test_no_drawdown(self):
        cum = np.array([1.0, 1.01, 1.02, 1.03])
        assert signal_max_drawdown(cum) == 0.0

    def test_known_drawdown(self):
        cum = np.array([1.0, 1.1, 0.99, 1.05])
        # Peak 1.1 -> trough 0.99 = (1.1-0.99)/1.1 = 0.11/1.1 = 0.1
        assert signal_max_drawdown(cum) == pytest.approx(0.11 / 1.1, abs=1e-6)

    def test_single_value(self):
        assert signal_max_drawdown(np.array([1.0])) == 0.0


class TestLogLoss:
    def test_perfect_predictions(self):
        y_true = np.array([0, 1, 2])
        y_proba = np.array([
            [0.99, 0.005, 0.005],
            [0.005, 0.99, 0.005],
            [0.005, 0.005, 0.99],
        ])
        ll = log_loss_score(y_true, y_proba)
        assert ll < 0.1  # near-perfect should have very low loss

    def test_random_predictions(self):
        y_true = np.array([0, 1, 2])
        y_proba = np.array([
            [1/3, 1/3, 1/3],
            [1/3, 1/3, 1/3],
            [1/3, 1/3, 1/3],
        ])
        ll = log_loss_score(y_true, y_proba)
        assert ll == pytest.approx(np.log(3), abs=0.01)


# ---------------------------------------------------------------------------
# WalkForwardValidator tests
# ---------------------------------------------------------------------------

class TestWindowCreation:
    def test_expanding_windows_no_overlap(self):
        validator = WalkForwardValidator(max_optuna_trials=0)
        windows = validator._create_windows(
            n_samples=600, holdout_size=100, train_size=200,
            test_size=50, step_size=50, mode="expanding",
        )
        assert len(windows) > 0
        for train_idx, test_idx in windows:
            # No overlap
            train_set = set(train_idx)
            test_set = set(test_idx)
            assert train_set.isdisjoint(test_set)
            # Test comes after train
            assert min(test_idx) > max(train_idx)

    def test_rolling_windows_fixed_train_size(self):
        validator = WalkForwardValidator(max_optuna_trials=0)
        windows = validator._create_windows(
            n_samples=600, holdout_size=100, train_size=200,
            test_size=50, step_size=50, mode="rolling",
        )
        for train_idx, test_idx in windows:
            assert len(train_idx) == 200
            assert len(test_idx) == 50

    def test_holdout_excluded(self):
        validator = WalkForwardValidator(max_optuna_trials=0, holdout_pct=0.20)
        windows = validator._create_windows(
            n_samples=1000, holdout_size=200, train_size=300,
            test_size=100, step_size=100, mode="expanding",
        )
        holdout_start = 800
        for train_idx, test_idx in windows:
            assert max(test_idx) < holdout_start

    def test_invalid_mode_raises(self):
        validator = WalkForwardValidator(max_optuna_trials=0)
        with pytest.raises(ValueError, match="Unknown window_mode"):
            validator._create_windows(
                n_samples=600, holdout_size=100, train_size=200,
                test_size=50, step_size=50, mode="invalid",
            )


class TestWalkForwardValidation:
    def test_basic_validation_no_tuning(self):
        """Full walk-forward with no Optuna tuning (fast)."""
        X, target, close = _synthetic_dataset(n=1200)
        config = MLConfig(min_training_samples=50)
        validator = WalkForwardValidator(
            config=config, max_optuna_trials=0, holdout_pct=0.20,
        )

        results = validator.validate(
            features=X, target=target, close_prices=close,
            window_mode="expanding", train_size=400,
            test_size=100, step_size=100,
        )

        assert "windows" in results
        assert "aggregate" in results
        assert "holdout_metrics" in results
        assert "best_params" in results

        assert len(results["windows"]) > 0
        assert results["aggregate"]["n_windows"] == len(results["windows"])
        assert results["aggregate"]["n_total_oos_samples"] > 0

        # Directional accuracy should be better than random (> 0.25)
        # for a dataset with a learnable pattern
        assert results["aggregate"]["directional_accuracy"] > 0.25

    def test_training_data_never_includes_test(self):
        """Verify no data leakage between train and test windows."""
        X, target, _ = _synthetic_dataset(n=800)
        config = MLConfig(min_training_samples=50)
        validator = WalkForwardValidator(
            config=config, max_optuna_trials=0, holdout_pct=0.20,
        )

        windows = validator._create_windows(
            n_samples=800, holdout_size=160, train_size=300,
            test_size=60, step_size=60, mode="expanding",
        )

        for train_idx, test_idx in windows:
            train_set = set(train_idx)
            test_set = set(test_idx)
            assert len(train_set & test_set) == 0, "Train/test overlap detected!"

    def test_insufficient_data_raises(self):
        """Too little data should raise ValueError."""
        X, target, _ = _synthetic_dataset(n=100)
        config = MLConfig(min_training_samples=50)
        validator = WalkForwardValidator(
            config=config, max_optuna_trials=0, holdout_pct=0.20,
        )

        with pytest.raises(ValueError, match="Not enough data"):
            validator.validate(
                features=X, target=target,
                train_size=200, test_size=50, step_size=50,
            )

    def test_with_optuna_tuning(self):
        """Optuna tuning with very few trials for speed."""
        X, target, _ = _synthetic_dataset(n=1200)
        config = MLConfig(min_training_samples=50)
        validator = WalkForwardValidator(
            config=config, max_optuna_trials=3, holdout_pct=0.20,
        )

        results = validator.validate(
            features=X, target=target,
            window_mode="expanding", train_size=400,
            test_size=100, step_size=200,  # large step = fewer windows = faster
        )

        assert len(results["windows"]) > 0
        # With tuning, best_params should have some entries
        # (may be empty if no window completed tuning, but normally should be populated)
        assert results["aggregate"]["directional_accuracy"] > 0.0


class TestApplyParams:
    def test_patched_pipeline_trains(self):
        """_apply_params should create a trainable pipeline."""
        X, target, _ = _synthetic_dataset(n=600)
        config = MLConfig(min_training_samples=50)
        pipeline = MLPipeline(config=config)
        params = {"max_depth": 4, "learning_rate": 0.1, "n_estimators": 50}
        _apply_params(pipeline, params)

        metrics = pipeline.train(X, target)
        assert "accuracy" in metrics
        assert metrics["accuracy"] > 0.0

        preds = pipeline.predict(X)
        assert len(preds) == len(X)

    def test_empty_params_noop(self):
        """Empty params should not patch the pipeline."""
        import types

        config = MLConfig(min_training_samples=50)
        pipeline = MLPipeline(config=config)
        _apply_params(pipeline, {})
        # With empty params, train should still be the original bound method,
        # not a patched closure (which would be a plain function).
        assert isinstance(pipeline.train, types.MethodType)
