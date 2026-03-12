"""Model version registry backed by Redis."""
from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class ModelVersion:
    """Metadata for a saved model version."""

    def __init__(
        self,
        version_id: str,
        path: str,
        metrics: dict,
        created_at: datetime,
        is_active: bool = False,
    ):
        self.version_id = version_id
        self.path = path
        self.metrics = metrics
        self.created_at = created_at
        self.is_active = is_active

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "path": self.path,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ModelVersion:
        return cls(
            version_id=d["version_id"],
            path=d["path"],
            metrics=d["metrics"],
            created_at=datetime.fromisoformat(d["created_at"]),
            is_active=d.get("is_active", False),
        )


class ModelRegistry:
    """Track model versions, metrics, promote/rollback."""

    def __init__(self, models_dir: str = "models", redis=None):
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._redis = redis
        self._versions: list[ModelVersion] = []

    def register(self, version_id: str, model_path: str, metrics: dict) -> ModelVersion:
        """Register a new model version."""
        version = ModelVersion(
            version_id=version_id,
            path=model_path,
            metrics=metrics,
            created_at=datetime.now(UTC),
        )
        self._versions.append(version)
        logger.info("model.registered", version=version_id, metrics=metrics)
        return version

    def get_active(self) -> ModelVersion | None:
        """Get the currently active model version."""
        for v in reversed(self._versions):
            if v.is_active:
                return v
        return None

    def promote(self, version_id: str) -> bool:
        """Promote a version to active, deactivating others."""
        found = False
        for v in self._versions:
            if v.version_id == version_id:
                v.is_active = True
                found = True
            else:
                v.is_active = False
        if found:
            logger.info("model.promoted", version=version_id)
        return found

    def should_promote(self, new_metrics: dict, current_metrics: dict | None) -> bool:
        """Check if new model should replace current.
        New model must have higher Sharpe on walk-forward validation."""
        if current_metrics is None:
            return True
        new_sharpe = new_metrics.get("sharpe_ratio", 0)
        current_sharpe = current_metrics.get("sharpe_ratio", 0)
        return new_sharpe > current_sharpe

    def list_versions(self) -> list[dict]:
        return [v.to_dict() for v in self._versions]

    def rollback(self) -> bool:
        """Rollback to previous active version."""
        active_idx = None
        for i, v in enumerate(self._versions):
            if v.is_active:
                active_idx = i
                break
        if active_idx is None or active_idx == 0:
            return False
        self._versions[active_idx].is_active = False
        self._versions[active_idx - 1].is_active = True
        logger.info(
            "model.rollback", to_version=self._versions[active_idx - 1].version_id
        )
        return True
