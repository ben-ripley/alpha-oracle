"""Unit tests for weekly_retrain_job.

All external dependencies (Universe, Storage, FeatureStore, MLPipeline,
ModelRegistry) are mocked so no database, broker, or real model training
is required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.scheduling.jobs import weekly_retrain_job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SYMBOLS = ["AAPL", "MSFT"]
_METRICS = {"accuracy": 0.62, "log_loss": 0.91, "n_samples": 600, "n_features": 48}


def _make_bar(symbol: str, ts: datetime, close: float = 150.0) -> MagicMock:
    bar = MagicMock()
    bar.symbol = symbol
    bar.timestamp = ts
    bar.close = close
    return bar


def _make_bars(symbol: str, n: int = 10) -> list:
    base = datetime(2023, 1, 2, tzinfo=timezone.utc)
    from datetime import timedelta
    return [
        _make_bar(symbol, base + timedelta(days=i), close=150.0 + i * 0.1)
        for i in range(n)
    ]


def _make_feature_df(n_rows: int = 10) -> pd.DataFrame:
    """Return a small DataFrame that looks like FeatureStore output (no close, no symbol)."""
    from datetime import timedelta
    base = datetime(2023, 1, 2, tzinfo=timezone.utc)
    index = pd.DatetimeIndex([base + timedelta(days=i) for i in range(n_rows)])
    return pd.DataFrame(
        {"ret_1d": [0.01] * n_rows, "rsi_14": [50.0] * n_rows},
        index=index,
    )


def _make_target_series(n_rows: int = 10, n_nan: int = 5) -> pd.Series:
    """Return a target Series with some NaN at the tail (forward-return horizon)."""
    from datetime import timedelta
    base = datetime(2023, 1, 2, tzinfo=timezone.utc)
    index = pd.DatetimeIndex([base + timedelta(days=i) for i in range(n_rows)])
    values = [1] * (n_rows - n_nan) + [float("nan")] * n_nan
    return pd.Series(values, index=index)


def _mock_universe(symbols: list[str]) -> MagicMock:
    mock = MagicMock()
    mock.get_symbols = AsyncMock(return_value=symbols)
    return mock


def _mock_storage(bars_per_symbol: dict[str, list]) -> MagicMock:
    mock = MagicMock()

    async def _get_ohlcv(symbol, start, end):
        return bars_per_symbol.get(symbol, [])

    mock.get_ohlcv = _get_ohlcv
    mock.get_sentiment = AsyncMock(return_value=[])
    mock.get_analyst_estimates = AsyncMock(return_value=[])
    return mock


def _mock_feature_store(feat_df: pd.DataFrame) -> MagicMock:
    mock = MagicMock()
    mock.compute_features = MagicMock(return_value=feat_df)
    return mock


def _mock_pipeline(
    target: pd.Series | None = None,
    metrics: dict | None = None,
    min_samples: int = 5,
) -> MagicMock:
    mock = MagicMock()
    mock.prepare_target = MagicMock(return_value=target if target is not None else _make_target_series())
    mock.train = MagicMock(return_value=metrics or _METRICS)
    mock.save_model = MagicMock()
    mock.config = MagicMock()
    mock.config.min_training_samples = min_samples
    return mock


def _mock_registry(
    champion: MagicMock | None = None,
    should_promote: bool = True,
) -> MagicMock:
    mock = MagicMock()
    mock.register = MagicMock()
    mock.get_active = MagicMock(return_value=champion)
    mock.should_promote = MagicMock(return_value=should_promote)
    mock.promote = MagicMock(return_value=True)
    return mock


def _patches(
    universe=None,
    storage=None,
    store=None,
    pipeline=None,
    registry=None,
):
    """Return a list of context managers for the lazy imports in weekly_retrain_job."""
    return [
        patch("src.data.universe.SymbolUniverse", return_value=universe or _mock_universe(_SYMBOLS)),
        patch("src.data.storage.TimeSeriesStorage", return_value=storage or _mock_storage(
            {s: _make_bars(s) for s in _SYMBOLS}
        )),
        patch("src.signals.feature_store.FeatureStore", return_value=store or _mock_feature_store(_make_feature_df())),
        patch("src.signals.ml.pipeline.MLPipeline", return_value=pipeline or _mock_pipeline()),
        patch("src.signals.ml.registry.ModelRegistry", return_value=registry or _mock_registry()),
    ]


def _apply_patches(ps):
    """Enter a list of patches and return (stack_of_mocks, original_patches)."""
    entered = [p.__enter__() for p in ps]
    return ps, entered


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWeeklyRetrainJobNoSymbols:
    @pytest.mark.asyncio
    async def test_empty_universe_returns_early(self):
        universe = _mock_universe([])
        pipeline = _mock_pipeline()
        ps = _patches(universe=universe, pipeline=pipeline)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        pipeline.train.assert_not_called()


class TestWeeklyRetrainJobNoData:
    @pytest.mark.asyncio
    async def test_no_ohlcv_returns_early(self):
        """All symbols return empty bar lists — job should log warning and return."""
        storage = _mock_storage({"AAPL": [], "MSFT": []})
        pipeline = _mock_pipeline()
        registry = _mock_registry()

        ps = _patches(storage=storage, pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        pipeline.train.assert_not_called()
        registry.register.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_feature_df_skips_symbol(self):
        """FeatureStore returns empty DataFrame for every symbol — no training."""
        store = _mock_feature_store(pd.DataFrame())
        pipeline = _mock_pipeline()

        ps = _patches(store=store, pipeline=pipeline)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        pipeline.train.assert_not_called()


class TestWeeklyRetrainJobInsufficientData:
    @pytest.mark.asyncio
    async def test_fewer_clean_rows_than_min_returns_early(self):
        """Only 2 non-NaN target rows but min_training_samples=500 — should not train."""
        target = _make_target_series(n_rows=10, n_nan=8)   # 2 clean rows
        pipeline = _mock_pipeline(target=target, min_samples=500)
        registry = _mock_registry()

        ps = _patches(pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        pipeline.train.assert_not_called()
        registry.register.assert_not_called()


class TestWeeklyRetrainJobHappyPath:
    @pytest.mark.asyncio
    async def test_model_trained_and_registered(self):
        pipeline = _mock_pipeline(min_samples=1)
        registry = _mock_registry(champion=None, should_promote=True)

        ps = _patches(pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        pipeline.train.assert_called_once()
        pipeline.save_model.assert_called_once()
        registry.register.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_champion_always_promotes(self):
        """When no champion exists, should_promote returns True and model is promoted."""
        pipeline = _mock_pipeline(min_samples=1)
        registry = _mock_registry(champion=None, should_promote=True)

        ps = _patches(pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        registry.promote.assert_called_once()

    @pytest.mark.asyncio
    async def test_version_id_passed_to_register_and_promote(self):
        pipeline = _mock_pipeline(min_samples=1)
        registry = _mock_registry(champion=None, should_promote=True)

        ps = _patches(pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        register_args = registry.register.call_args
        version_id = register_args[0][0]
        assert version_id.startswith("v")

        promote_args = registry.promote.call_args
        assert promote_args[0][0] == version_id

    @pytest.mark.asyncio
    async def test_compute_features_called_per_symbol(self):
        store = _mock_feature_store(_make_feature_df())
        pipeline = _mock_pipeline(min_samples=1)

        ps = _patches(store=store, pipeline=pipeline)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        assert store.compute_features.call_count == len(_SYMBOLS)


class TestWeeklyRetrainJobNotPromoted:
    @pytest.mark.asyncio
    async def test_worse_than_champion_not_promoted(self):
        """New model's metrics are worse — should_promote returns False — no promote call."""
        champion = MagicMock()
        champion.metrics = {"sharpe_ratio": 2.0}

        pipeline = _mock_pipeline(min_samples=1)
        registry = _mock_registry(champion=champion, should_promote=False)

        ps = _patches(pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        # Model is still registered, just not promoted
        registry.register.assert_called_once()
        registry.promote.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_promote_receives_correct_metrics(self):
        """should_promote must be called with (new_metrics, champion_metrics)."""
        champion = MagicMock()
        champion.metrics = {"sharpe_ratio": 1.5}

        pipeline = _mock_pipeline(metrics=_METRICS, min_samples=1)
        registry = _mock_registry(champion=champion, should_promote=False)

        ps = _patches(pipeline=pipeline, registry=registry)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        registry.should_promote.assert_called_once_with(_METRICS, champion.metrics)


class TestWeeklyRetrainJobErrorHandling:
    @pytest.mark.asyncio
    async def test_training_exception_does_not_crash_job(self):
        """If pipeline.train() raises, the job catches it and logs — no re-raise."""
        pipeline = _mock_pipeline(min_samples=1)
        pipeline.train = MagicMock(side_effect=RuntimeError("XGBoost exploded"))

        ps = _patches(pipeline=pipeline)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()   # must not raise
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

    @pytest.mark.asyncio
    async def test_symbol_error_is_isolated(self):
        """An exception while processing one symbol should not stop others."""
        # First symbol's get_ohlcv raises, second works fine
        storage = MagicMock()
        call_count = 0

        async def _get_ohlcv(symbol, start, end):
            nonlocal call_count
            call_count += 1
            if symbol == "AAPL":
                raise RuntimeError("storage error for AAPL")
            return _make_bars(symbol)

        storage.get_ohlcv = _get_ohlcv
        storage.get_sentiment = AsyncMock(return_value=[])
        storage.get_analyst_estimates = AsyncMock(return_value=[])

        pipeline = _mock_pipeline(min_samples=1)
        store = _mock_feature_store(_make_feature_df())

        ps = _patches(storage=storage, pipeline=pipeline, store=store)
        for p in ps:
            p.__enter__()
        try:
            await weekly_retrain_job()   # must not raise
        finally:
            for p in reversed(ps):
                p.__exit__(None, None, None)

        # MSFT should have been processed successfully
        pipeline.train.assert_called_once()
