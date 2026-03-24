"""APScheduler integration with FastAPI."""
from __future__ import annotations

from datetime import datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.config import get_settings

logger = structlog.get_logger(__name__)


class TradingScheduler:
    """Manages scheduled jobs for the trading system."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._settings = get_settings().scheduler

    def setup(self) -> None:
        """Register all jobs based on config cron expressions."""
        from src.scheduling.jobs import (
            biweekly_altdata_job,
            daily_bars_job,
            daily_briefing_job,
            daily_sentiment_job,
            weekly_fundamentals_job,
            weekly_options_flow_job,
            weekly_retrain_job,
            weekly_trends_job,
        )

        if not self._settings.enabled:
            logger.info("scheduler_disabled")
            return

        self._scheduler.add_job(
            daily_bars_job,
            CronTrigger.from_crontab(self._settings.daily_bars_cron),
            id="daily_bars",
            name="Daily OHLCV Backfill",
            replace_existing=True,
        )
        self._scheduler.add_job(
            weekly_fundamentals_job,
            CronTrigger.from_crontab(self._settings.weekly_fundamentals_cron),
            id="weekly_fundamentals",
            name="Weekly Fundamentals Refresh",
            replace_existing=True,
        )
        self._scheduler.add_job(
            biweekly_altdata_job,
            CronTrigger.from_crontab(self._settings.biweekly_altdata_cron),
            id="biweekly_altdata",
            name="Biweekly Alt Data Fetch",
            replace_existing=True,
        )
        self._scheduler.add_job(
            weekly_retrain_job,
            CronTrigger.from_crontab(self._settings.weekly_retrain_cron),
            id="weekly_retrain",
            name="Weekly Model Retrain",
            replace_existing=True,
        )
        self._scheduler.add_job(
            daily_sentiment_job,
            CronTrigger.from_crontab(self._settings.daily_sentiment_cron),
            id="daily_sentiment",
            name="Daily Sentiment Scoring",
            replace_existing=True,
        )
        self._scheduler.add_job(
            daily_briefing_job,
            CronTrigger.from_crontab(self._settings.daily_briefing_cron),
            id="daily_briefing",
            name="Daily Portfolio Briefing",
            replace_existing=True,
        )
        self._scheduler.add_job(
            weekly_options_flow_job,
            CronTrigger.from_crontab(self._settings.weekly_options_flow_cron),
            id="weekly_options_flow",
            name="Weekly Options Flow Fetch",
            replace_existing=True,
        )
        self._scheduler.add_job(
            weekly_trends_job,
            CronTrigger.from_crontab(self._settings.weekly_trends_cron),
            id="weekly_trends",
            name="Weekly Google Trends Fetch",
            replace_existing=True,
        )

    def start(self) -> None:
        self._scheduler.start()
        logger.info("scheduler_started", jobs=len(self._scheduler.get_jobs()))

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("scheduler_stopped")

    def get_status(self) -> dict:
        """Get status of all registered jobs."""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(nrt) if (nrt := getattr(job, "next_run_time", None)) else None,
                "trigger": str(job.trigger),
            })
        return {"running": self._scheduler.running, "jobs": jobs}

    async def trigger_job(self, job_id: str) -> bool:
        """Manually trigger a job by ID."""
        job = self._scheduler.get_job(job_id)
        if not job:
            return False
        job.modify(next_run_time=datetime.now())
        return True
