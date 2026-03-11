"""Dependency injection for API routes.

Provides singleton instances of core services. In production these would be
properly initialized at startup; for now they use lazy initialization with
configuration from settings.
"""
from __future__ import annotations

import structlog

from src.core.config import get_settings
from src.core.interfaces import BrokerAdapter

logger = structlog.get_logger()

_broker: BrokerAdapter | None = None
_risk_manager = None
_execution_engine = None
_strategy_engine = None
_storage = None


async def get_broker() -> BrokerAdapter:
    global _broker
    if _broker is None:
        from src.execution.broker_adapters.alpaca_adapter import AlpacaBrokerAdapter
        settings = get_settings()
        _broker = AlpacaBrokerAdapter(settings)
    return _broker


async def get_risk_manager():
    global _risk_manager
    if _risk_manager is None:
        from src.risk.manager import RiskManagerImpl
        broker = await get_broker()
        _risk_manager = RiskManagerImpl(broker_adapter=broker)
    return _risk_manager


async def get_execution_engine():
    global _execution_engine
    if _execution_engine is None:
        from src.execution.engine import ExecutionEngine
        broker = await get_broker()
        risk_mgr = await get_risk_manager()
        _execution_engine = ExecutionEngine(broker=broker, risk_manager=risk_mgr)
    return _execution_engine


async def get_strategy_engine():
    global _strategy_engine
    if _strategy_engine is None:
        from src.strategy.engine import StrategyEngine
        _strategy_engine = StrategyEngine()
    return _strategy_engine


async def get_storage():
    global _storage
    if _storage is None:
        from src.data.storage import TimeSeriesStorage
        _storage = TimeSeriesStorage()
    return _storage
