"""Seed Redis with realistic demo data for manual UI testing.

Run inside the Docker container:
    docker-compose exec api python scripts/seed_demo_data.py

Or locally (requires Redis running on localhost:6379):
    python scripts/seed_demo_data.py
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta

import redis.asyncio as aioredis

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

REDIS_URL = "redis://localhost:6379/0"


async def get_redis() -> aioredis.Redis:
    # Try Docker-internal hostname first, then localhost
    for url in ["redis://redis:6379/0", REDIS_URL]:
        try:
            r = aioredis.from_url(url, decode_responses=True)
            await r.ping()
            print(f"Connected to Redis at {url}")
            return r
        except Exception:
            pass
    raise RuntimeError("Could not connect to Redis at redis:6379 or localhost:6379")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

NOW = datetime.now(UTC)


def dt(days_ago: float, hour: int = 10, minute: int = 0) -> str:
    return (NOW - timedelta(days=days_ago)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    ).isoformat()


TRADE_HISTORY = [
    {
        "id": "T001", "symbol": "NVDA", "side": "BUY", "quantity": 10,
        "entry_price": 875.50, "exit_price": 912.30,
        "entry_time": dt(5, 14, 30), "exit_time": dt(1, 15, 45),
        "pnl": 368.00, "pnl_pct": 4.20, "strategy_name": "swing_momentum",
        "hold_duration_days": 4.05, "is_day_trade": False,
    },
    {
        "id": "T002", "symbol": "AAPL", "side": "BUY", "quantity": 15,
        "entry_price": 178.50, "exit_price": None,
        "entry_time": dt(4, 10, 15), "exit_time": None,
        "pnl": 70.50, "pnl_pct": 2.63, "strategy_name": "swing_momentum",
        "hold_duration_days": 4.0, "is_day_trade": False,
    },
    {
        "id": "T003", "symbol": "META", "side": "BUY", "quantity": 6,
        "entry_price": 502.80, "exit_price": 495.20,
        "entry_time": dt(7, 11, 0), "exit_time": dt(4, 14, 30),
        "pnl": -45.60, "pnl_pct": -1.51, "strategy_name": "mean_reversion",
        "hold_duration_days": 3.15, "is_day_trade": False,
    },
    {
        "id": "T004", "symbol": "MSFT", "side": "BUY", "quantity": 8,
        "entry_price": 415.00, "exit_price": None,
        "entry_time": dt(2, 9, 45), "exit_time": None,
        "pnl": 62.40, "pnl_pct": 1.88, "strategy_name": "mean_reversion",
        "hold_duration_days": 2.0, "is_day_trade": False,
    },
    {
        "id": "T005", "symbol": "GOOG", "side": "BUY", "quantity": 12,
        "entry_price": 165.40, "exit_price": 170.15,
        "entry_time": dt(8, 13, 20), "exit_time": dt(5, 15, 50),
        "pnl": 57.00, "pnl_pct": 2.87, "strategy_name": "swing_momentum",
        "hold_duration_days": 3.10, "is_day_trade": False,
    },
    {
        "id": "T006", "symbol": "JPM", "side": "BUY", "quantity": 12,
        "entry_price": 195.20, "exit_price": None,
        "entry_time": dt(3, 10, 30), "exit_time": None,
        "pnl": -37.20, "pnl_pct": -1.59, "strategy_name": "value_factor",
        "hold_duration_days": 3.0, "is_day_trade": False,
    },
    {
        "id": "T007", "symbol": "AMD", "side": "BUY", "quantity": 20,
        "entry_price": 142.30, "exit_price": 151.80,
        "entry_time": dt(14, 9, 30), "exit_time": dt(11, 15, 0),
        "pnl": 190.00, "pnl_pct": 6.68, "strategy_name": "swing_momentum",
        "hold_duration_days": 3.23, "is_day_trade": False,
    },
    {
        "id": "T008", "symbol": "COST", "side": "BUY", "quantity": 5,
        "entry_price": 698.40, "exit_price": 712.60,
        "entry_time": dt(18, 10, 15), "exit_time": dt(15, 14, 30),
        "pnl": 71.00, "pnl_pct": 2.03, "strategy_name": "value_factor",
        "hold_duration_days": 3.18, "is_day_trade": False,
    },
    {
        "id": "T009", "symbol": "TSLA", "side": "BUY", "quantity": 8,
        "entry_price": 248.60, "exit_price": 239.10,
        "entry_time": dt(22, 11, 0), "exit_time": dt(19, 15, 45),
        "pnl": -76.00, "pnl_pct": -3.82, "strategy_name": "mean_reversion",
        "hold_duration_days": 3.20, "is_day_trade": False,
    },
    {
        "id": "T010", "symbol": "AMZN", "side": "BUY", "quantity": 10,
        "entry_price": 182.40, "exit_price": 191.20,
        "entry_time": dt(25, 9, 45), "exit_time": dt(22, 14, 0),
        "pnl": 88.00, "pnl_pct": 4.82, "strategy_name": "swing_momentum",
        "hold_duration_days": 3.18, "is_day_trade": False,
    },
]

PENDING_APPROVALS = [
    {
        "id": "P001", "symbol": "AMZN", "side": "BUY",
        "order_type": "LIMIT", "quantity": 5, "limit_price": 188.50,
        "stop_price": None, "take_profit_price": None,
        "status": "PENDING", "strategy_name": "swing_momentum",
        "signal_strength": 0.78, "created_at": dt(0, 9, 32),
        "filled_at": None, "filled_price": None,
        "filled_quantity": None, "broker_order_id": "",
        "metadata": {"approval_reasons": ["MANUAL_APPROVAL mode: requires human sign-off"]},
    },
    {
        "id": "P002", "symbol": "TSLA", "side": "SELL",
        "order_type": "LIMIT", "quantity": 8, "limit_price": 245.00,
        "stop_price": None, "take_profit_price": None,
        "status": "PENDING", "strategy_name": "mean_reversion",
        "signal_strength": 0.65, "created_at": dt(0, 9, 35),
        "filled_at": None, "filled_price": None,
        "filled_quantity": None, "broker_order_id": "",
        "metadata": {"approval_reasons": ["MANUAL_APPROVAL mode: requires human sign-off"]},
    },
]

# One PDT day trade from 2 business days ago
PDT_TRADE = {
    "symbol": "NVDA",
    "date": (date.today() - timedelta(days=2)).isoformat(),
    "recorded_at": (NOW - timedelta(days=2)).isoformat(),
    "order_id": "demo-pdt-001",
}

BACKTEST_RESULTS = {
    "swing_momentum": {
        "strategy_name": "swing_momentum",
        "start_date": (NOW - timedelta(days=365)).isoformat(),
        "end_date": NOW.isoformat(),
        "initial_capital": 20000.0,
        "final_capital": 26480.0,
        "total_return_pct": 32.4,
        "annual_return_pct": 32.4,
        "sharpe_ratio": 1.42,
        "sortino_ratio": 1.78,
        "max_drawdown_pct": 12.3,
        "profit_factor": 1.82,
        "total_trades": 247,
        "winning_trades": 144,
        "losing_trades": 103,
        "win_rate": 58.3,
        "avg_win_pct": 3.2,
        "avg_loss_pct": -1.8,
        "equity_curve": [
            {"date": (NOW - timedelta(days=365 - i * 7)).strftime("%Y-%m-%d"),
             "equity": round(20000 + i * 120 + (i % 5) * 80 - (i % 7) * 40, 2)}
            for i in range(52)
        ],
        "trades": [],
        "metadata": {},
    },
    "mean_reversion": {
        "strategy_name": "mean_reversion",
        "start_date": (NOW - timedelta(days=365)).isoformat(),
        "end_date": NOW.isoformat(),
        "initial_capital": 20000.0,
        "final_capital": 24220.0,
        "total_return_pct": 21.1,
        "annual_return_pct": 21.1,
        "sharpe_ratio": 1.28,
        "sortino_ratio": 1.55,
        "max_drawdown_pct": 14.8,
        "profit_factor": 1.67,
        "total_trades": 312,
        "winning_trades": 195,
        "losing_trades": 117,
        "win_rate": 62.5,
        "avg_win_pct": 2.4,
        "avg_loss_pct": -1.9,
        "equity_curve": [
            {"date": (NOW - timedelta(days=365 - i * 7)).strftime("%Y-%m-%d"),
             "equity": round(20000 + i * 95 + (i % 6) * 60 - (i % 8) * 50, 2)}
            for i in range(52)
        ],
        "trades": [],
        "metadata": {},
    },
    "value_factor": {
        "strategy_name": "value_factor",
        "start_date": (NOW - timedelta(days=365)).isoformat(),
        "end_date": NOW.isoformat(),
        "initial_capital": 20000.0,
        "final_capital": 22120.0,
        "total_return_pct": 10.6,
        "annual_return_pct": 10.6,
        "sharpe_ratio": 0.89,
        "sortino_ratio": 1.02,
        "max_drawdown_pct": 18.5,
        "profit_factor": 1.35,
        "total_trades": 156,
        "winning_trades": 85,
        "losing_trades": 71,
        "win_rate": 54.5,
        "avg_win_pct": 3.8,
        "avg_loss_pct": -2.9,
        "equity_curve": [
            {"date": (NOW - timedelta(days=365 - i * 7)).strftime("%Y-%m-%d"),
             "equity": round(20000 + i * 60 + (i % 9) * 70 - (i % 6) * 55, 2)}
            for i in range(52)
        ],
        "trades": [],
        "metadata": {},
    },
}

STRATEGY_RANKINGS = [
    {
        "strategy_name": "swing_momentum",
        "composite_score": 78.4,
        "sharpe_ratio": 1.42,
        "sortino_ratio": 1.78,
        "max_drawdown_pct": 12.3,
        "profit_factor": 1.82,
        "consistency_score": 0.74,
        "total_trades": 247,
        "win_rate": 58.3,
        "meets_thresholds": True,
        "ranked_at": NOW.isoformat(),
    },
    {
        "strategy_name": "mean_reversion",
        "composite_score": 72.1,
        "sharpe_ratio": 1.28,
        "sortino_ratio": 1.55,
        "max_drawdown_pct": 14.8,
        "profit_factor": 1.67,
        "consistency_score": 0.68,
        "total_trades": 312,
        "win_rate": 62.5,
        "meets_thresholds": True,
        "ranked_at": NOW.isoformat(),
    },
    {
        "strategy_name": "value_factor",
        "composite_score": 55.2,
        "sharpe_ratio": 0.89,
        "sortino_ratio": 1.02,
        "max_drawdown_pct": 18.5,
        "profit_factor": 1.35,
        "consistency_score": 0.52,
        "total_trades": 156,
        "win_rate": 54.5,
        "meets_thresholds": False,
        "ranked_at": NOW.isoformat(),
    },
]

# Portfolio history: 30 daily equity snapshots
PORTFOLIO_HISTORY = [
    {
        "timestamp": (NOW - timedelta(days=29 - i)).strftime("%Y-%m-%dT%H:%M:%S"),
        "total_equity": round(20000 + i * 50 + (i % 5) * 80 - (i % 7) * 40, 2),
        "cash": 8819.72,
        "positions_value": round(11000 + i * 50, 2),
        "daily_pnl": round((i % 3 - 1) * 45 + (i % 5) * 20, 2),
        "daily_pnl_pct": round(((i % 3 - 1) * 45 + (i % 5) * 20) / (20000 + i * 50) * 100, 3),
        "total_pnl": round(i * 50 + (i % 5) * 80 - (i % 7) * 40, 2),
        "total_pnl_pct": round((i * 50 + (i % 5) * 80 - (i % 7) * 40) / 20000 * 100, 3),
        "max_drawdown_pct": round(min(i * 0.1 + 1.5, 4.2), 2),
    }
    for i in range(30)
]


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

async def seed(r: aioredis.Redis) -> None:
    print("\nSeeding demo data into Redis...")

    # 1. Trade history
    await r.delete("execution:trade_history")
    for symbol in set(t["symbol"] for t in TRADE_HISTORY):
        await r.delete(f"execution:trade_history:{symbol}")

    for trade in TRADE_HISTORY:
        payload = json.dumps(trade)
        await r.rpush("execution:trade_history", payload)
        await r.rpush(f"execution:trade_history:{trade['symbol']}", payload)
    print(f"  ✓ {len(TRADE_HISTORY)} trade records")

    # 2. Pending approval orders
    await r.delete("execution:pending_approvals")
    for order in PENDING_APPROVALS:
        await r.hset("execution:pending_approvals", order["id"], json.dumps(order))
    print(f"  ✓ {len(PENDING_APPROVALS)} pending approvals")

    # 3. PDT day trade record
    await r.delete("risk:pdt:trades")
    entry_date = date.today() - timedelta(days=2)
    await r.zadd("risk:pdt:trades", {json.dumps(PDT_TRADE): entry_date.toordinal()})
    print("  ✓ 1 PDT day trade (1/3 used)")

    # 4. Strategy backtest results
    for name, result in BACKTEST_RESULTS.items():
        await r.set(f"strategy:results:{name}", json.dumps(result))
    print(f"  ✓ {len(BACKTEST_RESULTS)} backtest results")

    # 5. Strategy rankings
    await r.set("strategy:rankings", json.dumps(STRATEGY_RANKINGS))
    print(f"  ✓ {len(STRATEGY_RANKINGS)} strategy rankings")

    # 6. Portfolio history
    await r.set("portfolio:history", json.dumps(PORTFOLIO_HISTORY))
    print(f"  ✓ {len(PORTFOLIO_HISTORY)} portfolio history snapshots")

    # 7. Operator heartbeat (so dead man's switch doesn't trip)
    await r.set("circuit_breaker:heartbeat", NOW.isoformat())
    print("  ✓ Operator heartbeat recorded")

    print("\nDone! Restart the API to pick up strategy data:")
    print("  docker-compose restart api")


async def main() -> None:
    r = await get_redis()
    try:
        await seed(r)
    finally:
        await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
