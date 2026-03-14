"""Tests for TradingScheduler."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scheduling.scheduler import TradingScheduler


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.scheduler.enabled = True
    settings.scheduler.daily_bars_cron = "0 17 * * 1-5"
    settings.scheduler.weekly_fundamentals_cron = "0 6 * * 6"
    settings.scheduler.biweekly_altdata_cron = "0 7 1,15 * *"
    settings.scheduler.weekly_retrain_cron = "0 2 * * 0"
    settings.scheduler.daily_sentiment_cron = "30 17 * * 1-5"
    settings.scheduler.daily_briefing_cron = "0 8 * * 1-5"
    settings.scheduler.weekly_options_flow_cron = "0 7 * * 6"
    settings.scheduler.weekly_trends_cron = "30 7 * * 6"
    return settings


@pytest.fixture
def scheduler(mock_settings):
    with patch("src.scheduling.scheduler.get_settings", return_value=mock_settings):
        s = TradingScheduler()
    return s


class TestTradingScheduler:
    def test_setup_registers_all_jobs(self, scheduler):
        scheduler.setup()
        jobs = scheduler._scheduler.get_jobs()
        job_ids = {j.id for j in jobs}
        assert job_ids == {
            "daily_bars", "weekly_fundamentals", "biweekly_altdata", "weekly_retrain",
            "daily_sentiment", "daily_briefing", "weekly_options_flow", "weekly_trends",
        }

    def test_setup_disabled_registers_no_jobs(self, mock_settings):
        mock_settings.scheduler.enabled = False
        with patch("src.scheduling.scheduler.get_settings", return_value=mock_settings):
            s = TradingScheduler()
        s.setup()
        assert len(s._scheduler.get_jobs()) == 0

    def test_get_status_returns_expected_structure(self, scheduler):
        scheduler.setup()
        status = scheduler.get_status()
        assert "running" in status
        assert "jobs" in status
        assert len(status["jobs"]) == 8
        for job in status["jobs"]:
            assert "id" in job
            assert "name" in job
            assert "next_run" in job
            assert "trigger" in job

    @pytest.mark.asyncio
    async def test_start_and_stop(self, scheduler):
        scheduler.setup()
        scheduler.start()
        assert scheduler._scheduler.running is True
        # shutdown(wait=False) is async-deferred; just verify no error
        scheduler.stop()

    @pytest.mark.asyncio
    async def test_trigger_job_found(self, scheduler):
        scheduler.setup()
        scheduler.start()
        result = await scheduler.trigger_job("daily_bars")
        assert result is True
        scheduler.stop()

    @pytest.mark.asyncio
    async def test_trigger_job_not_found(self, scheduler):
        scheduler.setup()
        scheduler.start()
        result = await scheduler.trigger_job("nonexistent_job")
        assert result is False
        scheduler.stop()
