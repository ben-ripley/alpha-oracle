from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

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
        checks["broker"] = await broker.health_check()
    except Exception:
        checks["broker"] = False

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
            "alpaca_feed": settings.data.alpaca.feed,
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
    await risk_mgr.circuit_breakers.update_heartbeat()
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
