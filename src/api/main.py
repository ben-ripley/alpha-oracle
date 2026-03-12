from __future__ import annotations

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

    # Start market data feed based on configured broker provider
    settings = get_settings()
    provider = settings.broker.provider.lower()
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
    except Exception:
        logger.warning("feed.startup_failed", exc_info=True)
        app.state.market_feed = None

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
