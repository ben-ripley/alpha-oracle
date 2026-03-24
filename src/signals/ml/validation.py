"""Walk-forward validation with Optuna hyperparameter tuning."""
from __future__ import annotations

import numpy as np
import pandas as pd
import structlog

from src.signals.ml.config import MLConfig
from src.signals.ml.metrics import (
    directional_accuracy,
    log_loss_score,
    profit_weighted_accuracy,
    signal_max_drawdown,
)
from src.signals.ml.pipeline import MLPipeline

logger = structlog.get_logger(__name__)


class WalkForwardValidator:
    """ML walk-forward validation with Optuna hyperparameter tuning."""

    def __init__(
        self,
        pipeline: MLPipeline | None = None,
        config: MLConfig | None = None,
        holdout_pct: float = 0.20,
        max_optuna_trials: int = 50,
    ) -> None:
        self.config = config or MLConfig()
        self.pipeline = pipeline or MLPipeline(config=self.config)
        self.holdout_pct = holdout_pct
        self.max_optuna_trials = max_optuna_trials

    def validate(
        self,
        features: pd.DataFrame,
        target: pd.Series,
        close_prices: pd.Series | None = None,
        window_mode: str = "expanding",
        train_size: int = 252 * 2,
        test_size: int = 63,
        step_size: int = 63,
    ) -> dict:
        """Run walk-forward validation.

        1. Reserve last holdout_pct as untouched holdout
        2. Split remaining into train/test windows
        3. For each window: optionally tune with Optuna, train, predict, collect metrics
        4. Return aggregate results
        """
        n_samples = len(features)
        holdout_size = int(n_samples * self.holdout_pct)

        windows = self._create_windows(
            n_samples=n_samples,
            holdout_size=holdout_size,
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            mode=window_mode,
        )

        if not windows:
            raise ValueError(
                f"Not enough data for walk-forward: {n_samples} samples, "
                f"need at least {train_size + test_size + holdout_size}"
            )

        all_window_results: list[dict] = []
        all_oos_preds: list[int] = []
        all_oos_true: list[int] = []
        all_oos_proba: list[np.ndarray] = []
        all_oos_returns: list[float] = []
        best_params: dict = {}
        best_log_loss = float("inf")

        for i, (train_idx, test_idx) in enumerate(windows):
            logger.info(
                "walk_forward_window",
                window=i,
                train_start=train_idx[0],
                train_end=train_idx[-1],
                test_start=test_idx[0],
                test_end=test_idx[-1],
            )

            train_features = features.iloc[list(train_idx)]
            train_target = target.iloc[list(train_idx)]
            test_features = features.iloc[list(test_idx)]
            test_target = target.iloc[list(test_idx)]

            # Optuna tuning on training data
            if self.max_optuna_trials > 0:
                window_params = self._tune_hyperparams(
                    features, target, train_idx, n_trials=self.max_optuna_trials
                )
            else:
                window_params = {}

            # Create a fresh pipeline with tuned params
            window_pipeline = MLPipeline(config=self.config)
            if window_params:
                window_pipeline._model = None  # ensure fresh

            # Train
            _apply_params(window_pipeline, window_params)
            train_metrics = window_pipeline.train(train_features, train_target)

            # Predict on test
            pred_df = window_pipeline.predict(test_features)
            preds = pred_df["pred_class"].values
            proba = pred_df[["prob_down", "prob_flat", "prob_up"]].values

            # Drop NaN targets from test evaluation
            valid_mask = test_target.notna()
            y_true = test_target[valid_mask].astype(int).values
            y_pred = preds[valid_mask.values]
            y_proba = proba[valid_mask.values]

            window_da = directional_accuracy(y_true, y_pred)
            window_ll = log_loss_score(y_true, y_proba) if len(y_true) > 0 else float("inf")

            # Track returns if close prices provided
            window_returns: list[float] = []
            if close_prices is not None:
                test_close = close_prices.iloc[list(test_idx)]
                rets = test_close.pct_change().fillna(0.0).values
                window_returns = rets[valid_mask.values].tolist()

            window_result = {
                "window": i,
                "train_idx": (train_idx[0], train_idx[-1]),
                "test_idx": (test_idx[0], test_idx[-1]),
                "train_metrics": train_metrics,
                "directional_accuracy": window_da,
                "log_loss": window_ll,
                "n_test_samples": len(y_true),
                "params": window_params,
            }
            all_window_results.append(window_result)

            all_oos_preds.extend(y_pred.tolist())
            all_oos_true.extend(y_true.tolist())
            all_oos_proba.extend(y_proba.tolist())
            all_oos_returns.extend(window_returns)

            if window_ll < best_log_loss:
                best_log_loss = window_ll
                best_params = window_params

        # Aggregate OOS metrics
        oos_true = np.array(all_oos_true)
        oos_preds = np.array(all_oos_preds)
        oos_proba = np.array(all_oos_proba)
        oos_returns = np.array(all_oos_returns) if all_oos_returns else np.array([])

        aggregate = {
            "directional_accuracy": directional_accuracy(oos_true, oos_preds),
            "log_loss": log_loss_score(oos_true, oos_proba) if len(oos_true) > 0 else None,
            "n_total_oos_samples": len(oos_true),
            "n_windows": len(windows),
        }

        if len(oos_returns) > 0:
            pwa = profit_weighted_accuracy(oos_true, oos_preds, oos_returns)
            aggregate["profit_weighted_accuracy"] = pwa

            # Simulated PnL: go long on UP predictions, short on DOWN, flat on FLAT
            signal_returns = np.where(
                oos_preds == 2, oos_returns,
                np.where(oos_preds == 0, -oos_returns, 0.0),
            )
            cum_returns = np.cumprod(1.0 + signal_returns)
            aggregate["simulated_pnl"] = float(cum_returns[-1] - 1.0) if len(cum_returns) > 0 else 0.0
            aggregate["max_drawdown"] = signal_max_drawdown(cum_returns)

        # Holdout evaluation
        holdout_metrics: dict | None = None
        if holdout_size > 0:
            holdout_start = n_samples - holdout_size
            holdout_features = features.iloc[holdout_start:]
            holdout_target = target.iloc[holdout_start:]
            holdout_valid = holdout_target.notna()

            if holdout_valid.sum() >= self.config.min_training_samples // 2:
                # Train final model on all non-holdout data with best params
                all_train_features = features.iloc[:holdout_start]
                all_train_target = target.iloc[:holdout_start]

                final_pipeline = MLPipeline(config=self.config)
                _apply_params(final_pipeline, best_params)
                final_pipeline.train(all_train_features, all_train_target)

                holdout_pred_df = final_pipeline.predict(holdout_features)
                h_preds = holdout_pred_df["pred_class"].values
                h_proba = holdout_pred_df[["prob_down", "prob_flat", "prob_up"]].values

                h_true = holdout_target[holdout_valid].astype(int).values
                h_pred = h_preds[holdout_valid.values]
                h_proba_valid = h_proba[holdout_valid.values]

                holdout_metrics = {
                    "directional_accuracy": directional_accuracy(h_true, h_pred),
                    "log_loss": log_loss_score(h_true, h_proba_valid),
                    "n_samples": len(h_true),
                }

        return {
            "windows": all_window_results,
            "aggregate": aggregate,
            "holdout_metrics": holdout_metrics,
            "best_params": best_params,
        }

    def _create_windows(
        self,
        n_samples: int,
        holdout_size: int,
        train_size: int,
        test_size: int,
        step_size: int,
        mode: str,
    ) -> list[tuple[range, range]]:
        """Create (train_idx, test_idx) pairs. No overlap between train and test."""
        usable = n_samples - holdout_size
        windows: list[tuple[range, range]] = []

        if mode == "expanding":
            # First window starts at 0, train_size samples
            test_start = train_size
            while test_start + test_size <= usable:
                train_idx = range(0, test_start)
                test_idx = range(test_start, test_start + test_size)
                windows.append((train_idx, test_idx))
                test_start += step_size
        elif mode == "rolling":
            test_start = train_size
            while test_start + test_size <= usable:
                train_start = test_start - train_size
                train_idx = range(train_start, test_start)
                test_idx = range(test_start, test_start + test_size)
                windows.append((train_idx, test_idx))
                test_start += step_size
        else:
            raise ValueError(f"Unknown window_mode: {mode}. Use 'expanding' or 'rolling'.")

        return windows

    def _tune_hyperparams(
        self,
        features: pd.DataFrame,
        target: pd.Series,
        train_idx: range,
        n_trials: int,
    ) -> dict:
        """Use Optuna to find best XGBoost params on training data using CV.

        Optimize for log_loss on 3-fold time-series CV within the training window.
        """
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        train_features = features.iloc[list(train_idx)]
        train_target = target.iloc[list(train_idx)]

        # Drop NaN targets
        valid = train_target.notna()
        X = train_features[valid].values
        y = train_target[valid].astype(int).values

        n = len(X)
        # 3-fold time-series CV splits
        fold_size = n // 4
        cv_splits = []
        for k in range(3):
            cv_train_end = fold_size * (k + 1)
            cv_test_start = cv_train_end
            cv_test_end = min(cv_test_start + fold_size, n)
            if cv_test_end > cv_test_start:
                cv_splits.append(
                    (np.arange(0, cv_train_end), np.arange(cv_test_start, cv_test_end))
                )

        if not cv_splits:
            return {}

        def objective(trial: optuna.Trial) -> float:
            from sklearn.metrics import log_loss as sk_log_loss
            from xgboost import XGBClassifier

            params = {
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            }

            scores = []
            for cv_train_idx, cv_test_idx in cv_splits:
                model = XGBClassifier(
                    **params,
                    objective="multi:softprob",
                    num_class=3,
                    eval_metric="mlogloss",
                    random_state=42,
                    verbosity=0,
                )
                model.fit(X[cv_train_idx], y[cv_train_idx])
                proba = model.predict_proba(X[cv_test_idx])
                # Ensure all 3 classes present in labels for log_loss
                scores.append(sk_log_loss(y[cv_test_idx], proba, labels=[0, 1, 2]))

            return float(np.mean(scores))

        study = optuna.create_study(direction="minimize")
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        logger.info(
            "optuna_tuning_complete",
            best_value=study.best_value,
            best_params=study.best_params,
            n_trials=len(study.trials),
        )

        return study.best_params


def _apply_params(pipeline: MLPipeline, params: dict) -> None:
    """Override default XGBoost params on a pipeline before training.

    We monkey-patch the train method to inject tuned params. This avoids
    modifying the MLPipeline class itself.
    """
    if not params:
        return

    def patched_train(features: pd.DataFrame, target: pd.Series) -> dict:
        from xgboost import XGBClassifier

        mask = target.notna()
        X = features.loc[mask]
        y = target.loc[mask].astype(int)

        if len(X) < pipeline.config.min_training_samples:
            raise ValueError(
                f"Insufficient training samples: {len(X)} < {pipeline.config.min_training_samples}"
            )

        pipeline._feature_names = list(X.columns)

        class_counts = y.value_counts()
        total = len(y)
        weights = y.map(lambda c: total / (len(class_counts) * class_counts[c]))

        xgb_params = {
            "n_estimators": params.get("n_estimators", 300),
            "max_depth": params.get("max_depth", 6),
            "learning_rate": params.get("learning_rate", 0.05),
            "subsample": params.get("subsample", 0.8),
            "colsample_bytree": params.get("colsample_bytree", 0.8),
            "min_child_weight": params.get("min_child_weight", 5),
            "objective": "multi:softprob",
            "num_class": 3,
            "eval_metric": "mlogloss",
            "random_state": 42,
            "verbosity": 0,
        }

        pipeline._model = XGBClassifier(**xgb_params)
        pipeline._model.fit(X, y, sample_weight=weights)

        from sklearn.metrics import accuracy_score, log_loss

        preds = pipeline._model.predict(X)
        proba = pipeline._model.predict_proba(X)

        return {
            "accuracy": float(accuracy_score(y, preds)),
            "log_loss": float(log_loss(y, proba, labels=[0, 1, 2])),
            "class_distribution": {int(k): int(v) for k, v in class_counts.items()},
            "n_samples": len(X),
            "n_features": len(pipeline._feature_names),
        }

    pipeline.train = patched_train
