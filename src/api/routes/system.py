from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request

from src.api.dependencies import get_broker, get_risk_manager
from src.core.config import get_settings

router = APIRouter()


@router.get("/health")
async def system_health():
    """Comprehensive system health check."""
    settings = get_settings()
    checks = {}

    try:
        broker = await get_broker()
        ibkr_ok = await broker.health_check()
        checks["broker"] = ibkr_ok
        checks["ibkr_gateway"] = ibkr_ok
    except Exception:
        checks["broker"] = False
        checks["ibkr_gateway"] = False

    try:
        from src.core.redis import get_redis
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    all_healthy = all(checks.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/config")
async def get_system_config():
    """Get non-sensitive system configuration."""
    settings = get_settings()
    return {
        "environment": settings.environment,
        "broker": {
            "provider": settings.broker.provider,
            "paper_trading": settings.broker.paper_trading,
        },
        "data": {
            "price_source": settings.broker.provider.lower(),
            "ibkr_host": settings.broker.ibkr.host,
            "ibkr_port": settings.broker.ibkr.port,
            "alpha_vantage_rate_limit": settings.data.alpha_vantage.rate_limit_per_minute,
        },
        "strategy": {
            "min_sharpe_ratio": settings.strategy.min_sharpe_ratio,
            "min_profit_factor": settings.strategy.min_profit_factor,
            "max_drawdown_pct": settings.strategy.max_drawdown_pct,
            "min_trades": settings.strategy.min_trades,
        },
        "risk": {
            "autonomy_mode": settings.risk.autonomy_mode,
            "max_position_pct": settings.risk.position_limits.max_position_pct,
            "max_drawdown_pct": settings.risk.portfolio_limits.max_drawdown_pct,
            "pdt_enabled": settings.risk.pdt_guard.enabled,
        },
    }


@router.post("/heartbeat")
async def operator_heartbeat():
    """Update operator heartbeat for dead man's switch."""
    risk_mgr = await get_risk_manager()
    await risk_mgr.circuit_breakers.record_heartbeat()
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/scheduler/status")
async def scheduler_status(request: Request):
    """Get scheduler status and job list."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"status": "not_running", "jobs": []}
    return scheduler.get_status()


@router.post("/scheduler/trigger/{job_name}")
async def trigger_job(job_name: str, request: Request):
    """Manually trigger a scheduled job."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        return {"error": "Scheduler not running"}
    success = await scheduler.trigger_job(job_name)
    if not success:
        return {"error": f"Job '{job_name}' not found"}
    return {"status": "triggered", "job": job_name}
