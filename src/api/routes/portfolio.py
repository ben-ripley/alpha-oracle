from __future__ import annotations

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Query

from src.api.dependencies import get_broker, get_storage
from src.core.models import PortfolioSnapshot, Position

router = APIRouter()


@router.get("/snapshot", response_model=PortfolioSnapshot)
async def get_portfolio_snapshot():
    """Get current portfolio snapshot including all positions."""
    broker = await get_broker()
    return await broker.get_portfolio()


@router.get("/positions", response_model=list[Position])
async def get_positions():
    """Get all current positions."""
    broker = await get_broker()
    return await broker.get_positions()


@router.get("/history")
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365),
):
    """Get portfolio value history for charting."""
    storage = await get_storage()
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    snapshots = await storage.get_portfolio_snapshots(start, end)
    if snapshots:
        return {
            "snapshots": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "total_equity": s.total_equity,
                    "cash": s.cash,
                    "positions_value": s.positions_value,
                    "daily_pnl": s.daily_pnl,
                    "daily_pnl_pct": s.daily_pnl_pct,
                    "total_pnl": s.total_pnl,
                    "total_pnl_pct": s.total_pnl_pct,
                    "max_drawdown_pct": s.max_drawdown_pct,
                }
                for s in snapshots
            ]
        }

    # Fall back to Redis seed data
    try:
        from src.core.redis import get_redis
        r = await get_redis()
        raw = await r.get("portfolio:history")
        if raw:
            all_history = json.loads(raw)
            cutoff = start.isoformat()
            return {"snapshots": [s for s in all_history if s["timestamp"] >= cutoff][-days:]}
    except Exception:
        pass
    return {"snapshots": []}


@router.get("/allocation")
async def get_allocation():
    """Get current portfolio allocation by sector and position."""
    broker = await get_broker()
    portfolio = await broker.get_portfolio()

    position_allocation = [
        {
            "symbol": p.symbol,
            "market_value": p.market_value,
            "pct": (p.market_value / portfolio.total_equity * 100) if portfolio.total_equity > 0 else 0,
            "unrealized_pnl": p.unrealized_pnl,
            "sector": p.sector,
        }
        for p in portfolio.positions
    ]

    sector_allocation = {}
    for p in portfolio.positions:
        sector = p.sector or "Unknown"
        sector_allocation[sector] = sector_allocation.get(sector, 0) + p.market_value

    sector_pcts = {
        k: (v / portfolio.total_equity * 100) if portfolio.total_equity > 0 else 0
        for k, v in sector_allocation.items()
    }

    return {
        "total_equity": portfolio.total_equity,
        "cash": portfolio.cash,
        "cash_pct": (portfolio.cash / portfolio.total_equity * 100) if portfolio.total_equity > 0 else 100,
        "positions": position_allocation,
        "sectors": sector_pcts,
    }
