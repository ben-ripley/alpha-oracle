from __future__ import annotations

from datetime import datetime

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
    strategies = engine.get_registered_strategies()
    return {
        "strategies": [
            {
                "name": s.name,
                "description": s.description,
                "min_hold_days": s.min_hold_days,
                "parameters": s.get_parameters(),
                "required_data": s.get_required_data(),
            }
            for s in strategies
        ]
    }


@router.get("/rankings", response_model=list[StrategyRanking])
async def get_strategy_rankings():
    """Get current strategy rankings by composite score."""
    engine = await get_strategy_engine()
    return engine.get_latest_rankings()


@router.post("/backtest", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest):
    """Run a backtest for a specific strategy."""
    engine = await get_strategy_engine()
    end_date = (
        datetime.fromisoformat(request.end_date) if request.end_date
        else datetime.utcnow()
    )
    result = await engine.run_backtest_async(
        strategy_name=request.strategy_name,
        symbols=request.symbols,
        initial_capital=request.initial_capital,
        start=datetime.fromisoformat(request.start_date),
        end=end_date,
    )
    return result


@router.get("/backtest/results")
async def get_backtest_results(
    strategy_name: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Get stored backtest results."""
    engine = await get_strategy_engine()
    results = engine.get_stored_results(strategy_name=strategy_name, limit=limit)
    return {"results": results}


@router.get("/{strategy_name}/performance")
async def get_strategy_performance(strategy_name: str):
    """Get live vs backtest performance comparison for a strategy."""
    engine = await get_strategy_engine()
    return await engine.get_performance_comparison(strategy_name)
