"""Scheduled job implementations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger(__name__)

_ET = ZoneInfo("America/New_York")
_INTRADAY_TIMEFRAMES = frozenset({"1Min", "5Min", "15Min", "1Hour"})

# Redis key TTLs
_DAILY_BARS_DONE_TTL = 90_000        # ~25 hours — expires before next day's run
_FUNDAMENTALS_DONE_TTL = 8 * 86_400  # 8 days — expires before next weekly run


def _now_et() -> datetime:
    """Return current time in US/Eastern. Isolated for test patching."""
    return datetime.now(_ET)


def is_market_hours_request_safe(timeframe: str) -> bool:
    """Return True if it is safe to request IBKR historical data for this timeframe.

    Daily/weekly/monthly bars are always safe to request at any time.
    Intraday bars (1Min, 5Min, 15Min, 1Hour) are only safe during US equity market
    hours: Monday–Friday, 9:30am–5:30pm ET. IBKR rejects intraday historical data
    requests outside this window with a pacing or no-data error.

    Callers should log a warning and skip (not raise) when this returns False.
    """
    if timeframe not in _INTRADAY_TIMEFRAMES:
        return True

    now_et = _now_et()
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=17, minute=30, second=0, microsecond=0)
    return market_open <= now_et <= market_close


async def daily_bars_job() -> None:
    """Fetch daily OHLCV bars for all universe symbols.

    Uses a 7-day lookback window so weekends and market holidays are covered.
    Idempotent: symbols already processed today (tracked in Redis) are skipped.
    """
    logger.info("job.daily_bars.start")
    try:
        from src.core.redis import get_redis
        from src.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
        from src.data.storage import TimeSeriesStorage
        from src.data.universe import SymbolUniverse

        universe = SymbolUniverse()
        symbols = await universe.get_symbols()

        today = _now_et().date()
        end_dt = datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=timezone.utc)
        start_dt = end_dt - timedelta(days=7)

        redis = await get_redis()
        done_key = f"jobs:daily_bars:{today.isoformat()}:done"

        av = AlphaVantageAdapter()
        storage = TimeSeriesStorage()

        fetched = skipped = errors = 0
        for symbol in symbols:
            if await redis.sismember(done_key, symbol):
                skipped += 1
                continue
            try:
                bars = await av.get_historical_bars(symbol, start_dt, end_dt)
                if bars:
                    await storage.store_ohlcv(bars)
                await redis.sadd(done_key, symbol)
                await redis.expire(done_key, _DAILY_BARS_DONE_TTL)
                fetched += 1
            except Exception:
                logger.warning("job.daily_bars.symbol_error", symbol=symbol, exc_info=True)
                errors += 1

        logger.info(
            "job.daily_bars.complete",
            symbols=len(symbols),
            fetched=fetched,
            skipped=skipped,
            errors=errors,
            target_date=str(today),
        )
    except Exception:
        logger.exception("job.daily_bars.error")


async def weekly_fundamentals_job() -> None:
    """Refresh fundamental data for universe symbols via Alpha Vantage OVERVIEW.

    Runs on Saturdays so all 500+ symbols can complete within the AV free-tier
    rate limit (5 req/min → ~1.7 hrs) before Monday open.
    Idempotent: symbols already processed this week (tracked in Redis) are skipped.
    """
    logger.info("job.weekly_fundamentals.start")
    try:
        from src.core.redis import get_redis
        from src.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
        from src.data.storage import TimeSeriesStorage
        from src.data.universe import SymbolUniverse

        universe = SymbolUniverse()
        symbols = await universe.get_symbols()

        redis = await get_redis()
        week_label = _now_et().date().strftime("%Y-W%W")
        done_key = f"jobs:weekly_fundamentals:{week_label}:done"

        av = AlphaVantageAdapter()
        storage = TimeSeriesStorage()

        fetched = skipped = errors = 0
        for symbol in symbols:
            if await redis.sismember(done_key, symbol):
                skipped += 1
                continue
            try:
                fundamentals = await av.get_fundamentals(symbol)
                if fundamentals:
                    await storage.store_fundamentals(fundamentals)
                await redis.sadd(done_key, symbol)
                await redis.expire(done_key, _FUNDAMENTALS_DONE_TTL)
                fetched += 1
            except Exception:
                logger.warning(
                    "job.weekly_fundamentals.symbol_error", symbol=symbol, exc_info=True
                )
                errors += 1

        logger.info(
            "job.weekly_fundamentals.complete",
            symbols=len(symbols),
            fetched=fetched,
            skipped=skipped,
            errors=errors,
        )
    except Exception:
        logger.exception("job.weekly_fundamentals.error")


async def biweekly_altdata_job() -> None:
    """Fetch Form 4 insider transactions and FINRA short interest.

    Short interest: fetched for all universe symbols in one batched FINRA call.
    Insider transactions: fetched per symbol since the last successful run
    (stored as ISO-8601 string in Redis key ``jobs:altdata:last_run``).
    Falls back to 14 days ago when no prior run exists.

    The ``jobs:altdata:last_run`` key is updated *after* both fetches succeed,
    so a partial failure leaves it unchanged and the next run re-fetches the
    full window.
    """
    logger.info("job.biweekly_altdata.start")
    try:
        from src.core.redis import get_redis
        from src.data.adapters.edgar_adapter import EdgarAdapter
        from src.data.adapters.finra_adapter import FinraAdapter
        from src.data.storage import TimeSeriesStorage
        from src.data.universe import SymbolUniverse

        universe = SymbolUniverse()
        symbols = await universe.get_symbols()

        redis = await get_redis()
        last_run_key = "jobs:altdata:last_run"
        now = datetime.now(timezone.utc)

        last_run_str = await redis.get(last_run_key)
        start_dt = (
            datetime.fromisoformat(last_run_str)
            if last_run_str
            else now - timedelta(days=14)
        )

        finra = FinraAdapter()
        edgar = EdgarAdapter()
        storage = TimeSeriesStorage()

        # Short interest — one batched request for all symbols
        short_interest_count = 0
        try:
            short_data = await finra.get_short_interest(symbols)
            if short_data:
                await storage.store_short_interest(short_data)
                short_interest_count = len(short_data)
        except Exception:
            logger.exception("job.biweekly_altdata.short_interest_error")

        # Form 4 insider transactions — per-symbol, errors are isolated
        insider_fetched = insider_errors = 0
        for symbol in symbols:
            try:
                transactions = await edgar.get_insider_transactions(symbol, start_dt, now)
                if transactions:
                    await storage.store_insider_transactions(transactions)
                insider_fetched += 1
            except Exception:
                logger.warning(
                    "job.biweekly_altdata.insider_error", symbol=symbol, exc_info=True
                )
                insider_errors += 1

        # Persist last-run timestamp so next run only fetches new filings
        await redis.set(last_run_key, now.isoformat())

        logger.info(
            "job.biweekly_altdata.complete",
            symbols=len(symbols),
            short_interest_count=short_interest_count,
            insider_fetched=insider_fetched,
            insider_errors=insider_errors,
        )
    except Exception:
        logger.exception("job.biweekly_altdata.error")


async def weekly_retrain_job() -> None:
    """Retrain XGBoost model on latest stored features.

    For each universe symbol, loads OHLCV bars from TimescaleDB, computes
    features via FeatureStore, and derives a 3-class directional target from
    forward close returns.  All per-symbol frames are concatenated before
    training so the model learns across the full universe.

    A new model is only promoted to active when it outperforms the current
    champion on sharpe_ratio (or when no champion exists).
    """
    logger.info("job.weekly_retrain.start")
    try:
        import pandas as pd

        from src.data.storage import TimeSeriesStorage
        from src.data.universe import SymbolUniverse
        from src.signals.feature_store import FeatureStore
        from src.signals.ml.pipeline import MLPipeline
        from src.signals.ml.registry import ModelRegistry

        universe = SymbolUniverse()
        symbols = await universe.get_symbols()

        if not symbols:
            logger.warning("job.weekly_retrain.no_symbols")
            return

        now = datetime.now(timezone.utc)
        two_years_ago = now - timedelta(days=730)

        storage = TimeSeriesStorage()
        store = FeatureStore()
        pipeline = MLPipeline()

        all_features: list = []
        all_targets: list = []

        for symbol in symbols:
            try:
                bars = await storage.get_ohlcv(symbol, two_years_ago, now)
                if not bars:
                    continue

                feat_df = store.compute_features(symbol, bars)
                if feat_df.empty:
                    continue

                # Add close prices for target generation.
                # Must be done per-symbol so forward-return shift doesn't bleed
                # across symbol boundaries.
                close_series = pd.Series(
                    {b.timestamp: b.close for b in bars},
                    name="close",
                )
                feat_df["close"] = close_series.reindex(feat_df.index)

                target = pipeline.prepare_target(feat_df, close_col="close")

                # Drop non-feature columns before training
                feat_df = feat_df.drop(columns=["close", "symbol"], errors="ignore")

                all_features.append(feat_df)
                all_targets.append(target)

            except Exception:
                logger.warning(
                    "job.weekly_retrain.symbol_error", symbol=symbol, exc_info=True
                )

        if not all_features:
            logger.warning("job.weekly_retrain.no_features")
            return

        features_df = pd.concat(all_features)
        target_series = pd.concat(all_targets)

        n_clean = int(target_series.notna().sum())
        if n_clean < pipeline.config.min_training_samples:
            logger.warning(
                "job.weekly_retrain.insufficient_data",
                clean_rows=n_clean,
                required=pipeline.config.min_training_samples,
            )
            return

        metrics = pipeline.train(features_df, target_series)

        version_id = f"v{now.strftime('%Y%m%d_%H%M%S')}"
        model_path = f"models/{version_id}.joblib"
        pipeline.save_model(model_path)

        registry = ModelRegistry()
        registry.register(version_id, model_path, metrics)

        champion = registry.get_active()
        champion_metrics = champion.metrics if champion else None
        if registry.should_promote(metrics, champion_metrics):
            registry.promote(version_id)
            logger.info("job.weekly_retrain.promoted", version=version_id, **metrics)
        else:
            logger.info("job.weekly_retrain.not_promoted", **metrics)

        logger.info("job.weekly_retrain.complete", **metrics)

    except Exception:
        logger.exception("job.weekly_retrain.error")
