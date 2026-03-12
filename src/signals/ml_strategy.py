"""XGBoost ML signal strategy implementing BaseStrategy."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, Signal, SignalDirection
from src.signals.confidence import ConfidenceCalibrator
from src.signals.feature_store import FeatureStore
from src.signals.ml.config import MLConfig
from src.signals.ml.pipeline import MLPipeline

logger = logging.getLogger(__name__)


class MLSignalStrategy(BaseStrategy):
    """XGBoost ML signal strategy using 50+ technical, fundamental, and alternative features."""

    def __init__(
        self,
        model_path: str = "models/xgboost_signal.joblib",
        feature_store: FeatureStore | None = None,
        calibrator: ConfidenceCalibrator | None = None,
        config: MLConfig | None = None,
    ) -> None:
        self._config = config or MLConfig()
        self._pipeline = MLPipeline(config=self._config)
        self._feature_store = feature_store or FeatureStore()
        self._calibrator = calibrator
        self._model_path = model_path
        self._model_loaded_at: datetime | None = None

        if Path(model_path).exists():
            self._pipeline.load_model(model_path)
            self._model_loaded_at = datetime.now(UTC)

    @property
    def name(self) -> str:
        return "ml_xgboost_signal"

    @property
    def description(self) -> str:
        return "XGBoost ML signal strategy using 50+ features"

    @property
    def min_hold_days(self) -> int:
        return 3

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        if not self._pipeline.is_trained or self._is_model_stale():
            return self._fallback_flat_signals(data)

        signals: list[Signal] = []
        for symbol, bars in data.items():
            if not bars:
                continue

            features = self._feature_store.compute_features(
                symbol=symbol,
                bars=bars,
                spy_bars=data.get("SPY", []),
            )
            if features.empty:
                continue

            latest_features = features.iloc[[-1]].drop(columns=["symbol"], errors="ignore")
            latest_features = latest_features.dropna(axis=1, how="all")

            try:
                pred_df = self._pipeline.predict(latest_features)
            except (ValueError, RuntimeError):
                continue

            pred_class = int(pred_df["pred_class"].iloc[0])
            proba = pred_df[["prob_down", "prob_flat", "prob_up"]].iloc[0].values

            if self._calibrator:
                proba = self._calibrator.calibrate(proba.reshape(1, -1))[0]

            direction, strength = self._map_prediction(pred_class, proba)

            if strength < self._config.confidence_threshold:
                direction = SignalDirection.FLAT

            try:
                importance = self._pipeline.feature_importance()
                top5 = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:5])
            except RuntimeError:
                top5 = {}

            signals.append(Signal(
                symbol=symbol,
                timestamp=bars[-1].timestamp,
                direction=direction,
                strength=min(max(strength, 0.0), 1.0),
                strategy_name=self.name,
                metadata={
                    "pred_class": pred_class,
                    "prob_down": float(proba[0]),
                    "prob_flat": float(proba[1]),
                    "prob_up": float(proba[2]),
                    "top_features": top5,
                    "model_stale": False,
                },
            ))

        return signals

    def get_parameters(self) -> dict[str, Any]:
        return {
            "model_path": self._model_path,
            "prediction_horizon": self._config.prediction_horizon,
            "confidence_threshold": self._config.confidence_threshold,
            "model_staleness_days": self._config.model_staleness_days,
            "up_threshold": self._config.up_threshold,
            "down_threshold": self._config.down_threshold,
        }

    def get_required_data(self) -> list[str]:
        return ["ohlcv", "fundamentals", "insider_transactions", "short_interest"]

    def _map_prediction(
        self, pred_class: int, proba: np.ndarray
    ) -> tuple[SignalDirection, float]:
        if pred_class == 2:  # UP
            return SignalDirection.LONG, float(proba[2])
        elif pred_class == 0:  # DOWN
            return SignalDirection.SHORT, float(proba[0])
        else:  # FLAT
            return SignalDirection.FLAT, float(proba[1])

    def _is_model_stale(self) -> bool:
        if self._model_loaded_at is None:
            return True
        age = (datetime.now(UTC) - self._model_loaded_at).days
        return age > self._config.model_staleness_days

    def _fallback_flat_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, bars in data.items():
            if bars:
                signals.append(Signal(
                    symbol=symbol,
                    timestamp=bars[-1].timestamp,
                    direction=SignalDirection.FLAT,
                    strength=0.0,
                    strategy_name=self.name,
                    metadata={
                        "fallback": True,
                        "model_stale": True,
                        "reason": "Model not loaded or stale",
                    },
                ))
        return signals
