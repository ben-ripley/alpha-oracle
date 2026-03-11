"""Shared test fixtures."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

# Ensure settings don't try to load .env or connect to real services
os.environ.setdefault("SA_ALPACA_API_KEY", "test_key")
os.environ.setdefault("SA_ALPACA_SECRET_KEY", "test_secret")

from src.core.models import (
    BacktestResult,
    OHLCV,
    Order,
    OrderSide,
    OrderType,
    Position,
    PortfolioSnapshot,
    Signal,
    SignalDirection,
)


@pytest.fixture
def sample_portfolio() -> PortfolioSnapshot:
    """A typical portfolio with $20K equity, 3 positions, $12K cash."""
    return PortfolioSnapshot(
        timestamp=datetime.utcnow(),
        total_equity=20000.0,
        cash=12000.0,
        positions_value=8000.0,
        daily_pnl=150.0,
        daily_pnl_pct=0.75,
        total_pnl=500.0,
        total_pnl_pct=2.5,
        max_drawdown_pct=3.2,
        positions=[
            Position(
                symbol="AAPL",
                quantity=10,
                avg_entry_price=178.0,
                current_price=183.0,
                market_value=1830.0,
                unrealized_pnl=50.0,
                unrealized_pnl_pct=2.81,
                sector="Technology",
                entry_date=datetime.utcnow() - timedelta(days=5),
                strategy_name="SwingMomentum",
            ),
            Position(
                symbol="MSFT",
                quantity=5,
                avg_entry_price=415.0,
                current_price=420.0,
                market_value=2100.0,
                unrealized_pnl=25.0,
                unrealized_pnl_pct=1.20,
                sector="Technology",
                entry_date=datetime.utcnow() - timedelta(days=3),
                strategy_name="MeanReversion",
            ),
            Position(
                symbol="JPM",
                quantity=20,
                avg_entry_price=195.0,
                current_price=198.0,
                market_value=3960.0,
                unrealized_pnl=60.0,
                unrealized_pnl_pct=1.54,
                sector="Financials",
                entry_date=datetime.utcnow() - timedelta(days=7),
                strategy_name="ValueFactor",
            ),
        ],
        sector_exposure={"Technology": 3930.0, "Financials": 3960.0},
    )


@pytest.fixture
def sample_buy_order() -> Order:
    """A typical buy limit order."""
    return Order(
        id="test-order-001",
        symbol="GOOG",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=5,
        limit_price=170.0,
        stop_price=166.60,
        strategy_name="SwingMomentum",
        signal_strength=0.7,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """A typical LONG signal."""
    return Signal(
        symbol="GOOG",
        timestamp=datetime.utcnow(),
        direction=SignalDirection.LONG,
        strength=0.75,
        strategy_name="SwingMomentum",
        metadata={"latest_price": 170.0, "win_rate": 0.58, "avg_win_pct": 3.0, "avg_loss_pct": 1.5},
    )


@pytest.fixture
def make_ohlcv_bars():
    """Factory to create a list of OHLCV bars for testing strategies."""
    def _make(
        symbol: str = "AAPL",
        days: int = 100,
        start_price: float = 150.0,
        volatility: float = 2.0,
    ) -> list[OHLCV]:
        import numpy as np
        np.random.seed(42)
        bars = []
        price = start_price
        base_date = datetime(2024, 1, 2)

        for i in range(days):
            change = np.random.normal(0, volatility)
            open_price = price
            close_price = price + change
            high_price = max(open_price, close_price) + abs(np.random.normal(0, volatility * 0.5))
            low_price = min(open_price, close_price) - abs(np.random.normal(0, volatility * 0.5))
            volume = int(np.random.uniform(1_000_000, 10_000_000))

            bars.append(OHLCV(
                symbol=symbol,
                timestamp=base_date + timedelta(days=i),
                open=round(max(open_price, 1.0), 2),
                high=round(max(high_price, 1.0), 2),
                low=round(max(low_price, 1.0), 2),
                close=round(max(close_price, 1.0), 2),
                volume=volume,
                source="test",
            ))
            price = close_price

        return bars
    return _make


@pytest.fixture
def mock_redis():
    """Shared AsyncMock Redis client for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    redis.hset = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hgetall = AsyncMock(return_value={})
    redis.hdel = AsyncMock()
    redis.hlen = AsyncMock(return_value=0)
    redis.rpush = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    redis.zadd = AsyncMock()
    redis.zrangebyscore = AsyncMock(return_value=[])
    redis.zremrangebyscore = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def mock_broker():
    """AsyncMock spec'd to BrokerAdapter interface."""
    from src.core.interfaces import BrokerAdapter

    broker = AsyncMock(spec=BrokerAdapter)
    broker.get_portfolio = AsyncMock(return_value=PortfolioSnapshot(
        total_equity=20000.0,
        cash=12000.0,
        positions_value=8000.0,
    ))
    broker.get_positions = AsyncMock(return_value=[])
    broker.submit_order = AsyncMock(side_effect=lambda o: o)
    broker.cancel_order = AsyncMock(return_value=True)
    broker.health_check = AsyncMock(return_value=True)
    return broker


@pytest.fixture
def make_backtest_result():
    """Factory for BacktestResult objects."""

    def _make(
        strategy_name: str = "TestStrategy",
        total_return_pct: float = 25.0,
        sharpe_ratio: float = 1.5,
        sortino_ratio: float = 2.0,
        max_drawdown_pct: float = 8.0,
        profit_factor: float = 2.0,
        total_trades: int = 150,
        win_rate: float = 0.55,
        **kwargs,
    ) -> BacktestResult:
        defaults = dict(
            strategy_name=strategy_name,
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2024, 1, 1),
            initial_capital=100_000.0,
            final_capital=125_000.0,
            total_return_pct=total_return_pct,
            annual_return_pct=total_return_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=int(total_trades * win_rate),
            losing_trades=total_trades - int(total_trades * win_rate),
            win_rate=win_rate,
            avg_win_pct=3.0,
            avg_loss_pct=1.5,
        )
        defaults.update(kwargs)
        return BacktestResult(**defaults)

    return _make
