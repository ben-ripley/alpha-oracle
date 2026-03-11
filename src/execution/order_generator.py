from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from src.core.config import get_settings
from src.core.models import (
    Order,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    Signal,
    SignalDirection,
)

logger = structlog.get_logger(__name__)


class OrderGenerator:
    """Generates orders from trading signals using Kelly criterion position sizing."""

    def __init__(self) -> None:
        self._settings = get_settings()

    def generate_order(
        self, signal: Signal, portfolio: PortfolioSnapshot
    ) -> Order:
        log = logger.bind(symbol=signal.symbol, direction=signal.direction)

        side = self._signal_to_side(signal)
        if side is None:
            raise ValueError(f"Cannot generate order for FLAT signal on {signal.symbol}")

        win_rate = signal.metadata.get("win_rate", 0.55)
        avg_win = signal.metadata.get("avg_win_pct", 2.0)
        avg_loss = signal.metadata.get("avg_loss_pct", 1.0)

        kelly_frac = self.kelly_criterion(win_rate, avg_win, avg_loss)
        quantity = self.calculate_quantity(signal, portfolio, kelly_frac)

        if quantity <= 0:
            raise ValueError(
                f"Calculated zero quantity for {signal.symbol}, "
                f"kelly={kelly_frac:.4f}, cash={portfolio.cash:.2f}"
            )

        exec_settings = self._settings.execution
        risk_settings = self._settings.risk.position_limits

        latest_price = self._get_latest_price(signal, portfolio)

        if exec_settings.default_order_type == "limit" and latest_price > 0:
            order_type = OrderType.LIMIT
            offset = exec_settings.limit_offset_pct / 100.0
            if side == OrderSide.BUY:
                limit_price = round(latest_price * (1 + offset), 2)
            else:
                limit_price = round(latest_price * (1 - offset), 2)
        else:
            order_type = OrderType.MARKET
            limit_price = None

        stop_loss_pct = risk_settings.stop_loss_pct / 100.0
        if latest_price > 0:
            if side == OrderSide.BUY:
                stop_price = round(latest_price * (1 - stop_loss_pct), 2)
            else:
                stop_price = round(latest_price * (1 + stop_loss_pct), 2)
        else:
            stop_price = None

        order = Order(
            id=str(uuid.uuid4()),
            symbol=signal.symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            strategy_name=signal.strategy_name,
            signal_strength=signal.strength,
            created_at=datetime.utcnow(),
            metadata={
                "signal_timestamp": signal.timestamp.isoformat(),
                "kelly_fraction": kelly_frac,
            },
        )

        log.info(
            "order_generated",
            side=side,
            qty=quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            kelly=kelly_frac,
        )
        return order

    @staticmethod
    def kelly_criterion(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Half-Kelly criterion: f*/2 = ((p*b - q) / b) / 2."""
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        p = win_rate
        q = 1.0 - p
        b = avg_win / avg_loss  # win/loss ratio

        kelly = (p * b - q) / b
        if kelly <= 0:
            return 0.0

        half_kelly = kelly / 2.0
        return min(half_kelly, 0.25)  # cap at 25% as safety

    def calculate_quantity(
        self,
        signal: Signal,
        portfolio: PortfolioSnapshot,
        kelly_fraction: float,
    ) -> float:
        """Calculate position size respecting portfolio limits."""
        max_position_pct = self._settings.risk.position_limits.max_position_pct / 100.0
        min_cash_reserve_pct = (
            self._settings.risk.portfolio_limits.min_cash_reserve_pct / 100.0
        )

        latest_price = self._get_latest_price(signal, portfolio)
        if latest_price <= 0:
            return 0.0

        # Kelly-based allocation, capped by max position size
        allocation_pct = min(kelly_fraction, max_position_pct)
        allocation_value = portfolio.total_equity * allocation_pct

        # Scale by signal strength
        allocation_value *= signal.strength

        # Ensure we keep minimum cash reserve
        available_cash = portfolio.cash - (portfolio.total_equity * min_cash_reserve_pct)
        if available_cash <= 0:
            return 0.0
        allocation_value = min(allocation_value, available_cash)

        # Round to whole shares
        quantity = int(allocation_value / latest_price)
        return float(max(quantity, 0))

    @staticmethod
    def _signal_to_side(signal: Signal) -> OrderSide | None:
        if signal.direction == SignalDirection.LONG:
            return OrderSide.BUY
        elif signal.direction == SignalDirection.SHORT:
            return OrderSide.SELL
        return None

    @staticmethod
    def _get_latest_price(signal: Signal, portfolio: PortfolioSnapshot) -> float:
        """Get latest price from signal metadata or existing position."""
        price = signal.metadata.get("latest_price", 0.0)
        if price > 0:
            return price

        for pos in portfolio.positions:
            if pos.symbol == signal.symbol and pos.current_price > 0:
                return pos.current_price

        return 0.0
