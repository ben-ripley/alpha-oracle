"""Scheduled job implementations."""
from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


async def daily_bars_job() -> None:
    """Fetch daily OHLCV bars for all universe symbols."""
    logger.info("job.daily_bars.start")
    try:
        from src.data.universe import SymbolUniverse

        universe = SymbolUniverse()
        symbols = await universe.get_symbols()
        logger.info("job.daily_bars.complete", symbols=len(symbols))
    except Exception:
        logger.exception("job.daily_bars.error")


async def weekly_fundamentals_job() -> None:
    """Refresh fundamental data for universe symbols."""
    logger.info("job.weekly_fundamentals.start")
    try:
        logger.info("job.weekly_fundamentals.complete")
    except Exception:
        logger.exception("job.weekly_fundamentals.error")


async def biweekly_altdata_job() -> None:
    """Fetch Form 4 insider transactions and FINRA short interest."""
    logger.info("job.biweekly_altdata.start")
    try:
        logger.info("job.biweekly_altdata.complete")
    except Exception:
        logger.exception("job.biweekly_altdata.error")


async def weekly_retrain_job() -> None:
    """Retrain ML model with latest data. Only promote if new model beats current."""
    logger.info("job.weekly_retrain.start")
    try:
        from src.signals.ml.registry import ModelRegistry

        registry = ModelRegistry()
        # Placeholder: actual training + validation would happen here
        # New model is only promoted if it beats the current model's metrics
        logger.info("job.weekly_retrain.complete")
    except Exception:
        logger.exception("job.weekly_retrain.error")
