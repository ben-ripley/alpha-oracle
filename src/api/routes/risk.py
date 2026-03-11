from __future__ import annotations

from fastapi import APIRouter

from src.api.dependencies import get_risk_manager, get_broker
from src.core.models import AutonomyMode

router = APIRouter()


@router.get("/dashboard")
async def get_risk_dashboard():
    """Get comprehensive risk dashboard data."""
    risk_mgr = await get_risk_manager()
    broker = await get_broker()
    portfolio = await broker.get_portfolio()
    context = await risk_mgr.circuit_breakers.build_context_from_redis(portfolio=portfolio)
    await risk_mgr.circuit_breakers.check_all(context)
    return await risk_mgr.get_risk_dashboard(portfolio)


@router.get("/limits")
async def get_risk_limits():
    """Get current risk limit configuration and utilization."""
    risk_mgr = await get_risk_manager()
    broker = await get_broker()
    portfolio = await broker.get_portfolio()

    metrics = await risk_mgr.portfolio_monitor.get_risk_metrics(portfolio)
    config = risk_mgr.settings

    return {
        "position_limits": {
            "max_position_pct": config.position_limits.max_position_pct,
            "max_sector_pct": config.position_limits.max_sector_pct,
            "stop_loss_pct": config.position_limits.stop_loss_pct,
            "min_price": config.position_limits.min_price,
        },
        "portfolio_limits": {
            "max_drawdown_pct": config.portfolio_limits.max_drawdown_pct,
            "current_drawdown_pct": metrics.get("current_drawdown_pct", 0),
            "max_daily_loss_pct": config.portfolio_limits.max_daily_loss_pct,
            "current_daily_pnl_pct": metrics.get("daily_pnl_pct", 0),
            "max_positions": config.portfolio_limits.max_positions,
            "current_positions": len(portfolio.positions),
            "min_cash_reserve_pct": config.portfolio_limits.min_cash_reserve_pct,
            "current_cash_pct": metrics.get("cash_reserve_pct", 100),
        },
        "pdt": {
            "day_trades_used": metrics.get("pdt_trades_used", 0),
            "day_trades_max": metrics.get("pdt_max", config.pdt_guard.max_day_trades),
            "max_day_trades": config.pdt_guard.max_day_trades,
            "rolling_window_days": config.pdt_guard.rolling_window_days,
            "enabled": config.pdt_guard.enabled,
        },
    }


@router.get("/circuit-breakers")
async def get_circuit_breaker_status():
    """Get status of all circuit breakers."""
    risk_mgr = await get_risk_manager()
    broker = await get_broker()
    portfolio = await broker.get_portfolio()
    context = await risk_mgr.circuit_breakers.build_context_from_redis(portfolio=portfolio)
    breakers = await risk_mgr.circuit_breakers.check_all(context)
    return {
        "breakers": [
            {"name": name, "tripped": tripped, "reason": reason}
            for name, tripped, reason in breakers
        ],
        "any_tripped": any(tripped for _, tripped, _ in breakers),
    }


@router.get("/autonomy-mode")
async def get_autonomy_mode():
    """Get current autonomy mode."""
    risk_mgr = await get_risk_manager()
    return {
        "mode": risk_mgr.settings.autonomy_mode,
        "modes_available": [m.value for m in AutonomyMode],
    }


@router.post("/kill-switch/activate")
async def activate_kill_switch(reason: str = "Manual activation via API"):
    """Activate the kill switch - cancels all open orders and halts trading."""
    risk_mgr = await get_risk_manager()
    await risk_mgr.activate_kill_switch(reason)
    return {"status": "activated", "reason": reason}


@router.post("/kill-switch/deactivate")
async def deactivate_kill_switch():
    """Deactivate the kill switch after cooldown period."""
    risk_mgr = await get_risk_manager()
    try:
        await risk_mgr.kill_switch.deactivate()
        return {"status": "deactivated"}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@router.get("/kill-switch/status")
async def get_kill_switch_status():
    """Get kill switch status."""
    risk_mgr = await get_risk_manager()
    active = await risk_mgr.is_kill_switch_active()
    return {"active": active}
