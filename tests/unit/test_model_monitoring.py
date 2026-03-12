"""Tests for ML model monitoring and drift detection."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.signals.ml.monitoring import ModelMonitor


def _make_ts(base: datetime, offset_seconds: int) -> datetime:
    return base + timedelta(seconds=offset_seconds)


@pytest.fixture
def monitor() -> ModelMonitor:
    return ModelMonitor(
        window_size=100,
        n_psi_bins=10,
        psi_threshold=0.25,
        accuracy_threshold=0.40,
        max_degraded_windows=5,
    )


@pytest.fixture
def base_time() -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0)


class TestPSI:
    def test_no_shift_returns_low_psi(self, monitor: ModelMonitor):
        rng = np.random.RandomState(42)
        ref_data = pd.DataFrame({"feat_a": rng.normal(0, 1, 1000)})
        cur_data = pd.DataFrame({"feat_a": rng.normal(0, 1, 1000)})

        monitor.set_reference_distribution(ref_data)
        psi = monitor.compute_psi(cur_data)

        assert "feat_a" in psi
        assert psi["feat_a"] < 0.1

    def test_shifted_distribution_returns_high_psi(self, monitor: ModelMonitor):
        rng = np.random.RandomState(42)
        ref_data = pd.DataFrame({"feat_a": rng.normal(0, 1, 1000)})
        cur_data = pd.DataFrame({"feat_a": rng.normal(1, 1, 1000)})

        monitor.set_reference_distribution(ref_data)
        psi = monitor.compute_psi(cur_data)

        assert "feat_a" in psi
        assert psi["feat_a"] > 0.25

    def test_no_reference_returns_empty(self, monitor: ModelMonitor):
        cur_data = pd.DataFrame({"feat_a": np.random.normal(0, 1, 100)})
        assert monitor.compute_psi(cur_data) == {}

    def test_missing_column_skipped(self, monitor: ModelMonitor):
        rng = np.random.RandomState(42)
        ref_data = pd.DataFrame({"feat_a": rng.normal(0, 1, 1000)})
        cur_data = pd.DataFrame({"feat_b": rng.normal(0, 1, 1000)})

        monitor.set_reference_distribution(ref_data)
        psi = monitor.compute_psi(cur_data)
        assert "feat_a" not in psi


class TestRollingAccuracy:
    def test_accuracy_computation(self, monitor: ModelMonitor, base_time: datetime):
        for i in range(100):
            ts = _make_ts(base_time, i)
            monitor.record_prediction(
                symbol="AAPL",
                pred_class=2 if i < 60 else 0,
                proba=np.array([0.1, 0.2, 0.7]),
                timestamp=ts,
            )
            # Actual is always 2 -> 60 correct out of 100
            monitor.record_actual("AAPL", ts, actual_class=2)

        assert monitor.rolling_accuracy() == pytest.approx(0.6, abs=1e-9)

    def test_empty_predictions_returns_zero(self, monitor: ModelMonitor):
        assert monitor.rolling_accuracy() == 0.0

    def test_unresolved_predictions_ignored(self, monitor: ModelMonitor):
        ts = datetime(2026, 1, 1, 12, 0)
        monitor.record_prediction("AAPL", 2, np.array([0.1, 0.2, 0.7]), ts)
        # No actual recorded
        assert monitor.rolling_accuracy() == 0.0


class TestRecordPredictionActual:
    def test_match_by_symbol_and_timestamp(self, monitor: ModelMonitor):
        ts1 = datetime(2026, 1, 1, 12, 0)
        ts2 = datetime(2026, 1, 1, 12, 1)
        monitor.record_prediction("AAPL", 2, np.array([0.1, 0.2, 0.7]), ts1)
        monitor.record_prediction("MSFT", 0, np.array([0.7, 0.2, 0.1]), ts2)

        monitor.record_actual("MSFT", ts2, actual_class=0)

        # AAPL has no actual, MSFT does
        preds = list(monitor._predictions)
        assert preds[0]["actual"] is None
        assert preds[1]["actual"] == 0


class TestDriftDetection:
    def test_degraded_windows_trigger_fallback(self, monitor: ModelMonitor):
        base = datetime(2026, 1, 1, 12, 0)
        # Insert enough wrong predictions so rolling accuracy stays below threshold,
        # then call check_drift repeatedly to accumulate degraded windows.
        for i in range(100):
            ts = _make_ts(base, i)
            monitor.record_prediction("AAPL", 2, np.array([0.1, 0.2, 0.7]), ts)
            monitor.record_actual("AAPL", ts, actual_class=0)

        # Each check_drift call with low accuracy increments degraded_window_count
        for _ in range(6):
            result = monitor.check_drift()

        assert result["fallback_recommended"] is True
        assert result["status"] == "critical"
        assert result["degraded_windows"] >= 5

    def test_ok_status_when_accurate(self, monitor: ModelMonitor, base_time: datetime):
        for i in range(100):
            ts = _make_ts(base_time, i)
            monitor.record_prediction("AAPL", 2, np.array([0.1, 0.2, 0.7]), ts)
            monitor.record_actual("AAPL", ts, actual_class=2)

        result = monitor.check_drift()
        assert result["status"] == "ok"
        assert result["fallback_recommended"] is False

    def test_psi_drift_contributes_to_degradation(self, monitor: ModelMonitor):
        rng = np.random.RandomState(42)
        ref_data = pd.DataFrame({"feat_a": rng.normal(0, 1, 1000)})
        cur_data = pd.DataFrame({"feat_a": rng.normal(3, 1, 1000)})
        monitor.set_reference_distribution(ref_data)

        # Good accuracy but high PSI
        base = datetime(2026, 1, 1, 12, 0)
        for i in range(100):
            ts = _make_ts(base, i)
            monitor.record_prediction("AAPL", 2, np.array([0.1, 0.2, 0.7]), ts)
            monitor.record_actual("AAPL", ts, actual_class=2)

        result = monitor.check_drift(current_features=cur_data)
        assert result["psi_max"] > 0.25
        assert result["degraded_windows"] > 0


class TestResetAfterRetrain:
    def test_reset_clears_state(self, monitor: ModelMonitor):
        monitor._degraded_window_count = 10
        monitor._fallback_active = True

        monitor.reset_after_retrain()

        assert monitor._degraded_window_count == 0
        assert monitor._fallback_active is False
        assert monitor._last_retrain_time is not None


class TestGetMetrics:
    def test_returns_expected_keys(self, monitor: ModelMonitor):
        metrics = monitor.get_metrics()
        expected_keys = {
            "accuracy",
            "total_predictions",
            "resolved_predictions",
            "degraded_windows",
            "fallback_active",
            "staleness_hours",
        }
        assert set(metrics.keys()) == expected_keys

    def test_staleness_after_retrain(self, monitor: ModelMonitor):
        monitor.reset_after_retrain()
        metrics = monitor.get_metrics()
        assert metrics["staleness_hours"] is not None
        assert metrics["staleness_hours"] >= 0.0
