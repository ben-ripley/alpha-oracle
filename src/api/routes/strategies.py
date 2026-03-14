from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import structlog
import redis as redis_sync
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.dependencies import get_strategy_engine, get_storage
from src.core.config import get_settings
from src.core.models import BacktestResult, StrategyRanking
from src.core.redis import get_redis
from src.strategy.backtest.backtrader_engine import BacktraderEngine

router = APIRouter()
logger = structlog.get_logger()

_BACKTEST_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_TIMING_KEY = "backtest:timing:ms_per_symbol"
_TIMING_FALLBACK_MS = 50.0


def _run_backtest_thread(
    job_key: str,
    strategy,
    bars: dict,
    initial_capital: float,
    start: datetime,
    end: datetime,
    redis_url: str,
) -> None:
    """Synchronous backtest runner -- executed in ThreadPoolExecutor."""
    client = redis_sync.from_url(redis_url, decode_responses=True)
    start_time = time.monotonic()
    try:
        engine = BacktraderEngine()
        result = engine.run(strategy, bars, initial_capital, start, end)
        duration_ms = (time.monotonic() - start_time) * 1000
        symbol_count = max(len(bars), 1)

        # Update job status
        raw = client.get(job_key)
        job_data = json.loads(raw) if raw else {}
        job_data.update({
            "status": "complete",
            "result": result.model_dump(mode="json"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        client.set(job_key, json.dumps(job_data), ex=3600)

        # Persist result so GET /backtest/results picks it up via its Redis fallback
        client.set(
            f"strategy:results:{result.strategy_name}",
            json.dumps(result.model_dump(mode="json")),
        )

        # Update timing calibration (rolling average, weight = 10%)
        sample_ms = duration_ms / symbol_count
        old_raw = client.get(_TIMING_KEY)
        if old_raw is None:
            updated_ms = sample_ms
        else:
            updated_ms = (float(old_raw) * 9 + sample_ms) / 10
        client.set(_TIMING_KEY, str(updated_ms))

    except Exception as exc:
        raw = client.get(job_key)
        job_data = json.loads(raw) if raw else {}
        job_data.update({
            "status": "failed",
            "error": str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        client.set(job_key, json.dumps(job_data), ex=3600)
    finally:
        client.close()


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
    """Submit a backtest job. Returns job_id for polling via GET /backtest/jobs/{id}."""
    engine = await get_strategy_engine()
    try:
        strategy = engine.get_strategy(request.strategy_name)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{request.strategy_name}' not found. "
                   f"Available: {engine.list_strategies()}",
        )

    start = datetime.fromisoformat(request.start_date).replace(tzinfo=timezone.utc)
    end = (
        datetime.fromisoformat(request.end_date).replace(tzinfo=timezone.utc)
        if request.end_date
        else datetime.now(timezone.utc)
    )

    storage = await get_storage()
    bar_lists = await asyncio.gather(
        *[storage.get_ohlcv(sym, start, end) for sym in request.symbols],
        return_exceptions=True,
    )
    bars = {
        sym: bar_list
        for sym, bar_list in zip(request.symbols, bar_lists)
        if isinstance(bar_list, list) and len(bar_list) > 0
    }
    if not bars:
        raise HTTPException(
            status_code=422,
            detail=f"No OHLCV data found for: {request.symbols}. "
                   "Run the data backfill script to load historical bars.",
        )

    redis = await get_redis()
    ms_raw = await redis.get(_TIMING_KEY)
    ms_per_symbol = float(ms_raw) if ms_raw else _TIMING_FALLBACK_MS
    estimated_seconds = round(len(request.symbols) * ms_per_symbol / 1000, 2)

    job_id = str(uuid.uuid4())
    job_key = f"backtest:job:{job_id}"
    job_data = {
        "status": "running",
        "strategy_name": request.strategy_name,
        "symbol_count": len(request.symbols),
        "estimated_seconds": estimated_seconds,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.set(job_key, json.dumps(job_data), ex=3600)

    settings = get_settings()
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(
        _BACKTEST_EXECUTOR,
        _run_backtest_thread,
        job_key,
        strategy,
        bars,
        request.initial_capital,
        start,
        end,
        settings.redis.url,
    )
    future.add_done_callback(
        lambda f: f.exception() and logger.error(
            "backtest executor raised unhandled exception", exc_info=f.exception()
        )
    )

    return {"job_id": job_id, "status": "running", "estimated_seconds": estimated_seconds}


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


@router.get("/backtest/jobs/{job_id}")
async def get_backtest_job(job_id: str):
    """Poll backtest job status. Returns status + result when complete."""
    redis = await get_redis()
    raw = await redis.get(f"backtest:job:{job_id}")
    if not raw:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    return json.loads(raw)


@router.get("/ml/signals")
async def get_ml_signals():
    """Get latest ML-generated signals. Returns mock data until ML pipeline is live."""
    return {
        "signals": [
            {"symbol": "AAPL", "direction": "LONG", "confidence": 0.87, "strategy": "XGBoost Momentum", "timestamp": "2026-03-11 14:32"},
            {"symbol": "MSFT", "direction": "LONG", "confidence": 0.79, "strategy": "XGBoost Momentum", "timestamp": "2026-03-11 14:32"},
            {"symbol": "TSLA", "direction": "SHORT", "confidence": 0.72, "strategy": "XGBoost Mean Reversion", "timestamp": "2026-03-11 14:30"},
            {"symbol": "NVDA", "direction": "LONG", "confidence": 0.68, "strategy": "XGBoost Momentum", "timestamp": "2026-03-11 14:28"},
            {"symbol": "META", "direction": "FLAT", "confidence": 0.44, "strategy": "XGBoost Ensemble", "timestamp": "2026-03-11 14:25"},
            {"symbol": "AMZN", "direction": "LONG", "confidence": 0.81, "strategy": "XGBoost Momentum", "timestamp": "2026-03-11 14:22"},
            {"symbol": "GOOG", "direction": "SHORT", "confidence": 0.56, "strategy": "XGBoost Mean Reversion", "timestamp": "2026-03-11 14:20"},
            {"symbol": "JPM", "direction": "LONG", "confidence": 0.63, "strategy": "XGBoost Value", "timestamp": "2026-03-11 14:18"},
        ],
        "model_meta": {
            "accuracy": 0.73,
            "precision": 0.69,
            "recall": 0.71,
            "model_version": "v0.1.0-mock",
            "last_trained": "2026-03-10",
            "drift_status": "OK",
            "fallback_active": False,
        },
    }


@router.get("/ml/feature-importance")
async def get_ml_feature_importance():
    """Get feature importance from latest model. Returns mock data until ML pipeline is live."""
    return {
        "features": [
            {"name": "rsi_14", "importance": 0.1247},
            {"name": "sma_20_200_ratio", "importance": 0.0934},
            {"name": "volume_ratio_20d", "importance": 0.0821},
            {"name": "macd_histogram", "importance": 0.0756},
            {"name": "bb_width_20", "importance": 0.0698},
            {"name": "atr_pct_14", "importance": 0.0612},
            {"name": "obv_slope_10", "importance": 0.0547},
            {"name": "sector_momentum", "importance": 0.0483},
            {"name": "earnings_surprise", "importance": 0.0421},
            {"name": "insider_net_30d", "importance": 0.0389},
        ]
    }


@router.get("/ml/monitoring")
async def get_ml_monitoring():
    """Get model monitoring data. Returns mock data until monitoring is wired."""
    return {
        "accuracy_history": [
            {"date": f"2026-03-{d:02d}", "accuracy": round(0.55 + (d % 7) * 0.03, 3)}
            for d in range(1, 12)
        ],
        "feature_drift": [
            {"name": "rsi_14", "psi": 0.04},
            {"name": "sma_20_200_ratio", "psi": 0.07},
            {"name": "volume_ratio_20d", "psi": 0.12},
            {"name": "macd_histogram", "psi": 0.03},
            {"name": "bb_width_20", "psi": 0.28},
            {"name": "atr_pct_14", "psi": 0.06},
            {"name": "obv_slope_10", "psi": 0.15},
            {"name": "sector_momentum", "psi": 0.09},
            {"name": "insider_net_30d", "psi": 0.02},
            {"name": "pe_sector_rank", "psi": 0.11},
        ],
        "model_versions": [
            {"version_id": "v1.2.0", "created_at": "2026-03-10", "sharpe": 1.45, "accuracy": 0.71, "is_active": True},
            {"version_id": "v1.1.0", "created_at": "2026-03-03", "sharpe": 1.32, "accuracy": 0.68, "is_active": False},
            {"version_id": "v1.0.0", "created_at": "2026-02-24", "sharpe": 1.18, "accuracy": 0.65, "is_active": False},
        ],
        "current_status": "ok",
        "rolling_accuracy": 0.71,
        "max_psi": 0.28,
        "fallback_active": False,
    }


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
