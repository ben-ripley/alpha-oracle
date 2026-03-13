# Data Backfill

The `backfill_history.py` script performs a one-time backfill of historical OHLCV data for the S&P 500 universe (or custom symbol list) using Alpha Vantage.

## Purpose

- Populate TimescaleDB with 2+ years of daily OHLCV bars
- Enable backtesting and strategy development
- Required before running live strategies (historical data for indicators)

**Source:** Alpha Vantage Daily Adjusted endpoint (20+ years available)

---

## Prerequisites

1. **Docker infrastructure running:**
   ```bash
   docker compose up -d timescaledb redis
   ```

2. **Alpha Vantage API key:**
   - Free tier: https://www.alphavantage.co/support/#api-key
   - Set in environment: `SA_ALPHA_VANTAGE_API_KEY`
   - Rate limit: 5 requests/minute (free tier)

3. **Python environment:**
   ```bash
   pip install -e ".[dev]"
   ```

---

## Usage

### Full S&P 500 backfill (2 years)

```bash
python scripts/backfill_history.py --years 2 --symbols sp500
```

**Output:**
```
Backfill: 2 year(s) of OHLCV history
------------------------------------------------------------
  Universe loaded: 503 S&P 500 symbols
  Total:      503
  Completed:  0
  Remaining:  503
  Estimated time at 5 req/min: 1h 40m 36s

  [AAPL ]  1/503 (  0.2%)  ETA: 1h 40m 36s
  [MSFT ]  2/503 (  0.4%)  ETA: 1h 39m 12s
  ...
```

**Duration:** ~1 hour 40 minutes on free tier (5 req/min rate limit)

---

### Quick smoke test (3 symbols)

```bash
python scripts/backfill_history.py --years 2 --symbols AAPL,MSFT,GOOG
```

**Output:**
```
  Symbol list: 3 symbols from command line
  Total:      3
  Completed:  0
  Remaining:  3
  Estimated time at 5 req/min: 36s
```

**Duration:** ~36 seconds

---

### Resume interrupted run

The script tracks completed symbols in Redis (`backfill:completed` set). If interrupted (Ctrl+C, network error), restart to continue:

```bash
python scripts/backfill_history.py --resume
# or just re-run without --reset (resume is default behavior)
```

**Output:**
```
  Total:      503
  Completed:  127
  Remaining:  376
  Estimated time at 5 req/min: 1h 15m 12s
```

Only symbols not in the `backfill:completed` set will be fetched.

---

### Reset and start over

```bash
python scripts/backfill_history.py --reset --years 2 --symbols sp500
```

**Warning:** Clears the `backfill:completed` Redis key. All symbols will be re-fetched (duplicates will be deduplicated by TimescaleDB primary key).

---

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--years` | 2 | Number of years of history to fetch |
| `--symbols` | `sp500` | Symbol list: `sp500` or comma-separated tickers |
| `--resume` | (default) | Skip symbols already in progress set (implicit) |
| `--reset` | (off) | Clear progress set and start from scratch |

---

## Rate Limiting

**Alpha Vantage free tier:** 5 requests per minute (500 API calls per day)

**Script behavior:**
- Respects Alpha Vantage rate limits via adaptive pacing
- Displays dynamic ETA based on actual throughput
- Safe to interrupt (Ctrl+C) — progress is saved

**Estimated times:**

| Symbols | Duration (5 req/min) |
|---------|---------------------|
| 10 | ~2 minutes |
| 100 | ~20 minutes |
| 503 (S&P 500) | ~1 hour 40 minutes |

**Premium tier:** 75 req/min → ~7 minutes for full S&P 500

---

## Idempotency

### Redis Progress Key

**Key:** `backfill:completed`
**Type:** Set
**Members:** Stock symbols (e.g., `"AAPL"`, `"MSFT"`)
**TTL:** None (persistent)

**Behavior:**
- Symbol added to set **after** successful storage in TimescaleDB
- Failed symbols are **not** added → will be retried on next run
- Check membership before fetching: `redis.sismember("backfill:completed", "AAPL")`

### Database Deduplication

OHLCV table has a primary key on `(symbol, timestamp)`. Duplicate inserts are ignored (ON CONFLICT DO NOTHING behavior).

**Result:** Safe to re-run the script multiple times — duplicates will be skipped.

---

## Error Handling

### Symbol-level errors

If a single symbol fails (network error, API limit, invalid ticker), the script logs a warning and continues:

```
[WARN] INVALID: API returned no data
```

**Behavior:**
- Symbol is **not** added to `backfill:completed`
- Will be retried on next run
- Fetched symbols are recorded before moving to the next

### Keyboard interrupt (Ctrl+C)

```
Interrupted after 42 symbols. Progress saved.
Run with --resume (or just re-run) to continue.
```

**Behavior:**
- Completed symbols are already in `backfill:completed`
- Re-run the script to continue from where it left off

### Network failure

**Transient errors:** Logged and skipped; retry on next run
**Persistent errors:** Check API key, internet connectivity, Alpha Vantage status

---

## Output

### Console

Live progress line with dynamic ETA:
```
[AAPL ]  42/503 (  8.3%)  ETA: 1h 32m 15s
```

**Fields:**
- `[SYMBOL]` — Current symbol being processed
- `42/503` — Completed count / total
- `(8.3%)` — Percentage complete
- `ETA: 1h 32m 15s` — Estimated time remaining (updates based on actual rate)

### Final Summary

```
============================================================
  Backfill complete in 1h 38m 42s
  Fetched: 503  Errors: 0  Skipped: 0
============================================================
```

### Logs

Warnings and errors are logged to `structlog` (console by default):
```python
logger.warning("backfill.symbol_error", symbol=symbol, error=str(exc))
```

---

## Verification

### Check database

```bash
# Connect to TimescaleDB
docker exec -it stock-analysis-timescaledb-1 psql -U trader -d stock_analysis

# Count symbols
SELECT COUNT(DISTINCT symbol) FROM ohlcv;
-- Expected: 503

# Check date range for AAPL
SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv WHERE symbol = 'AAPL';

# Sample data
SELECT * FROM ohlcv WHERE symbol = 'AAPL' ORDER BY timestamp DESC LIMIT 5;
```

### Check Redis progress

```bash
# Count completed symbols
docker exec -it stock-analysis-redis-1 redis-cli SCARD backfill:completed
-- Expected: 503

# Check specific symbol
docker exec -it stock-analysis-redis-1 redis-cli SISMEMBER backfill:completed AAPL
-- Expected: 1 (true)
```

---

## Troubleshooting

### "Connection refused" (TimescaleDB)
```bash
docker compose up -d timescaledb
docker compose logs timescaledb
```

### "Connection refused" (Redis)
```bash
docker compose up -d redis
```

### "Alpha Vantage API key invalid"
- Check environment variable: `echo $SA_ALPHA_VANTAGE_API_KEY`
- Verify key at https://www.alphavantage.co/support/#api-key
- Set in `.env` file or export: `export SA_ALPHA_VANTAGE_API_KEY=your_key_here`

### "Rate limit exceeded"
- Free tier: 5 req/min, 500 req/day
- Wait 24 hours for daily limit reset
- Upgrade to premium: https://www.alphavantage.co/premium/

### "No data returned for symbol"
- Symbol may be delisted or invalid ticker
- Alpha Vantage does not have data for all symbols
- Check ticker spelling (use primary exchange symbol)

### Slow progress
- Expected on free tier (5 req/min)
- Script displays accurate ETA based on actual rate
- Premium tier: 75 req/min → 15x faster

---

## Next Steps

After backfill completes:

1. **Run backtest:**
   ```python
   from src.strategy.backtest import BacktestEngine
   # ...
   ```

2. **Start daily bar job:**
   System will automatically fetch latest bars daily via scheduler (6:00 AM ET)

3. **Enable strategies:**
   Strategies require historical data for indicator calculations

---

<!-- DIAGRAM: Backfill flow from Alpha Vantage through adapters to TimescaleDB with Redis progress tracking -->
