# ADR-005: Backtesting - Backtrader + VectorBT

**Status:** Accepted

**Decision:** Backtrader for event-driven backtesting, VectorBT for rapid parameter optimization.

| Framework | Strength | Use Case |
|---|---|---|
| Backtrader (20.7K stars) | Realistic execution model, broker simulation, 122 indicators | Primary backtesting, strategy validation |
| VectorBT (~4K stars) | 20,000 parameter configs in <30s | Parameter sweeps, optimization |
| QuantConnect Lean (38.6K stars) | Professional-grade, multi-asset | Future upgrade if needed |

**Non-negotiable validation protocol:**
1. Walk-forward analysis (train on [t-N, t], test on [t, t+M], slide forward)
2. Out-of-sample holdout (reserve most recent 20%, touch once)
3. Monte Carlo simulation (randomize trade order/timing)
4. Transaction cost modeling (slippage + spread even at $0 commission)
5. Survivorship bias check (include delisted stocks)
6. Paper trading minimum 30 days before live capital
7. Minimum thresholds: Sharpe > 1.0, max drawdown < 20%, profit factor > 1.5, 100+ trades

**Strategy ranking formula:** Sharpe (30%) + Sortino (20%) + max drawdown inverse (20%) + profit factor (15%) + consistency across time periods (15%)

---

## Amendment: Non-Blocking Backtest API (2026-03-14)

**Decision:** Expose backtesting as an async background job via `POST /api/strategies/backtest` rather than a synchronous endpoint, to support multi-symbol runs (up to full S&P 500) without blocking the API server.

**Architecture:**
- CPU-bound `BacktraderEngine.run()` executes in a module-level `ThreadPoolExecutor(max_workers=2)` via `asyncio.get_running_loop().run_in_executor()`
- API handler loads OHLCV for all symbols via `asyncio.gather`, creates a Redis job record (`backtest:job:{uuid}`, 1h TTL), then returns immediately with `{job_id, estimated_seconds}`
- Background thread uses a synchronous Redis client (`redis.from_url`) — cannot share the async client across thread boundary
- Completed results written to `strategy:results:{strategy_name}` (no TTL) for consumption by `GET /backtest/results`

**Position sizing decision:** Replaced `cash * 0.95 / close` (order-dependent, first symbol consumes most capital) with equal-weight `initial_capital / max_positions` per slot. Capacity cap skips buy signals when `len(_entry_bars) >= max_positions`. `max_positions` sourced from `risk_limits.yaml` so backtest reflects the same constraint as live trading.

**Progress estimation:** Redis key `backtest:timing:ms_per_symbol` stores a rolling average (weight 10%) calibrated from real runs. Frontend uses elapsed-time vs `estimated_seconds` to drive an artificial progress bar capped at 95% until the job completes. Fallback: 50 ms/symbol.

**Route ordering:** `GET /backtest/jobs/{job_id}` registered before `GET /{strategy_name}/performance` wildcard to prevent FastAPI capturing `jobs` as a strategy name.
