#!/usr/bin/env python3
"""Backfill historical OHLCV data using Yahoo Finance (yfinance) — no API key required.

Use this script when you do not have an Alpha Vantage premium subscription.
Once you have a premium Alpha Vantage key, the standard backfill_history.py
script provides split/dividend-adjusted closes directly from Alpha Vantage.

Usage:
    python scripts/backfill_history_yf.py --years 5 --symbols sp500
    python scripts/backfill_history_yf.py --years 5 --symbols AAPL,MSFT,GOOG
    python scripts/backfill_history_yf.py --resume        # continue interrupted run
    python scripts/backfill_history_yf.py --reset         # clear progress and restart

Prerequisites:
    - Docker infra running (TimescaleDB + Redis)
    - pip install -e ".[dev]" completed (includes yfinance)

Progress is tracked in Redis under the same key as the Alpha Vantage script
(``backfill:completed``) so both scripts are interchangeable and resume-aware.
Prices are stored as adjusted closes (split/dividend adjusted) via yfinance
``auto_adjust=True``, which matches the behaviour of Alpha Vantage's
TIME_SERIES_DAILY_ADJUSTED endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import structlog

logger = structlog.get_logger(__name__)

_REDIS_PROGRESS_KEY = "backfill:completed"
_REQUEST_DELAY_SECONDS = 0.5  # be polite to Yahoo Finance


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill historical OHLCV data into TimescaleDB via Yahoo Finance.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--years", type=int, default=5,
                        help="Number of years of history to fetch (default: 5)")
    parser.add_argument("--symbols", default="sp500",
                        help='Comma-separated symbols or "sp500" (default: sp500)')
    parser.add_argument("--resume", action="store_true",
                        help="Skip already-completed symbols (default behaviour)")
    parser.add_argument("--reset", action="store_true",
                        help="Clear the Redis progress set and start over")
    return parser.parse_args()


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


async def _get_symbols(symbols_arg: str) -> list[str]:
    if symbols_arg.lower() == "sp500":
        from src.data.universe import SymbolUniverse
        universe = SymbolUniverse()
        symbols = await universe.get_symbols()
        print(f"  Universe loaded: {len(symbols)} S&P 500 symbols")
        return symbols
    symbols = [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
    print(f"  Symbol list: {len(symbols)} symbols from command line")
    return symbols


def _fetch_yf_bars(symbol: str, start_dt: datetime, end_dt: datetime):
    """Fetch OHLCV bars from Yahoo Finance. Returns list of OHLCV or empty list."""
    import yfinance as yf
    from src.core.models import OHLCV

    ticker = yf.Ticker(symbol)
    hist = ticker.history(
        start=start_dt.strftime("%Y-%m-%d"),
        end=end_dt.strftime("%Y-%m-%d"),
        auto_adjust=True,   # prices are split/dividend adjusted — matches AV adjusted close
        actions=False,
    )

    if hist.empty:
        return []

    bars: list[OHLCV] = []
    for ts, row in hist.iterrows():
        # yfinance returns timezone-aware timestamps; normalise to UTC
        if hasattr(ts, "tzinfo") and ts.tzinfo is not None:
            bar_ts = ts.to_pydatetime().astimezone(timezone.utc).replace(tzinfo=timezone.utc)
        else:
            bar_ts = ts.to_pydatetime().replace(tzinfo=timezone.utc)

        close = float(row["Close"])
        bars.append(
            OHLCV(
                symbol=symbol,
                timestamp=bar_ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=close,
                volume=int(row["Volume"]),
                adjusted_close=close,  # auto_adjust=True means Close IS the adjusted close
                source="yahoo_finance",
            )
        )
    return bars


async def _run(args: argparse.Namespace) -> None:
    from src.core.redis import get_redis
    from src.data.storage import TimeSeriesStorage

    redis = await get_redis()

    if args.reset:
        await redis.delete(_REDIS_PROGRESS_KEY)
        print("  Progress reset — starting from scratch.")

    print(f"\nBackfill (Yahoo Finance): {args.years} year(s) of OHLCV history")
    print("-" * 60)

    symbols = await _get_symbols(args.symbols)
    if not symbols:
        print("  No symbols to process. Exiting.")
        return

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

    eta_seconds = to_fetch * _REQUEST_DELAY_SECONDS
    print(f"  Estimated time: {_fmt_duration(eta_seconds)} (no rate limit)")
    print()

    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=365 * args.years)

    storage = TimeSeriesStorage()
    fetched = errors = 0
    run_start = time.monotonic()

    try:
        for i, symbol in enumerate(remaining, start=1):
            done_count = already_done + i - 1
            pct = (done_count / total) * 100

            elapsed = time.monotonic() - run_start
            if i > 1:
                rate_actual = (i - 1) / elapsed
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
                # yfinance is synchronous — run in executor to avoid blocking event loop
                loop = asyncio.get_event_loop()
                bars = await loop.run_in_executor(
                    None, _fetch_yf_bars, symbol, start_dt, end_dt
                )
                if bars:
                    await storage.store_ohlcv(bars)
                await redis.sadd(_REDIS_PROGRESS_KEY, symbol)
                fetched += 1
                await asyncio.sleep(_REQUEST_DELAY_SECONDS)
            except KeyboardInterrupt:
                print(f"\n\n  Interrupted after {fetched} symbols. Progress saved.")
                print(f"  Re-run to continue.")
                return
            except Exception as exc:
                errors += 1
                print(f"\n  [WARN] {symbol}: {exc}")
                logger.warning("backfill_yf.symbol_error", symbol=symbol, error=str(exc))
    finally:
        pass  # TimeSeriesStorage uses SQLAlchemy sessions (no persistent connection to close)

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
