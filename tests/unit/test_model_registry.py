"""Tests for ModelRegistry."""
from __future__ import annotations

import pytest

from src.signals.ml.registry import ModelRegistry


@pytest.fixture
def registry(tmp_path):
    return ModelRegistry(models_dir=str(tmp_path / "models"))


class TestModelRegistry:
    def test_register_version(self, registry):
        v = registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        assert v.version_id == "v1"
        assert v.metrics == {"sharpe_ratio": 1.5}
        assert v.is_active is False

    def test_promote_makes_version_active(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        registry.register("v2", "models/v2.pkl", {"sharpe_ratio": 2.0})
        result = registry.promote("v2")
        assert result is True
        active = registry.get_active()
        assert active is not None
        assert active.version_id == "v2"

    def test_promote_deactivates_others(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        registry.register("v2", "models/v2.pkl", {"sharpe_ratio": 2.0})
        registry.promote("v1")
        registry.promote("v2")
        active = registry.get_active()
        assert active.version_id == "v2"
        # v1 should no longer be active
        v1 = [v for v in registry._versions if v.version_id == "v1"][0]
        assert v1.is_active is False

    def test_get_active_returns_none_when_no_active(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        assert registry.get_active() is None

    def test_should_promote_true_when_better_sharpe(self, registry):
        assert registry.should_promote(
            {"sharpe_ratio": 2.0}, {"sharpe_ratio": 1.5}
        ) is True

    def test_should_promote_true_when_no_current(self, registry):
        assert registry.should_promote({"sharpe_ratio": 1.0}, None) is True

    def test_should_promote_false_when_worse_sharpe(self, registry):
        assert registry.should_promote(
            {"sharpe_ratio": 1.0}, {"sharpe_ratio": 1.5}
        ) is False

    def test_should_promote_false_when_equal_sharpe(self, registry):
        assert registry.should_promote(
            {"sharpe_ratio": 1.5}, {"sharpe_ratio": 1.5}
        ) is False

    def test_rollback_to_previous(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        registry.register("v2", "models/v2.pkl", {"sharpe_ratio": 2.0})
        registry.promote("v2")
        result = registry.rollback()
        assert result is True
        active = registry.get_active()
        assert active.version_id == "v1"

    def test_rollback_returns_false_when_no_previous(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        registry.promote("v1")
        result = registry.rollback()
        assert result is False

    def test_rollback_returns_false_when_no_active(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        result = registry.rollback()
        assert result is False

    def test_list_versions(self, registry):
        registry.register("v1", "models/v1.pkl", {"sharpe_ratio": 1.5})
        registry.register("v2", "models/v2.pkl", {"sharpe_ratio": 2.0})
        versions = registry.list_versions()
        assert len(versions) == 2
        assert versions[0]["version_id"] == "v1"
        assert versions[1]["version_id"] == "v2"
        assert "created_at" in versions[0]
        assert "metrics" in versions[0]
