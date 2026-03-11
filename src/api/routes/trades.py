from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.api.dependencies import get_execution_engine

router = APIRouter()


class TradeApprovalRequest(BaseModel):
    order_id: str
    action: str  # "approve" or "reject"
    reason: str = ""


@router.get("/history")
async def get_trade_history(
    symbol: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get trade history with optional filters."""
    engine = await get_execution_engine()
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    trades = await engine.tracker.get_trade_history(
        symbol=symbol, start=start, end=end, limit=limit,
    )
    return {"trades": [t.model_dump() for t in trades]}


@router.get("/open-orders")
async def get_open_orders():
    """Get all currently open orders."""
    engine = await get_execution_engine()
    orders = await engine.tracker.get_open_orders()
    return {"orders": [o.model_dump() for o in orders]}


@router.get("/pending-approvals")
async def get_pending_approvals():
    """Get orders pending human approval (MANUAL_APPROVAL mode)."""
    engine = await get_execution_engine()
    pending = await engine.get_pending_approvals()
    return {"pending": [o.model_dump() for o in pending]}


@router.post("/approve")
async def approve_or_reject_trade(request: TradeApprovalRequest):
    """Approve or reject a pending trade."""
    engine = await get_execution_engine()
    if request.action == "approve":
        order = await engine.approve_pending_order(request.order_id)
        return {"status": "approved", "order": order.model_dump()}
    elif request.action == "reject":
        await engine.reject_pending_order(request.order_id, request.reason)
        return {"status": "rejected", "order_id": request.order_id, "reason": request.reason}
    else:
        return {"status": "error", "message": f"Invalid action: {request.action}"}


@router.get("/execution-quality")
async def get_execution_quality(days: int = Query(default=30, ge=1, le=365)):
    """Get execution quality metrics (slippage, fill rates)."""
    engine = await get_execution_engine()
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    metrics = await engine.tracker.get_execution_quality(start, end)
    return metrics


@router.get("/daily-summary")
async def get_daily_summary():
    """Get today's trading summary."""
    engine = await get_execution_engine()
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    trades = await engine.tracker.get_trade_history(
        start=today_start, end=datetime.utcnow(),
    )

    total_pnl = sum(t.pnl for t in trades)
    winners = [t for t in trades if t.pnl > 0]
    losers = [t for t in trades if t.pnl < 0]

    return {
        "date": today_start.date().isoformat(),
        "total_trades": len(trades),
        "winning_trades": len(winners),
        "losing_trades": len(losers),
        "total_pnl": round(total_pnl, 2),
        "best_trade": max((t.pnl for t in trades), default=0),
        "worst_trade": min((t.pnl for t in trades), default=0),
    }
