"""Confidence calibration for XGBoost probability outputs."""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression

logger = logging.getLogger(__name__)


class ConfidenceCalibrator:
    """Calibrate raw XGBoost probabilities using isotonic regression or Platt scaling."""

    def __init__(self, method: str = "isotonic") -> None:
        if method not in ("isotonic", "platt"):
            raise ValueError(f"Unknown calibration method: {method}")
        self.method = method
        self._calibrators: list | None = None
        self._fitted = False

    def fit(self, y_true: np.ndarray, y_proba: np.ndarray) -> None:
        """Fit calibration on a validation set.

        Args:
            y_true: 1-D array of true class labels (0, 1, 2).
            y_proba: 2-D array of shape (n_samples, n_classes) with raw probabilities.
        """
        n_classes = y_proba.shape[1]
        self._calibrators = []

        for cls in range(n_classes):
            binary_target = (y_true == cls).astype(float)
            raw_prob = y_proba[:, cls]

            if self.method == "isotonic":
                cal = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                cal.fit(raw_prob, binary_target)
            else:  # platt
                from sklearn.linear_model import LogisticRegression

                lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
                lr.fit(raw_prob.reshape(-1, 1), binary_target)
                cal = lr

            self._calibrators.append(cal)

        self._fitted = True
        logger.info("Calibrator fitted with method=%s, n_classes=%d", self.method, n_classes)

    def calibrate(self, y_proba: np.ndarray) -> np.ndarray:
        """Return calibrated probabilities.

        Args:
            y_proba: 2-D array of shape (n_samples, n_classes).

        Returns:
            Calibrated probabilities, same shape. If not fitted, returns input unchanged.
        """
        if not self._fitted or self._calibrators is None:
            return y_proba

        n_samples, n_classes = y_proba.shape
        calibrated = np.zeros_like(y_proba)

        for cls in range(n_classes):
            raw_prob = y_proba[:, cls]
            cal = self._calibrators[cls]

            if self.method == "isotonic":
                calibrated[:, cls] = cal.predict(raw_prob)
            else:  # platt
                calibrated[:, cls] = cal.predict_proba(raw_prob.reshape(-1, 1))[:, 1]

        # Renormalize rows to sum to 1
        row_sums = calibrated.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1.0, row_sums)
        calibrated = calibrated / row_sums

        return calibrated

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"method": self.method, "calibrators": self._calibrators, "fitted": self._fitted},
            path,
        )

    def load(self, path: str | Path) -> None:
        artifact = joblib.load(Path(path))
        self.method = artifact["method"]
        self._calibrators = artifact["calibrators"]
        self._fitted = artifact["fitted"]
