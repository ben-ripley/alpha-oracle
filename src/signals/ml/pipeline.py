"""XGBoost training pipeline for stock signal generation."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import structlog
from sklearn.metrics import accuracy_score, log_loss
from xgboost import XGBClassifier

from src.signals.ml.config import MLConfig

logger = structlog.get_logger(__name__)


class MLPipeline:
    """XGBoost training pipeline for stock signal generation."""

    def __init__(self, config: MLConfig | None = None) -> None:
        self.config = config or MLConfig()
        self._model: XGBClassifier | None = None
        self._feature_names: list[str] = []

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def prepare_target(self, df: pd.DataFrame, close_col: str = "close") -> pd.Series:
        """Create classification target from forward returns.

        Target at time T uses returns from T+1 to T+prediction_horizon.
        Labels: 0=DOWN (return < down_threshold), 1=FLAT, 2=UP (return > up_threshold)
        """
        horizon = self.config.prediction_horizon
        close = df[close_col]
        forward_return = (close.shift(-horizon) - close) / close

        target = pd.Series(1, index=df.index, dtype=int)  # default FLAT
        target[forward_return > self.config.up_threshold] = 2   # UP
        target[forward_return < self.config.down_threshold] = 0  # DOWN

        # Drop last `horizon` rows where forward return is NaN
        target.iloc[-horizon:] = np.nan
        return target

    def train(self, features: pd.DataFrame, target: pd.Series) -> dict:
        """Train XGBoost model on feature matrix + target.

        Args:
            features: DataFrame with feature columns (no target, no close price)
            target: Series with 0/1/2 labels aligned to features index

        Returns:
            Training metrics dict (accuracy, log_loss, class_distribution)
        """
        # Align and drop NaN
        mask = target.notna()
        X = features.loc[mask]
        y = target.loc[mask].astype(int)

        if len(X) < self.config.min_training_samples:
            raise ValueError(
                f"Insufficient training samples: {len(X)} < {self.config.min_training_samples}"
            )

        self._feature_names = list(X.columns)

        # Compute sample weights for class imbalance
        class_counts = y.value_counts()
        total = len(y)
        weights = y.map(lambda c: total / (len(class_counts) * class_counts[c]))

        self._model = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=5,
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            random_state=42,
            verbosity=0,
        )
        self._model.fit(X, y, sample_weight=weights)

        # Compute training metrics
        preds = self._model.predict(X)
        proba = self._model.predict_proba(X)

        metrics = {
            "accuracy": float(accuracy_score(y, preds)),
            "log_loss": float(log_loss(y, proba, labels=[0, 1, 2])),
            "class_distribution": {
                int(k): int(v) for k, v in class_counts.items()
            },
            "n_samples": len(X),
            "n_features": len(self._feature_names),
        }

        logger.info(
            "model_trained",
            accuracy=metrics["accuracy"],
            log_loss=metrics["log_loss"],
            n_samples=metrics["n_samples"],
        )
        return metrics

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        """Generate predictions with class probabilities.

        Returns DataFrame with columns: pred_class, prob_down, prob_flat, prob_up
        """
        if self._model is None:
            raise RuntimeError("Model not trained or loaded")

        missing = set(self._feature_names) - set(features.columns)
        extra = set(features.columns) - set(self._feature_names)
        if missing or extra:
            raise ValueError(
                f"Feature mismatch. Missing: {missing}, Extra: {extra}"
            )

        X = features[self._feature_names]
        proba = self._model.predict_proba(X)
        preds = self._model.predict(X)

        return pd.DataFrame(
            {
                "pred_class": preds.astype(int),
                "prob_down": proba[:, 0],
                "prob_flat": proba[:, 1],
                "prob_up": proba[:, 2],
            },
            index=features.index,
        )

    def feature_importance(self) -> dict[str, float]:
        """Return feature name -> importance score dict."""
        if self._model is None:
            raise RuntimeError("Model not trained or loaded")
        scores = self._model.feature_importances_
        return dict(zip(self._feature_names, [float(s) for s in scores]))

    def save_model(self, path: str | Path) -> None:
        """Save model + feature names to disk using joblib."""
        if self._model is None:
            raise RuntimeError("Model not trained or loaded")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact = {
            "model": self._model,
            "feature_names": self._feature_names,
            "config": self.config,
        }
        joblib.dump(artifact, path)
        logger.info("model_saved", path=str(path))

    def load_model(self, path: str | Path) -> None:
        """Load model + feature names from disk."""
        path = Path(path)
        artifact = joblib.load(path)
        self._model = artifact["model"]
        self._feature_names = artifact["feature_names"]
        self.config = artifact.get("config", self.config)
        logger.info("model_loaded", path=str(path))
