"""Context gathering utilities for agent workflows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def gather_symbol_context(symbol: str) -> dict[str, Any]:
    """Gather technical features, sentiment, and insider data for a symbol.

    Returns a partial dict gracefully if any source is unavailable.
    This is a best-effort aggregation — missing data produces empty/None values,
    not exceptions.

    The ``_gathered_at`` key records when the context was assembled (UTC ISO-8601).
    Agents and callers can use this to detect stale data: if ``_gathered_at`` is
    more than a few hours old, sentiment and insider signals may no longer reflect
    current market conditions.
    """
    ctx: dict[str, Any] = {
        "symbol": symbol,
        "_gathered_at": datetime.now(timezone.utc).isoformat(),
    }

    # Technical features from FeatureStore
    try:
        from src.signals.feature_store import FeatureStore
        store = FeatureStore()
        features = await store.get_latest_features(symbol)
        ctx["technical_features"] = features if features is not None else {}
    except (ConnectionError, OSError, TimeoutError):
        logger.warning("context.feature_store_unavailable", symbol=symbol)
        ctx["technical_features"] = {}
    except Exception:
        logger.error("context.feature_store_unexpected_error", symbol=symbol, exc_info=True)
        ctx["technical_features"] = {}

    # Sentiment scores from Redis storage
    try:
        from src.core.redis import get_redis
        redis = await get_redis()
        sentiment_key = f"sentiment:latest:{symbol}"
        raw = await redis.get(sentiment_key)
        if raw:
            import json
            ctx["sentiment"] = json.loads(raw)
        else:
            ctx["sentiment"] = None
    except (ConnectionError, OSError, TimeoutError):
        logger.warning("context.sentiment_unavailable", symbol=symbol)
        ctx["sentiment"] = None
    except Exception:
        logger.error("context.sentiment_unexpected_error", symbol=symbol, exc_info=True)
        ctx["sentiment"] = None

    # Insider signals (recent buy/sell transactions)
    try:
        from src.core.redis import get_redis
        redis = await get_redis()
        insider_key = f"insider:latest:{symbol}"
        raw = await redis.get(insider_key)
        if raw:
            import json
            ctx["insider_signals"] = json.loads(raw)
        else:
            ctx["insider_signals"] = None
    except (ConnectionError, OSError, TimeoutError):
        logger.warning("context.insider_unavailable", symbol=symbol)
        ctx["insider_signals"] = None
    except Exception:
        logger.error("context.insider_unexpected_error", symbol=symbol, exc_info=True)
        ctx["insider_signals"] = None

    return ctx


def format_context_for_prompt(ctx: dict[str, Any]) -> str:
    """Format a symbol context dict into a human-readable string for the LLM prompt."""
    lines = [f"Symbol: {ctx.get('symbol', 'UNKNOWN')}"]

    technical = ctx.get("technical_features", {})
    if technical:
        lines.append("\nTechnical Features:")
        for key, val in list(technical.items())[:15]:  # limit to avoid token overflow
            if val is not None:
                lines.append(f"  {key}: {val:.4f}" if isinstance(val, float) else f"  {key}: {val}")

    sentiment = ctx.get("sentiment")
    if sentiment:
        lines.append(f"\nSentiment: score={sentiment.get('mean', 'N/A')}, "
                     f"articles={sentiment.get('count', 'N/A')}")

    insider = ctx.get("insider_signals")
    if insider:
        lines.append(f"\nInsider Activity: {insider}")

    return "\n".join(lines)
