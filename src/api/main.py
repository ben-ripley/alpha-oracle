from __future__ import annotations

import json
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import portfolio, strategies, risk, trades, system, websocket
from src.core.config import get_settings
from src.core.redis import close_redis

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting stock-analysis API")

    settings = get_settings()
    provider = settings.broker.provider.lower()

    # Start market data feed based on configured broker provider
    feed_connected = False
    try:
        from src.data.universe import SymbolUniverse

        if provider == "ibkr":
            from src.data.feeds.ibkr_feed import IBKRMarketFeed
            feed = IBKRMarketFeed(settings)
        else:
            logger.warning("feed.skipped_unknown_provider", provider=provider)
            app.state.market_feed = None
            feed = None

        if feed is not None:
            await feed.start()
            symbols = await SymbolUniverse().get_symbols()
            if symbols:
                await feed.subscribe(symbols)
                logger.info("feed.subscribed_universe", provider=provider, count=len(symbols))
            app.state.market_feed = feed
            feed_connected = True
    except Exception:
        logger.warning("feed.startup_failed", exc_info=True)
        app.state.market_feed = None

    # Validate IBKR broker connectivity and surface degraded state clearly
    broker_connected = False
    try:
        from src.api.dependencies import get_broker
        broker = await get_broker()
        broker_connected = await broker.health_check()
        if not broker_connected:
            logger.error(
                "ibkr_gateway.not_connected",
                msg="IB Gateway / TWS is not reachable — system is running in degraded mode",
            )
    except Exception:
        logger.error("ibkr_gateway.health_check_failed", exc_info=True)

    app.state.ibkr_gateway_connected = broker_connected

    # Publish connectivity status to Redis so the WebSocket can relay it to the dashboard
    try:
        from src.core.redis import get_redis
        redis = await get_redis()
        status_payload = json.dumps({
            "broker": "connected" if broker_connected else "disconnected",
            "feed": "connected" if feed_connected else "disconnected",
        })
        await redis.set("system:status", status_payload)
    except Exception:
        logger.warning("system_status.publish_failed", exc_info=True)

    # Start scheduler
    try:
        from src.scheduling.scheduler import TradingScheduler

        scheduler = TradingScheduler()
        scheduler.setup()
        scheduler.start()
        app.state.scheduler = scheduler
    except Exception:
        logger.warning("scheduler.startup_failed", exc_info=True)
        app.state.scheduler = None

    yield

    # Stop scheduler
    if getattr(app.state, "scheduler", None) is not None:
        app.state.scheduler.stop()

    # Stop market data feed
    if getattr(app.state, "market_feed", None) is not None:
        await app.state.market_feed.stop()

    # Disconnect broker
    try:
        from src.api.dependencies import close_broker
        await close_broker()
    except Exception:
        logger.warning("broker.shutdown_disconnect_failed", exc_info=True)

    logger.info("Shutting down stock-analysis API")
    await close_redis()


app = FastAPI(
    title="Stock Analysis Trading System",
    description="AI-driven automated stock trading system API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(websocket.router, tags=["websocket"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "stock-analysis"}
