from __future__ import annotations

import json

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.api.dependencies import get_strategy_engine
from src.core.models import BacktestResult, StrategyRanking

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_name: str
    symbols: list[str]
    start_date: str
    end_date: str | None = None
    initial_capital: float = 20000.0


@router.get("/list")
async def list_strategies():
    """List all registered strategies with their parameters."""
    engine = await get_strategy_engine()
    return {
        "strategies": [
            {
                "name": name,
                "description": engine.get_strategy(name).description,
                "min_hold_days": engine.get_strategy(name).min_hold_days,
                "parameters": engine.get_strategy(name).get_parameters(),
                "required_data": engine.get_strategy(name).get_required_data(),
            }
            for name in engine.list_strategies()
        ]
    }


@router.get("/rankings")
async def get_strategy_rankings():
    """Get current strategy rankings. Falls back to Redis-cached seed data."""
    from src.core.redis import get_redis
    engine = await get_strategy_engine()

    # Try in-memory rankings first
    live = engine.rank_all()
    if live:
        return live

    # Fall back to Redis seed data
    try:
        r = await get_redis()
        raw = await r.get("strategy:rankings")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return []


@router.post("/backtest")
async def run_backtest(request: BacktestRequest):
    """Run a backtest for a specific strategy. Requires data to be loaded first."""
    return {
        "status": "not_implemented",
        "message": "Backtest via API requires data ingestion (Phase 2). Use the strategy engine directly.",
    }


@router.get("/backtest/results")
async def get_backtest_results(
    strategy_name: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get stored backtest results. Falls back to Redis-cached seed data."""
    import json as _json
    from src.core.redis import get_redis
    engine = await get_strategy_engine()

    # Try in-memory results first
    results = [
        r.model_dump() for name, r in engine._results.items()
        if not strategy_name or name == strategy_name
    ]
    if results:
        return {"results": results[:limit]}

    # Fall back to Redis seed data
    try:
        r = await get_redis()
        if strategy_name:
            raw = await r.get(f"strategy:results:{strategy_name}")
            results = [_json.loads(raw)] if raw else []
        else:
            keys = await r.keys("strategy:results:*")
            results = []
            for key in keys:
                raw = await r.get(key)
                if raw:
                    results.append(_json.loads(raw))
    except Exception:
        results = []
    return {"results": results[:limit]}


@router.get("/{strategy_name}/performance")
async def get_strategy_performance(strategy_name: str):
    """Get backtest performance for a strategy."""
    import json as _json
    from src.core.redis import get_redis
    engine = await get_strategy_engine()
    try:
        strategy = engine.get_strategy(strategy_name)
    except KeyError:
        return {"error": f"Strategy '{strategy_name}' not registered"}

    result = engine._results.get(strategy_name)
    if result:
        return {"strategy": strategy_name, "description": strategy.description, "backtest": result.model_dump()}

    # Fall back to Redis
    try:
        r = await get_redis()
        raw = await r.get(f"strategy:results:{strategy_name}")
        if raw:
            return {"strategy": strategy_name, "description": strategy.description, "backtest": _json.loads(raw)}
    except Exception:
        pass
    return {"strategy": strategy_name, "description": strategy.description, "backtest": None}
