"""ML model monitoring: prediction tracking, feature drift (PSI), concept drift."""
from __future__ import annotations

from collections import deque
from datetime import UTC as _UTC
from datetime import datetime

import numpy as np
import pandas as pd


class ModelMonitor:
    """Track ML model predictions vs actuals, detect drift."""

    _MAX_PREDICTIONS = 10_000

    def __init__(
        self,
        window_size: int = 100,
        n_psi_bins: int = 10,
        psi_threshold: float = 0.25,
        accuracy_threshold: float = 0.40,
        max_degraded_windows: int = 5,
    ):
        self._predictions: deque[dict] = deque(maxlen=self._MAX_PREDICTIONS)
        self._window_size = window_size
        self._n_psi_bins = n_psi_bins
        self._psi_threshold = psi_threshold
        self._accuracy_threshold = accuracy_threshold
        self._max_degraded_windows = max_degraded_windows
        self._degraded_window_count = 0
        self._fallback_active = False
        self._reference_distributions: dict[str, np.ndarray] | None = None
        self._reference_bin_edges: dict[str, np.ndarray] | None = None
        self._last_retrain_time: datetime | None = None

    def record_prediction(
        self,
        symbol: str,
        pred_class: int,
        proba: np.ndarray,
        timestamp: datetime,
    ) -> None:
        """Record a prediction for later comparison with actuals."""
        self._predictions.append({
            "symbol": symbol,
            "timestamp": timestamp,
            "pred_class": pred_class,
            "proba": np.asarray(proba, dtype=float),
            "actual": None,
        })

    def record_actual(
        self, symbol: str, timestamp: datetime, actual_class: int
    ) -> None:
        """Record actual outcome to compare with earlier prediction."""
        for entry in reversed(self._predictions):
            if entry["symbol"] == symbol and entry["timestamp"] == timestamp:
                entry["actual"] = actual_class
                return

    def set_reference_distribution(self, features: pd.DataFrame) -> None:
        """Set reference feature distribution from training data for PSI."""
        self._reference_distributions = {}
        self._reference_bin_edges = {}
        for col in features.columns:
            vals = features[col].dropna().values.astype(float)
            if len(vals) < self._n_psi_bins:
                continue
            # Compute quantile bin edges from reference data
            edges = np.quantile(vals, np.linspace(0, 1, self._n_psi_bins + 1))
            # Deduplicate edges to avoid zero-width bins
            edges = np.unique(edges)
            if len(edges) < 2:
                continue
            counts = np.histogram(vals, bins=edges)[0].astype(float)
            self._reference_distributions[col] = counts / counts.sum()
            self._reference_bin_edges[col] = edges

    def compute_psi(self, current_features: pd.DataFrame) -> dict[str, float]:
        """Population Stability Index per feature.

        PSI = sum((actual_pct - expected_pct) * ln(actual_pct / expected_pct))
        PSI < 0.1 = no shift, 0.1-0.25 = moderate, > 0.25 = significant
        """
        if self._reference_distributions is None or self._reference_bin_edges is None:
            return {}

        eps = 1e-6
        result: dict[str, float] = {}
        for col, ref_pct in self._reference_distributions.items():
            if col not in current_features.columns:
                continue
            vals = current_features[col].dropna().values.astype(float)
            if len(vals) == 0:
                continue
            edges = self._reference_bin_edges[col]
            counts = np.histogram(vals, bins=edges)[0].astype(float)
            total = counts.sum()
            if total == 0:
                continue
            cur_pct = counts / total

            # Add epsilon to avoid log(0)
            ref_safe = np.clip(ref_pct, eps, None)
            cur_safe = np.clip(cur_pct, eps, None)
            psi = float(np.sum((cur_safe - ref_safe) * np.log(cur_safe / ref_safe)))
            result[col] = psi
        return result

    def rolling_accuracy(self) -> float:
        """Compute accuracy over the last window_size predictions that have actuals."""
        resolved = [
            p for p in self._predictions if p["actual"] is not None
        ]
        if not resolved:
            return 0.0
        window = resolved[-self._window_size :]
        correct = sum(1 for p in window if p["pred_class"] == p["actual"])
        return correct / len(window)

    def check_drift(
        self, current_features: pd.DataFrame | None = None
    ) -> dict:
        """Run all drift checks, return status dict."""
        accuracy = self.rolling_accuracy()
        psi_features: dict[str, float] = {}
        psi_max = 0.0

        if current_features is not None:
            psi_features = self.compute_psi(current_features)
            if psi_features:
                psi_max = max(psi_features.values())

        # Concept drift: accuracy below threshold (only if we have resolved predictions)
        has_resolved = any(p["actual"] is not None for p in self._predictions)
        if has_resolved and accuracy < self._accuracy_threshold:
            self._degraded_window_count += 1
        elif not has_resolved or accuracy >= self._accuracy_threshold:
            self._degraded_window_count = max(0, self._degraded_window_count - 1)

        # Feature drift can also trigger degradation
        if psi_max > self._psi_threshold:
            self._degraded_window_count += 1

        fallback_recommended = (
            self._degraded_window_count >= self._max_degraded_windows
        )
        if fallback_recommended:
            self._fallback_active = True

        if self._fallback_active:
            status = "critical"
        elif self._degraded_window_count > 0:
            status = "warning"
        else:
            status = "ok"

        return {
            "accuracy": accuracy,
            "psi_max": psi_max,
            "psi_features": psi_features,
            "degraded_windows": self._degraded_window_count,
            "fallback_recommended": fallback_recommended,
            "status": status,
        }

    def reset_after_retrain(self) -> None:
        """Reset counters after successful model retrain."""
        self._degraded_window_count = 0
        self._fallback_active = False
        self._last_retrain_time = datetime.now(tz=_UTC)

    def get_metrics(self) -> dict:
        """Return metrics dict for Prometheus export."""
        accuracy = self.rolling_accuracy()
        resolved_count = sum(
            1 for p in self._predictions if p["actual"] is not None
        )
        staleness_hours = None
        if self._last_retrain_time is not None:
            delta = datetime.now(tz=_UTC) - self._last_retrain_time
            staleness_hours = delta.total_seconds() / 3600.0

        return {
            "accuracy": accuracy,
            "total_predictions": len(self._predictions),
            "resolved_predictions": resolved_count,
            "degraded_windows": self._degraded_window_count,
            "fallback_active": self._fallback_active,
            "staleness_hours": staleness_hours,
        }
