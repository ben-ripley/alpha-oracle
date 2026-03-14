"""Agent API routes: filing analysis, trade recommendations, briefings, cost summary."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.dependencies import get_analyst_agent, get_advisor_agent, get_briefing_agent

router = APIRouter()

_AGENT_DISABLED_RESPONSE = {"detail": "Agent module is disabled"}


def _check_agent_enabled():
    """Raise HTTP 503 if agent.enabled=False."""
    from src.core.config import get_settings
    if not get_settings().agent.enabled:
        raise HTTPException(status_code=503, detail="Agent module is disabled")


async def _check_rate_limit(endpoint: str, limit: int) -> None:
    """Check rate limit for the given endpoint. Raises 429 if exceeded."""
    from src.agents.rate_limiter import AgentRateLimiter
    limiter = AgentRateLimiter()
    allowed = await limiter.check_rate_limit(endpoint, limit_per_hour=limit)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {endpoint}. Try again later.",
        )


# ---------------------------------------------------------------------------
# Filing analysis
# ---------------------------------------------------------------------------

class AnalyzeFilingRequest(BaseModel):
    symbol: str
    filing_text: str
    filing_type: str = "FILING_10K"


@router.post("/analyze-filing")
async def analyze_filing(request: AnalyzeFilingRequest):
    """Trigger Claude analysis of an SEC filing. Rate-limited.

    filing_type: FILING_10K | FILING_10Q | FILING_8K | EARNINGS_SUMMARY
    """
    _check_agent_enabled()
    from src.core.config import get_settings
    settings = get_settings()
    await _check_rate_limit("analyze_filing", settings.agent.rate_limit_analyses_per_hour)

    from src.agents.base import AgentContext
    from src.agents.cost_tracker import BudgetExceededError

    agent = await get_analyst_agent()
    context = AgentContext(
        symbol=request.symbol,
        data={
            "filing_text": request.filing_text,
            "symbol": request.symbol,
            "filing_type": request.filing_type,
        },
    )

    try:
        result = await agent.run(context)
    except BudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    if result.output is None:
        raise HTTPException(status_code=503, detail="Agent module is disabled")

    return result.output.model_dump()


@router.get("/analyses")
async def list_analyses(symbol: str | None = None, limit: int = 20):
    """List recent filing analyses, optionally filtered by symbol."""
    _check_agent_enabled()

    if not symbol:
        raise HTTPException(
            status_code=400,
            detail="symbol query parameter is required",
        )

    agent = await get_analyst_agent()
    analyses = await agent.get_analyses_for_symbol(symbol)
    return {"analyses": [a.model_dump() for a in analyses[:limit]], "total": len(analyses)}


@router.get("/analyses/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get a single filing analysis by ID."""
    _check_agent_enabled()

    from src.core.models import AgentAnalysis
    from src.core.redis import get_redis

    redis = await get_redis()
    data = await redis.get(f"agent:analyses:{analysis_id}")
    if not data:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found")

    try:
        analysis = AgentAnalysis.model_validate_json(data)
        if analysis.schema_version != 1:
            raise HTTPException(status_code=410, detail="Stale analysis — schema version mismatch")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to deserialize analysis")

    return analysis.model_dump()


# ---------------------------------------------------------------------------
# Trade recommendations
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    context_data: dict = {}


@router.post("/recommend/{symbol}")
async def recommend_trade(symbol: str, request: RecommendRequest = RecommendRequest()):
    """Trigger advisor analysis for a symbol. Rate-limited.

    Returns a TradeRecommendation with action (BUY/SELL/HOLD), confidence,
    rationale, and risk factors. Human approval required in MANUAL_APPROVAL mode.
    """
    _check_agent_enabled()
    from src.core.config import get_settings
    settings = get_settings()
    await _check_rate_limit(
        "recommend", settings.agent.rate_limit_recommendations_per_hour
    )

    from src.agents.base import AgentContext
    from src.agents.cost_tracker import BudgetExceededError

    agent = await get_advisor_agent()
    context = AgentContext(
        symbol=symbol,
        data={"symbol": symbol, **request.context_data},
    )

    try:
        result = await agent.run(context)
    except BudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    if result.output is None:
        raise HTTPException(status_code=503, detail="Agent module is disabled")

    return result.output.model_dump()


@router.get("/recommendations")
async def list_recommendations(symbol: str | None = None, limit: int = 20):
    """List recent trade recommendations from Redis."""
    _check_agent_enabled()

    from src.core.models import TradeRecommendation
    from src.core.redis import get_redis

    redis = await get_redis()

    if symbol:
        key = f"agent:recommendations:by_symbol:{symbol}"
        ids = await redis.lrange(key, 0, limit - 1)
    else:
        ids = await redis.lrange("agent:recommendations:recent", 0, limit - 1)

    recommendations = []
    for rec_id in ids:
        data = await redis.get(f"agent:recommendations:{rec_id}")
        if data:
            try:
                rec = TradeRecommendation.model_validate_json(data)
                if rec.schema_version == 1:
                    recommendations.append(rec.model_dump())
            except Exception:
                pass

    return {"recommendations": recommendations, "total": len(recommendations)}


@router.post("/recommendations/{recommendation_id}/approve")
async def approve_recommendation(recommendation_id: str):
    """Mark a pending recommendation as human-approved."""
    _check_agent_enabled()

    from src.core.models import TradeRecommendation
    from src.core.redis import get_redis

    redis = await get_redis()
    key = f"agent:recommendations:{recommendation_id}"
    data = await redis.get(key)
    if not data:
        raise HTTPException(
            status_code=404, detail=f"Recommendation '{recommendation_id}' not found"
        )

    try:
        rec = TradeRecommendation.model_validate_json(data)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to deserialize recommendation")

    rec.human_approved = True
    await redis.set(key, rec.model_dump_json(), keepttl=True)

    # Publish approval event
    await redis.publish("agent:recommendation", json.dumps({
        "event": "approved",
        "recommendation_id": recommendation_id,
        "symbol": rec.symbol,
        "action": rec.action.value if hasattr(rec.action, "value") else rec.action,
    }))

    return {"status": "approved", "recommendation_id": recommendation_id}


@router.post("/recommendations/{recommendation_id}/reject")
async def reject_recommendation(recommendation_id: str):
    """Mark a pending recommendation as human-rejected."""
    _check_agent_enabled()

    from src.core.models import TradeRecommendation
    from src.core.redis import get_redis

    redis = await get_redis()
    key = f"agent:recommendations:{recommendation_id}"
    data = await redis.get(key)
    if not data:
        raise HTTPException(
            status_code=404, detail=f"Recommendation '{recommendation_id}' not found"
        )

    try:
        rec = TradeRecommendation.model_validate_json(data)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to deserialize recommendation")

    rec.human_approved = False
    await redis.set(key, rec.model_dump_json(), keepttl=True)

    await redis.publish("agent:recommendation", json.dumps({
        "event": "rejected",
        "recommendation_id": recommendation_id,
        "symbol": rec.symbol,
    }))

    return {"status": "rejected", "recommendation_id": recommendation_id}


# ---------------------------------------------------------------------------
# Daily briefing
# ---------------------------------------------------------------------------

@router.get("/briefing/latest")
async def get_latest_briefing():
    """Get the most recent daily portfolio briefing."""
    _check_agent_enabled()

    from src.core.models import DailyBriefing
    from src.core.redis import get_redis
    from datetime import date

    redis = await get_redis()
    today = date.today().isoformat()

    # Try today first, then previous days (up to 7)
    for days_ago in range(7):
        from datetime import timedelta
        check_date = (date.today() - timedelta(days=days_ago)).isoformat()
        data = await redis.get(f"agent:briefings:{check_date}")
        if data:
            try:
                briefing = DailyBriefing.model_validate_json(data)
                if briefing.schema_version == 1:
                    return briefing.model_dump()
            except Exception:
                pass

    return {"detail": "No briefing available yet"}


@router.get("/briefing/history")
async def get_briefing_history(limit: int = 7):
    """List recent daily briefings (up to limit days)."""
    _check_agent_enabled()

    from src.core.models import DailyBriefing
    from src.core.redis import get_redis
    from datetime import date, timedelta

    redis = await get_redis()
    briefings = []

    for days_ago in range(limit):
        check_date = (date.today() - timedelta(days=days_ago)).isoformat()
        data = await redis.get(f"agent:briefings:{check_date}")
        if data:
            try:
                briefing = DailyBriefing.model_validate_json(data)
                if briefing.schema_version == 1:
                    briefings.append(briefing.model_dump())
            except Exception:
                pass

    return {"briefings": briefings, "total": len(briefings)}


# ---------------------------------------------------------------------------
# Cost summary
# ---------------------------------------------------------------------------

@router.get("/cost-summary")
async def get_cost_summary():
    """Get LLM API usage and cost summary (daily and monthly)."""
    _check_agent_enabled()

    from src.agents.cost_tracker import CostTracker
    tracker = CostTracker()
    return await tracker.get_cost_summary()
