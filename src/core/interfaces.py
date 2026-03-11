from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from src.core.models import (
    BacktestResult,
    FundamentalData,
    Filing,
    OHLCV,
    Order,
    OrderStatus,
    Position,
    PortfolioSnapshot,
    RiskCheckResult,
    Signal,
)


class DataSourceInterface(ABC):
    """Interface for all market data source adapters."""

    @abstractmethod
    async def get_historical_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str = "1Day"
    ) -> list[OHLCV]:
        ...

    @abstractmethod
    async def get_latest_bar(self, symbol: str) -> OHLCV | None:
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> FundamentalData | None:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class FilingSourceInterface(ABC):
    """Interface for SEC filing data sources."""

    @abstractmethod
    async def get_filings(
        self, symbol: str, filing_type: str, start: datetime, end: datetime
    ) -> list[Filing]:
        ...

    @abstractmethod
    async def get_insider_transactions(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        ...


class BaseStrategy(ABC):
    """Base class for all trading strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @property
    @abstractmethod
    def min_hold_days(self) -> int:
        """Minimum holding period in days (must be >= 2 for swing trading)."""
        ...

    @abstractmethod
    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        ...

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def get_required_data(self) -> list[str]:
        """Return list of data types needed: ['ohlcv', 'fundamentals', etc.]"""
        ...


class BrokerAdapter(ABC):
    """Interface for broker interactions."""

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        ...

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...

    @abstractmethod
    async def get_portfolio(self) -> PortfolioSnapshot:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...


class RiskManager(ABC):
    """Interface for risk management checks."""

    @abstractmethod
    async def check_pre_trade(self, order: Order, portfolio: PortfolioSnapshot) -> RiskCheckResult:
        ...

    @abstractmethod
    async def check_portfolio(self, portfolio: PortfolioSnapshot) -> RiskCheckResult:
        ...

    @abstractmethod
    async def is_kill_switch_active(self) -> bool:
        ...

    @abstractmethod
    async def activate_kill_switch(self, reason: str) -> None:
        ...


class BacktestEngine(ABC):
    """Interface for backtesting frameworks."""

    @abstractmethod
    def run(
        self,
        strategy: BaseStrategy,
        data: dict[str, list[OHLCV]],
        initial_capital: float,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        ...

    @abstractmethod
    def walk_forward(
        self,
        strategy: BaseStrategy,
        data: dict[str, list[OHLCV]],
        initial_capital: float,
        train_months: int,
        test_months: int,
        step_months: int,
    ) -> list[BacktestResult]:
        ...
