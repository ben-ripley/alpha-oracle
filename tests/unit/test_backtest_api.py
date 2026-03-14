"""Tests for POST /strategies/backtest and GET /strategies/backtest/jobs/{id}."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.models import BacktestResult


def _make_result(strategy_name: str = "SwingMomentum") -> BacktestResult:
    return BacktestResult(
        strategy_name=strategy_name,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2026, 1, 1),
        initial_capital=20000.0,
        final_capital=24000.0,
        total_return_pct=20.0,
        annual_return_pct=9.5,
        sharpe_ratio=1.2,
        sortino_ratio=1.56,
        max_drawdown_pct=8.0,
        profit_factor=1.8,
        total_trades=42,
        winning_trades=25,
        losing_trades=17,
        win_rate=0.595,
        avg_win_pct=2.1,
        avg_loss_pct=1.0,
    )


# ---------------------------------------------------------------------------
# _run_backtest_thread
# ---------------------------------------------------------------------------

class TestRunBacktestThread:

    def test_writes_complete_status_on_success(self):
        """Successful run writes status=complete + result to Redis."""
        from src.api.routes.strategies import _run_backtest_thread

        mock_result = _make_result()
        mock_engine_cls = MagicMock()
        mock_engine_cls.return_value.run.return_value = mock_result

        mock_client = MagicMock()
        mock_client.get.side_effect = lambda key: (
            json.dumps({"status": "running", "symbol_count": 2})
            if "job" in key else None
        )

        with patch("src.api.routes.strategies.BacktraderEngine", mock_engine_cls), \
             patch("src.api.routes.strategies.redis_sync") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_client

            _run_backtest_thread(
                job_key="backtest:job:test-123",
                strategy=MagicMock(name="SwingMomentum", min_hold_days=2),
                bars={"AAPL": [], "MSFT": []},
                initial_capital=20000.0,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, tzinfo=timezone.utc),
                redis_url="redis://localhost:6379/0",
            )

        set_calls = mock_client.set.call_args_list
        job_write = next(c for c in set_calls if "backtest:job:" in c.args[0])
        job_data = json.loads(job_write.args[1])
        assert job_data["status"] == "complete"
        assert "result" in job_data
        assert job_data["result"]["strategy_name"] == "SwingMomentum"

    def test_writes_failed_status_on_exception(self):
        """Engine exception writes status=failed with error message."""
        from src.api.routes.strategies import _run_backtest_thread

        mock_engine_cls = MagicMock()
        mock_engine_cls.return_value.run.side_effect = RuntimeError("cerebro exploded")

        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps({"status": "running", "symbol_count": 1})

        with patch("src.api.routes.strategies.BacktraderEngine", mock_engine_cls), \
             patch("src.api.routes.strategies.redis_sync") as mock_redis_mod:
            mock_redis_mod.from_url.return_value = mock_client

            _run_backtest_thread(
                job_key="backtest:job:test-456",
                strategy=MagicMock(),
                bars={"AAPL": []},
                initial_capital=20000.0,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, tzinfo=timezone.utc),
                redis_url="redis://localhost:6379/0",
            )

        set_calls = mock_client.set.call_args_list
        job_write = next(c for c in set_calls if "backtest:job:" in c.args[0])
        job_data = json.loads(job_write.args[1])
        assert job_data["status"] == "failed"
        assert "cerebro exploded" in job_data["error"]

    def test_updates_timing_calibration_on_success(self):
        """Successful run updates ms_per_symbol rolling average in Redis."""
        from src.api.routes.strategies import _run_backtest_thread

        mock_client = MagicMock()
        mock_client.get.side_effect = lambda key: (
            json.dumps({"status": "running", "symbol_count": 2})
            if "job" in key else None  # no existing timing value
        )

        with patch("src.api.routes.strategies.BacktraderEngine") as mock_engine_cls, \
             patch("src.api.routes.strategies.redis_sync") as mock_redis_mod:
            mock_engine_cls.return_value.run.return_value = _make_result()
            mock_redis_mod.from_url.return_value = mock_client

            _run_backtest_thread(
                job_key="backtest:job:test-789",
                strategy=MagicMock(),
                bars={"AAPL": [], "MSFT": []},
                initial_capital=20000.0,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, tzinfo=timezone.utc),
                redis_url="redis://localhost:6379/0",
            )

        set_calls = mock_client.set.call_args_list
        timing_write = next(
            (c for c in set_calls if "ms_per_symbol" in c.args[0]), None
        )
        assert timing_write is not None, "Expected timing key to be updated"

    def test_does_not_update_timing_on_failure(self):
        """Failed runs must not update timing calibration."""
        from src.api.routes.strategies import _run_backtest_thread

        mock_client = MagicMock()
        mock_client.get.return_value = json.dumps({"status": "running", "symbol_count": 2})

        with patch("src.api.routes.strategies.BacktraderEngine") as mock_engine_cls, \
             patch("src.api.routes.strategies.redis_sync") as mock_redis_mod:
            mock_engine_cls.return_value.run.side_effect = RuntimeError("fail")
            mock_redis_mod.from_url.return_value = mock_client

            _run_backtest_thread(
                job_key="backtest:job:test-000",
                strategy=MagicMock(),
                bars={"AAPL": []},
                initial_capital=20000.0,
                start=datetime(2024, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, tzinfo=timezone.utc),
                redis_url="redis://localhost:6379/0",
            )

        set_calls = mock_client.set.call_args_list
        timing_writes = [c for c in set_calls if "ms_per_symbol" in c.args[0]]
        assert len(timing_writes) == 0


# ---------------------------------------------------------------------------
# POST /strategies/backtest
# ---------------------------------------------------------------------------

class TestRunBacktestEndpoint:

    @pytest.mark.asyncio
    async def test_returns_job_id_and_estimated_seconds(self):
        """Successful submit returns job_id, status=running, estimated_seconds."""
        from src.api.routes.strategies import run_backtest, BacktestRequest
        from src.core.models import OHLCV

        mock_strategy_engine = MagicMock()
        mock_strategy_engine.get_strategy.return_value = MagicMock(name="SwingMomentum")

        mock_storage = MagicMock()
        mock_storage.get_ohlcv = AsyncMock(return_value=[MagicMock(spec=OHLCV)])

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # no prior timing
        mock_redis.set = AsyncMock()

        with patch("src.api.routes.strategies.get_strategy_engine", AsyncMock(return_value=mock_strategy_engine)), \
             patch("src.api.routes.strategies.get_storage", AsyncMock(return_value=mock_storage)), \
             patch("src.api.routes.strategies.get_redis", AsyncMock(return_value=mock_redis)), \
             patch("src.api.routes.strategies.asyncio.get_running_loop") as mock_loop, \
             patch("src.api.routes.strategies.get_settings") as mock_settings:

            mock_settings.return_value.redis.url = "redis://localhost:6379/0"
            mock_loop.return_value.run_in_executor = MagicMock(return_value=None)

            request = BacktestRequest(
                strategy_name="SwingMomentum",
                symbols=["AAPL", "MSFT"],
                start_date="2024-01-01",
                end_date="2026-01-01",
                initial_capital=20000.0,
            )
            result = await run_backtest(request)

        assert "job_id" in result
        assert result["status"] == "running"
        assert "estimated_seconds" in result

    @pytest.mark.asyncio
    async def test_returns_404_for_unknown_strategy(self):
        """Unknown strategy_name raises HTTPException 404."""
        from src.api.routes.strategies import run_backtest, BacktestRequest
        from fastapi import HTTPException

        mock_engine = MagicMock()
        mock_engine.get_strategy.side_effect = KeyError("unknown")

        with patch("src.api.routes.strategies.get_strategy_engine", AsyncMock(return_value=mock_engine)):
            with pytest.raises(HTTPException) as exc:
                await run_backtest(BacktestRequest(
                    strategy_name="Unknown",
                    symbols=["AAPL"],
                    start_date="2024-01-01",
                ))
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_when_no_ohlcv_data(self):
        """Empty OHLCV results for all symbols raises HTTPException 422."""
        from src.api.routes.strategies import run_backtest, BacktestRequest
        from fastapi import HTTPException

        mock_engine = MagicMock()
        mock_engine.get_strategy.return_value = MagicMock()

        mock_storage = MagicMock()
        mock_storage.get_ohlcv = AsyncMock(return_value=[])  # no bars

        with patch("src.api.routes.strategies.get_strategy_engine", AsyncMock(return_value=mock_engine)), \
             patch("src.api.routes.strategies.get_storage", AsyncMock(return_value=mock_storage)):
            with pytest.raises(HTTPException) as exc:
                await run_backtest(BacktestRequest(
                    strategy_name="SwingMomentum",
                    symbols=["UNKNOWN"],
                    start_date="2024-01-01",
                ))
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_uses_fallback_timing_when_no_redis_key(self):
        """estimated_seconds falls back to 50ms/symbol when Redis has no timing data."""
        from src.api.routes.strategies import run_backtest, BacktestRequest
        from src.core.models import OHLCV

        mock_engine = MagicMock()
        mock_engine.get_strategy.return_value = MagicMock()

        mock_storage = MagicMock()
        mock_storage.get_ohlcv = AsyncMock(return_value=[MagicMock(spec=OHLCV)])

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # no timing key
        mock_redis.set = AsyncMock()

        with patch("src.api.routes.strategies.get_strategy_engine", AsyncMock(return_value=mock_engine)), \
             patch("src.api.routes.strategies.get_storage", AsyncMock(return_value=mock_storage)), \
             patch("src.api.routes.strategies.get_redis", AsyncMock(return_value=mock_redis)), \
             patch("src.api.routes.strategies.asyncio.get_running_loop") as mock_loop, \
             patch("src.api.routes.strategies.get_settings") as mock_settings:

            mock_settings.return_value.redis.url = "redis://localhost:6379/0"
            mock_loop.return_value.run_in_executor = MagicMock()

            result = await run_backtest(BacktestRequest(
                strategy_name="SwingMomentum",
                symbols=["AAPL", "MSFT"],  # 2 symbols
                start_date="2024-01-01",
            ))

        # Fallback: 50ms * 2 symbols / 1000 = 0.1s
        assert result["estimated_seconds"] == pytest.approx(0.1, abs=0.01)


# ---------------------------------------------------------------------------
# GET /strategies/backtest/jobs/{job_id}
# ---------------------------------------------------------------------------

class TestGetBacktestJob:

    @pytest.mark.asyncio
    async def test_returns_job_data_when_found(self):
        """Returns parsed JSON from Redis when key exists."""
        from src.api.routes.strategies import get_backtest_job

        job_data = {"status": "running", "strategy_name": "SwingMomentum"}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(job_data))

        with patch("src.api.routes.strategies.get_redis", AsyncMock(return_value=mock_redis)):
            result = await get_backtest_job("some-job-id")

        assert result["status"] == "running"
        assert result["strategy_name"] == "SwingMomentum"

    @pytest.mark.asyncio
    async def test_raises_404_when_job_not_found(self):
        """Missing Redis key raises HTTPException 404."""
        from src.api.routes.strategies import get_backtest_job
        from fastapi import HTTPException

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("src.api.routes.strategies.get_redis", AsyncMock(return_value=mock_redis)):
            with pytest.raises(HTTPException) as exc:
                await get_backtest_job("expired-job-id")

        assert exc.value.status_code == 404
