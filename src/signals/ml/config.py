"""ML pipeline configuration defaults."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MLConfig:
    """ML pipeline configuration defaults."""

    prediction_horizon: int = 5
    up_threshold: float = 0.01
    down_threshold: float = -0.01
    min_training_samples: int = 500
    confidence_threshold: float = 0.55
    model_staleness_days: int = 14
    classification_labels: dict[int, str] = field(default_factory=lambda: {0: "DOWN", 1: "FLAT", 2: "UP"})
    model_dir: str = "models"

    @classmethod
    def from_settings(cls, settings=None) -> MLConfig:
        """Create from app settings."""
        if settings is None:
            from src.core.config import get_settings

            settings = get_settings()
        ml = settings.ml
        return cls(
            prediction_horizon=ml.prediction_horizon,
            up_threshold=ml.up_threshold,
            down_threshold=ml.down_threshold,
            min_training_samples=ml.min_training_samples,
        )
