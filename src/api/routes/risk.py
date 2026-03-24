from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_broker, get_risk_manager
from src.core.models import AutonomyMode

router = APIRouter()


class TransitionRequest(BaseModel):
    target_mode: str
    days_in_mode: int = 0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    circuit_breakers_tested: bool = False
    confirmation: str = ""


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
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/kill-switch/status")
async def get_kill_switch_status():
    """Get kill switch status."""
    risk_mgr = await get_risk_manager()
    active = await risk_mgr.is_kill_switch_active()
    return {"active": active}


@router.get("/autonomy-mode/readiness")
async def get_autonomy_mode_readiness():
    """Check readiness for each possible autonomy mode transition."""
    from datetime import datetime

    from src.core.redis import get_redis
    from src.risk.autonomy_validator import AutonomyValidator

    risk_mgr = await get_risk_manager()
    broker = await get_broker()
    current_mode_str = risk_mgr.settings.autonomy_mode
    try:
        current_mode = AutonomyMode(current_mode_str)
    except ValueError:
        current_mode = AutonomyMode.PAPER_ONLY

    # Fetch real portfolio metrics
    portfolio = await broker.get_portfolio()
    metrics_raw = await risk_mgr.portfolio_monitor.get_risk_metrics(portfolio)

    # Compute days in current mode from persisted Redis timestamp
    days_in_mode = 0
    try:
        redis = await get_redis()
        mode_since_str = await redis.get("risk:autonomy:mode_since")
        if mode_since_str:
            mode_since = datetime.fromisoformat(mode_since_str)
            if mode_since.tzinfo is None:
                mode_since = mode_since.replace(tzinfo=UTC)
            days_in_mode = (datetime.now(UTC) - mode_since).days
    except Exception:
        pass

    portfolio_metrics = {
        "days_in_mode": days_in_mode,
        "sharpe": 0.0,  # no in-system Sharpe source; validator will flag if < threshold
        "max_drawdown_pct": metrics_raw.get("current_drawdown_pct", 0.0),
        "circuit_breakers_tested": False,
    }

    validator = AutonomyValidator()
    readiness = {}

    for mode in AutonomyMode:
        approved, reasons = await validator.validate_transition(
            current_mode, mode, portfolio_metrics=portfolio_metrics
        )
        readiness[mode.value] = {"approved": approved, "blocking_reasons": reasons}

    return {
        "current_mode": current_mode.value,
        "readiness": readiness,
    }


@router.post("/autonomy-mode/transition")
async def transition_autonomy_mode(request: TransitionRequest):
    """Attempt to transition the system to a new autonomy mode.

    Validates all preconditions via AutonomyValidator. For FULL_AUTONOMOUS,
    the request body must include confirmation='FULL_AUTONOMOUS'.
    """
    from src.risk.autonomy_validator import AutonomyValidator

    risk_mgr = await get_risk_manager()
    current_mode_str = risk_mgr.settings.autonomy_mode
    try:
        current_mode = AutonomyMode(current_mode_str)
    except ValueError:
        current_mode = AutonomyMode.PAPER_ONLY

    try:
        target_mode = AutonomyMode(request.target_mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown autonomy mode '{request.target_mode}'. "
                   f"Valid values: {[m.value for m in AutonomyMode]}",
        )

    if target_mode == AutonomyMode.FULL_AUTONOMOUS and request.confirmation != "FULL_AUTONOMOUS":
        raise HTTPException(
            status_code=400,
            detail="Transitioning to FULL_AUTONOMOUS requires confirmation='FULL_AUTONOMOUS' in request body.",
        )

    portfolio_metrics = {
        "days_in_mode": request.days_in_mode,
        "sharpe": request.sharpe,
        "max_drawdown_pct": request.max_drawdown_pct,
        "circuit_breakers_tested": request.circuit_breakers_tested,
    }

    validator = AutonomyValidator()
    approved, reasons = await validator.validate_transition(current_mode, target_mode, portfolio_metrics)

    if not approved:
        raise HTTPException(
            status_code=422,
            detail={"message": "Transition not approved", "blocking_reasons": reasons},
        )

    if hasattr(risk_mgr, "transition_autonomy_mode"):
        await risk_mgr.transition_autonomy_mode(target_mode, portfolio_metrics, request.confirmation)

    return {
        "status": "transitioned",
        "from_mode": current_mode.value,
        "to_mode": target_mode.value,
    }


@router.get("/guardrails/status")
async def get_guardrails_status():
    """Get LLM guardrail verification status."""
    from src.agents.guardrails import LLMGuardrailsChecker

    checker = LLMGuardrailsChecker()
    last_verified = await checker.get_last_verified()

    if last_verified is None:
        return {"verified": False, "last_verified": None, "message": "Guardrails never verified"}

    from datetime import datetime
    verified_at = datetime.fromisoformat(last_verified)
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=UTC)
    age_hours = (datetime.now(UTC) - verified_at).total_seconds() / 3600

    return {
        "verified": age_hours <= 24.0,
        "last_verified": last_verified,
        "age_hours": round(age_hours, 2),
        "stale": age_hours > 24.0,
    }
