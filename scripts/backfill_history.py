#!/usr/bin/env python3
"""Backfill historical OHLCV data for S&P 500 symbols via Alpha Vantage.

Usage:
    python scripts/backfill_history.py --years 2 --symbols sp500
    python scripts/backfill_history.py --years 2 --symbols AAPL,MSFT,GOOG
    python scripts/backfill_history.py --resume        # continue interrupted run
    python scripts/backfill_history.py --reset         # clear progress and restart

Prerequisites:
    - Docker infra running (TimescaleDB + Redis)
    - SA_ALPHA_VANTAGE_API_KEY set in .env or environment
    - pip install -e ".[dev]" completed

On the free Alpha Vantage tier (5 req/min), 500 symbols takes ~1 hour 40 minutes.
The script is safe to interrupt and resume — completed symbols are tracked in
Redis under the key ``backfill:completed``.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure the project root is on sys.path when run as a script
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import structlog

logger = structlog.get_logger(__name__)

_REDIS_PROGRESS_KEY = "backfill:completed"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill historical OHLCV data into TimescaleDB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--years",
        type=int,
        default=2,
        help="Number of years of history to fetch (default: 2)",
    )
    parser.add_argument(
        "--symbols",
        default="sp500",
        help='Comma-separated symbols or "sp500" for full universe (default: sp500)',
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip symbols already in the Redis progress set (default behaviour; flag for clarity)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the Redis progress set and start over",
    )
    return parser.parse_args()


def _fmt_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym Zs'."""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


async def _get_symbols(symbols_arg: str) -> list[str]:
    """Return the list of symbols to process."""
    if symbols_arg.lower() == "sp500":
        from src.data.universe import SymbolUniverse
        universe = SymbolUniverse()
        symbols = await universe.get_symbols()
        print(f"  Universe loaded: {len(symbols)} S&P 500 symbols")
        return symbols

    symbols = [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
    print(f"  Symbol list: {len(symbols)} symbols from command line")
    return symbols


async def _run(args: argparse.Namespace) -> None:
    from src.core.redis import get_redis
    from src.data.adapters.alpha_vantage_adapter import AlphaVantageAdapter
    from src.data.storage import TimeSeriesStorage

    redis = await get_redis()

    if args.reset:
        await redis.delete(_REDIS_PROGRESS_KEY)
        print("  Progress reset — starting from scratch.")

    print(f"\nBackfill: {args.years} year(s) of OHLCV history")
    print("-" * 60)

    symbols = await _get_symbols(args.symbols)
    if not symbols:
        print("  No symbols to process. Exiting.")
        return

    # Determine which symbols still need processing
    completed_raw = await redis.smembers(_REDIS_PROGRESS_KEY)
    completed: set[str] = set(completed_raw) if completed_raw else set()
    remaining = [s for s in symbols if s not in completed]

    total = len(symbols)
    already_done = len(completed)
    to_fetch = len(remaining)

    print(f"  Total:      {total}")
    print(f"  Completed:  {already_done}")
    print(f"  Remaining:  {to_fetch}")

    if to_fetch == 0:
        print("\n  All symbols already complete. Nothing to do.")
        return

    # Estimate time based on AV free-tier rate (5 req/min)
    from src.core.config import get_settings
    settings = get_settings()
    rate_per_min = settings.data.alpha_vantage.rate_limit_per_minute
    eta_seconds = (to_fetch / rate_per_min) * 60
    print(f"  Estimated time at {rate_per_min} req/min: {_fmt_duration(eta_seconds)}")
    print()

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365 * args.years)

    av = AlphaVantageAdapter()
    storage = TimeSeriesStorage()

    fetched = errors = 0
    run_start = time.monotonic()

    try:
        for i, symbol in enumerate(remaining, start=1):
            done_count = already_done + i - 1
            pct = (done_count / total) * 100

            # Recalculate ETA from actual elapsed rate
            elapsed = time.monotonic() - run_start
            if i > 1:
                rate_actual = (i - 1) / elapsed  # symbols/sec
                secs_left = (to_fetch - i + 1) / rate_actual if rate_actual > 0 else 0
                eta_str = _fmt_duration(secs_left)
            else:
                eta_str = _fmt_duration(eta_seconds)

            print(
                f"  [{symbol:<6}] {done_count + 1:>4}/{total} ({pct:5.1f}%)  ETA: {eta_str}",
                end="\r",
                flush=True,
            )

            try:
                bars = await av.get_historical_bars(symbol, start_dt, end_dt)
                if bars:
                    await storage.store_ohlcv(bars)
                await redis.sadd(_REDIS_PROGRESS_KEY, symbol)
                fetched += 1
            except KeyboardInterrupt:
                print(f"\n\n  Interrupted after {fetched} symbols. Progress saved.")
                print(f"  Run with --resume (or just re-run) to continue.")
                return
            except Exception as exc:
                errors += 1
                # Print on new line so progress bar isn't overwritten
                print(f"\n  [WARN] {symbol}: {exc}")
                logger.warning("backfill.symbol_error", symbol=symbol, error=str(exc))
    finally:
        await av.close()

    elapsed_total = time.monotonic() - run_start
    print(f"\n\n{'=' * 60}")
    print(f"  Backfill complete in {_fmt_duration(elapsed_total)}")
    print(f"  Fetched: {fetched}  Errors: {errors}  Skipped: {already_done}")
    print(f"{'=' * 60}\n")

    if errors:
        print(
            f"  {errors} symbol(s) failed. Re-run to retry — failed symbols were not "
            f"added to the progress set."
        )


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        print("\n\n  Aborted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
