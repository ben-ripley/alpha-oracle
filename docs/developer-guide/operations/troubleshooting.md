# Troubleshooting

Common issues and solutions for the alpha-oracle system.

## Backend / API Issues

### "Connection refused" on port 8000

**Symptom:** Frontend shows connection error, `curl http://localhost:8000` fails

**Diagnosis:**
```bash
# Check if backend is running
ps aux | grep uvicorn

# Check PID file
cat .pids/backend.pid

# Check logs
tail -f logs/backend.log
```

**Solutions:**
1. Backend not started → `./scripts/start-backend.sh`
2. Backend crashed → Check `logs/backend.log` for errors
3. Port already in use → `lsof -i :8000` (kill conflicting process)
4. Permission error → Check file ownership, run as non-root

---

### FastAPI startup fails

**Symptom:** Backend exits immediately after start

**Check logs:**
```bash
tail -50 logs/backend.log
```

**Common causes:**

**1. Missing environment variables:**
```
KeyError: 'SA_ALPHA_VANTAGE_API_KEY'
```
**Solution:** Set in `.env` file or export:
```bash
export SA_ALPHA_VANTAGE_API_KEY=your_key_here
```

**2. Database connection error:**
```
sqlalchemy.exc.OperationalError: could not connect to server
```
**Solution:** Start TimescaleDB:
```bash
docker compose up -d timescaledb
docker compose logs timescaledb
```

**3. Redis connection error:**
```
redis.exceptions.ConnectionError: Error connecting to Redis
```
**Solution:** Start Redis:
```bash
docker compose up -d redis
docker compose logs redis
```

**4. Import error:**
```
ModuleNotFoundError: No module named 'ib_async'
```
**Solution:** Install dependencies:
```bash
pip install -e ".[dev]"
```

---

## Database Issues

### "Connection refused" on port 5432

**Symptom:** Backend logs show PostgreSQL connection errors

**Diagnosis:**
```bash
docker compose ps
docker compose logs timescaledb
```

**Solutions:**
1. TimescaleDB not running → `docker compose up -d timescaledb`
2. Database initializing → Wait 10-15 seconds for health check
3. Port conflict → Check if another Postgres instance is using 5432
4. Volume corruption → `docker compose down -v && docker compose up -d` (destroys data)

---

### Empty query results despite backfill

**Symptom:** Queries return no rows, but backfill completed

**Diagnosis:**
```bash
docker exec -it alpha-oracle-timescaledb-1 psql -U trader -d stock_analysis

-- Check row count
SELECT COUNT(*) FROM ohlcv;

-- Check symbols
SELECT DISTINCT symbol FROM ohlcv LIMIT 10;

-- Check date range
SELECT MIN(timestamp), MAX(timestamp) FROM ohlcv;
```

**Common causes:**
1. Timezone mismatch → Queries use wrong timezone
2. Symbol case sensitivity → Use uppercase symbols
3. Wrong database → Check connection string points to `stock_analysis`

---

### Hypertable errors

**Symptom:**
```
ERROR: relation "ohlcv" is not a hypertable
```

**Solution:** Re-initialize database:
```bash
docker compose down -v  # WARNING: destroys all data
docker compose up -d timescaledb
# Wait for initialization to complete
python scripts/backfill_history.py --years 2 --symbols sp500
```

---

## Redis Issues

### "Connection refused" on port 6379

**Symptom:** Backend logs show Redis connection errors

**Diagnosis:**
```bash
docker compose ps
docker compose logs redis
```

**Solutions:**
1. Redis not running → `docker compose up -d redis`
2. Port conflict → Check if another Redis instance is using 6379
3. Max clients reached → `docker restart alpha-oracle-redis-1`

---

### Redis out of memory

**Symptom:**
```
redis.exceptions.ResponseError: OOM command not allowed when used memory > 'maxmemory'
```

**Solution:** Increase Redis max memory in `docker-compose.yml`:
```yaml
redis:
  command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
```

Then restart:
```bash
docker compose restart redis
```

---

### Lost PDT tracking data

**Symptom:** Day trade count resets unexpectedly

**Diagnosis:**
```bash
docker exec -it alpha-oracle-redis-1 redis-cli ZRANGE risk:pdt:trades 0 -1 WITHSCORES
```

**Causes:**
1. Redis `FLUSHALL` executed → Data lost, cannot recover
2. Container restart with no volume → Check `docker-compose.yml` has `redis_data` volume

**Prevention:**
- Never run `FLUSHALL` in production
- Always use `docker compose down` (not `docker compose down -v`)
- Backup Redis data: `docker exec alpha-oracle-redis-1 redis-cli SAVE`

---

## IBKR Gateway Issues

### "Client ID already in use"

**Symptom:**
```
ib_async.wrapper.Connection error: 326, clientId 1 is already in use.
```

**Cause:** Another connection is using the same client ID

**Diagnosis:**
```bash
# Check for orphaned Python processes
ps aux | grep python

# Check IB Gateway connections (in Gateway UI)
# File → Global Configuration → API → Settings → Active Clients
```

**Solutions:**
1. Kill orphaned process: `pkill -f "uvicorn src.api.main"`
2. Restart IB Gateway to clear stuck connections
3. Use unique client IDs: broker=1, data=2, feed=3 (default)
4. Check `SA_BROKER__IBKR__CLIENT_ID` environment variable

---

### "No security definition found for"

**Symptom:**
```
ERROR: No security definition found for symbol XYZ
```

**Causes:**
1. Invalid ticker symbol
2. Symbol not traded on SMART routing
3. Delisted stock

**Solutions:**
1. Verify ticker spelling (use IBKR's primary symbol)
2. Check symbol on IBKR TWS → Symbol search
3. Remove delisted symbols from universe

---

### IB Gateway not reachable

**Symptom:**
```
ERROR: ibkr_gateway.not_connected - system is running in degraded mode
```

**Diagnosis:**
1. Is IB Gateway running?
2. Check Gateway status indicator (should be green "Ready")
3. Check port configuration (paper=4002, live=4001)

**Solutions:**
1. Start IB Gateway and wait for "Ready" status
2. Verify port in `.env`: `SA_BROKER__IBKR__PORT=4002`
3. Check firewall allows localhost connections
4. Restart IB Gateway if stuck in "Connecting..." state

---

### Delayed market data

**Symptom:** Prices are 15 minutes behind

**Cause:** No real-time market data subscription

**Expected in paper trading:** Delayed data is normal without subscription

**Solution for live trading:**
1. Log in to IBKR Account Management
2. Navigate to Market Data Subscriptions
3. Subscribe to "US Equity and Options Add-On Streaming Bundle" (~$10/mo)

---

### Connection drops at 4pm ET

**Symptom:** Feed disconnects every day at market close

**Cause:** Expected behavior — IBKR closes connections at 4pm ET

**Solution:** System auto-reconnects. Check logs for:
```
system:feed:disconnected
system:feed:reconnected
```

No action needed. This is normal.

---

## Test Failures

### Tests fail with import errors

**Symptom:**
```
AttributeError: <module 'src.data.storage'> has no attribute 'TimeSeriesStorage'
```

**Cause:** Lazy imports in job functions not patched correctly

**Solution:** Patch at source module path:
```python
# WRONG
@patch('src.scheduling.jobs.TimeSeriesStorage')

# CORRECT
@patch('src.data.storage.TimeSeriesStorage')
```

**Rule:** Patch where the object is **imported from**, not where it's **used**.

---

### PDT guard rejecting all orders

**Symptom:** All BUY orders rejected with PDT warning

**Diagnosis:**
```bash
# Check day trade count
docker exec -it alpha-oracle-redis-1 redis-cli ZCARD risk:pdt:trades
```

**Causes:**
1. Account under $25K → PDT rules apply
2. 3+ day trades in last 5 business days → At limit
3. Redis key corrupted → Contains invalid dates

**Solutions:**
1. Wait for old trades to expire (7 days)
2. Increase `min_hold_days` to 3+ in strategies
3. Clear Redis (development only): `redis-cli DEL risk:pdt:trades`

**NEVER disable PDT guard in production.**

---

## Kill Switch Issues

### Kill switch stuck in active state

**Symptom:** Trading halted, cannot resume

**Diagnosis:**
```bash
# Check Redis key
docker exec -it alpha-oracle-redis-1 redis-cli GET risk:kill_switch

# Check database
docker exec -it alpha-oracle-timescaledb-1 psql -U trader -d stock_analysis
SELECT * FROM kill_switch;
```

**Solutions:**
1. Use dashboard kill switch modal with "RESUME" confirmation
2. Manual override (development only):
   ```bash
   docker exec -it alpha-oracle-redis-1 redis-cli SET risk:kill_switch inactive
   ```
3. Database update (development only):
   ```sql
   UPDATE kill_switch SET active = FALSE, deactivated_at = NOW();
   ```

**In production:** Always use proper deactivation flow (dashboard or API) for audit trail.

---

## Data Quality Issues

### Stale data alerts

**Symptom:** Circuit breaker activates due to stale data

**Causes:**
1. Market feed disconnected
2. No recent bar ingestion
3. Scheduler job failed

**Diagnosis:**
```bash
# Check feed status
curl http://localhost:8000/api/system/health

# Check latest bars
docker exec -it alpha-oracle-timescaledb-1 psql -U trader -d stock_analysis
SELECT symbol, MAX(timestamp) FROM ohlcv GROUP BY symbol ORDER BY MAX(timestamp) DESC LIMIT 10;

# Check scheduler logs
grep "daily_bars_job" logs/backend.log
```

**Solutions:**
1. Restart market feed (restart backend)
2. Manually trigger job: `POST /api/system/scheduler/trigger/daily_bars`
3. Check Alpha Vantage API key and rate limits

---

### Missing fundamental data

**Symptom:** Strategies fail due to missing PE ratio, etc.

**Cause:** Alpha Vantage does not provide fundamentals for all symbols

**Solutions:**
1. Check if symbol is excluded: `grep "fundamentals.symbol_error" logs/backend.log`
2. Manually trigger job: `POST /api/system/scheduler/trigger/weekly_fundamentals`
3. Some symbols (ETFs, foreign stocks) don't have fundamentals → Strategy should handle `None`

---

## Frontend Issues

### Frontend not loading

**Symptom:** Blank page or "Cannot GET /" error

**Diagnosis:**
```bash
# Check if Vite is running
ps aux | grep vite

# Check PID file
cat .pids/frontend.pid

# Check logs
tail -f logs/frontend.log
```

**Solutions:**
1. Frontend not started → `./scripts/start-frontend.sh`
2. Port conflict (3000) → Kill conflicting process
3. Build error → Check `logs/frontend.log`, run `npm run lint`

---

### API proxy not working

**Symptom:** API calls fail with CORS errors or 404

**Cause:** Vite proxy misconfigured or backend not reachable

**Diagnosis:**
```bash
# Check Vite config
cat web/vite.config.ts

# Should contain:
# proxy: {
#   '/api': 'http://localhost:8000',
# }

# Check backend
curl http://localhost:8000/api/portfolio
```

**Solutions:**
1. Restart Vite dev server
2. Check backend is running on port 8000
3. Verify proxy config in `vite.config.ts`

---

### WebSocket disconnected

**Symptom:** Dashboard shows "Disconnected" status

**Diagnosis:**
```bash
# Check WebSocket endpoint
curl http://localhost:8000/ws
# Should return "Method Not Allowed"

# Check backend logs
grep "WebSocket" logs/backend.log
```

**Solutions:**
1. Backend not running → Start backend
2. Redis not running → Start Redis
3. Browser console shows error → Check for JavaScript errors

**Auto-reconnect:** Frontend automatically reconnects after 3 seconds.

---

## Performance Issues

### Slow API responses

**Symptom:** Dashboard takes 5+ seconds to load

**Diagnosis:**
```bash
# Check database query time
docker exec -it alpha-oracle-timescaledb-1 psql -U trader -d stock_analysis
\timing on
SELECT * FROM ohlcv WHERE symbol = 'AAPL' AND timestamp > NOW() - INTERVAL '1 year';

# Check backend logs for slow queries
grep "slow_query" logs/backend.log
```

**Solutions:**
1. Add indexes on frequently queried columns
2. Reduce time range for historical queries
3. Implement caching for portfolio snapshots
4. Check TimescaleDB chunk compression settings

---

### High memory usage

**Symptom:** System uses 8GB+ RAM

**Causes:**
1. Large dataset in memory (pandas DataFrames)
2. Redis cache growing unbounded
3. Leaked WebSocket connections

**Solutions:**
1. Use Polars instead of pandas for large datasets
2. Configure Redis max memory: `maxmemory 512mb`
3. Set TTL on cache keys
4. Restart services periodically

---

## Getting Help

If troubleshooting steps don't resolve the issue:

1. **Check logs:** `logs/backend.log`, `logs/frontend.log`
2. **Check Docker logs:** `docker compose logs`
3. **Enable debug logging:** Set `SA_ENVIRONMENT=development` in `.env`
4. **Run tests:** `pytest tests/ -v -s` (verbose + print output)
5. **File an issue:** https://github.com/anthropics/claude-code/issues (with logs, config, steps to reproduce)

**Provide in issue report:**
- System version (git commit hash)
- Environment (development/paper/live)
- Full error message and stack trace
- Relevant log excerpts
- Steps to reproduce

---

<!-- DIAGRAM: Troubleshooting decision tree for common error categories -->
