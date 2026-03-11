"""Stub broker adapter that returns demo portfolio data when no real broker is configured.

Used during local development/testing when Alpaca API keys are not available.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import structlog

from src.core.interfaces import BrokerAdapter
from src.core.models import (
    Order,
    OrderSide,
    OrderStatus,
    Position,
    PortfolioSnapshot,
)

logger = structlog.get_logger(__name__)

_DEMO_POSITIONS = [
    Position(
        symbol="AAPL", quantity=15, avg_entry_price=178.50, current_price=183.20,
        market_value=2748.00, unrealized_pnl=70.50, unrealized_pnl_pct=2.63,
        side=OrderSide.BUY, sector="Technology", strategy_name="swing_momentum",
        entry_date=datetime.utcnow() - timedelta(days=4),
    ),
    Position(
        symbol="MSFT", quantity=8, avg_entry_price=415.00, current_price=422.80,
        market_value=3382.40, unrealized_pnl=62.40, unrealized_pnl_pct=1.88,
        side=OrderSide.BUY, sector="Technology", strategy_name="mean_reversion",
        entry_date=datetime.utcnow() - timedelta(days=2),
    ),
    Position(
        symbol="JPM", quantity=12, avg_entry_price=195.20, current_price=192.10,
        market_value=2305.20, unrealized_pnl=-37.20, unrealized_pnl_pct=-1.59,
        side=OrderSide.BUY, sector="Financials", strategy_name="value_factor",
        entry_date=datetime.utcnow() - timedelta(days=3),
    ),
    Position(
        symbol="UNH", quantity=4, avg_entry_price=528.00, current_price=541.50,
        market_value=2166.00, unrealized_pnl=54.00, unrealized_pnl_pct=2.56,
        side=OrderSide.BUY, sector="Healthcare", strategy_name="swing_momentum",
        entry_date=datetime.utcnow() - timedelta(days=3),
    ),
    Position(
        symbol="XOM", quantity=20, avg_entry_price=105.40, current_price=103.20,
        market_value=2064.00, unrealized_pnl=-44.00, unrealized_pnl_pct=-2.09,
        side=OrderSide.BUY, sector="Energy", strategy_name="value_factor",
        entry_date=datetime.utcnow() - timedelta(days=5),
    ),
]


class PaperStubBroker(BrokerAdapter):
    """Returns demo portfolio data. No real broker calls."""

    def __init__(self) -> None:
        logger.warning(
            "paper_stub_broker_initialized",
            msg="No Alpaca API keys configured — using stub broker with demo data",
        )

    async def submit_order(self, order: Order) -> Order:
        order.broker_order_id = f"stub-{uuid.uuid4()}"
        order.status = OrderStatus.REJECTED
        order.metadata["rejection_reason"] = "Stub broker — configure Alpaca API keys to trade"
        logger.warning("stub_broker_order_rejected", symbol=order.symbol)
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        return True

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        return OrderStatus.REJECTED

    async def get_positions(self) -> list[Position]:
        return list(_DEMO_POSITIONS)

    async def get_portfolio(self) -> PortfolioSnapshot:
        positions = list(_DEMO_POSITIONS)
        positions_value = sum(p.market_value for p in positions)
        cash = 8819.72
        total_equity = cash + positions_value
        sector_exposure: dict[str, float] = {}
        for p in positions:
            sector_exposure[p.sector] = sector_exposure.get(p.sector, 0.0) + p.market_value

        return PortfolioSnapshot(
            total_equity=total_equity,
            cash=cash,
            positions_value=positions_value,
            daily_pnl=105.70,
            daily_pnl_pct=0.53,
            total_pnl=105.70,
            total_pnl_pct=0.53,
            max_drawdown_pct=4.2,
            positions=positions,
            sector_exposure=sector_exposure,
        )

    async def health_check(self) -> bool:
        return False
