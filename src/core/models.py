from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---

class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    BRACKET = "BRACKET"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class RiskAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUIRE_HUMAN_APPROVAL = "REQUIRE_HUMAN_APPROVAL"
    REDUCE_SIZE = "REDUCE_SIZE"


class AutonomyMode(str, Enum):
    PAPER_ONLY = "PAPER_ONLY"
    MANUAL_APPROVAL = "MANUAL_APPROVAL"
    BOUNDED_AUTONOMOUS = "BOUNDED_AUTONOMOUS"
    FULL_AUTONOMOUS = "FULL_AUTONOMOUS"


# --- Data Models ---

class OHLCV(BaseModel):
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    source: str = ""
    adjusted_close: float | None = None


class FundamentalData(BaseModel):
    symbol: str
    timestamp: datetime
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    ps_ratio: float | None = None
    ev_ebitda: float | None = None
    debt_to_equity: float | None = None
    current_ratio: float | None = None
    roe: float | None = None
    revenue_growth: float | None = None
    earnings_growth: float | None = None
    dividend_yield: float | None = None
    market_cap: float | None = None
    sector: str = ""
    industry: str = ""


class Filing(BaseModel):
    symbol: str
    filing_type: str  # 10-K, 10-Q, 8-K, Form 4
    filed_date: datetime
    url: str
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Signal & Strategy Models ---

class Signal(BaseModel):
    symbol: str
    timestamp: datetime
    direction: SignalDirection
    strength: float = Field(ge=0.0, le=1.0)
    strategy_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyRanking(BaseModel):
    strategy_name: str
    composite_score: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    consistency_score: float
    total_trades: int
    win_rate: float
    meets_thresholds: bool
    ranked_at: datetime = Field(default_factory=datetime.utcnow)


class BacktestResult(BaseModel):
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annual_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Execution Models ---

class Order(BaseModel):
    id: str = ""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    take_profit_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    strategy_name: str = ""
    signal_strength: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None
    filled_price: float | None = None
    filled_quantity: float | None = None
    broker_order_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    side: OrderSide = OrderSide.BUY
    sector: str = ""
    entry_date: datetime | None = None
    strategy_name: str = ""


class PortfolioSnapshot(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_equity: float
    cash: float
    positions_value: float
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    positions: list[Position] = Field(default_factory=list)
    sector_exposure: dict[str, float] = Field(default_factory=dict)


class TradeRecord(BaseModel):
    id: str = ""
    symbol: str
    side: OrderSide
    quantity: float
    entry_price: float
    exit_price: float | None = None
    entry_time: datetime
    exit_time: datetime | None = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    strategy_name: str = ""
    hold_duration_days: float = 0.0
    is_day_trade: bool = False


# --- Risk Models ---

class RiskCheckResult(BaseModel):
    action: RiskAction
    reasons: list[str] = Field(default_factory=list)
    adjusted_quantity: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Phase 2: Alternative Data Models ---

class InsiderTransaction(BaseModel):
    symbol: str
    filed_date: datetime
    insider_name: str = ""
    insider_title: str = ""
    transaction_type: str = ""  # P (purchase), S (sale), A (grant), D (disposal), M (exercise)
    shares: float = 0.0
    price_per_share: float | None = None
    shares_owned_after: float | None = None
    is_direct: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ShortInterestData(BaseModel):
    symbol: str
    settlement_date: datetime
    short_interest: int = 0
    avg_daily_volume: int = 0
    days_to_cover: float = 0.0
    short_pct_float: float | None = None
    change_pct: float | None = None


# --- Phase 2: Execution Quality ---

class ExecutionQualityMetrics(BaseModel):
    order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    expected_price: float = 0.0
    filled_price: float = 0.0
    slippage_bps: float = 0.0
    arrival_slippage_bps: float = 0.0
    fill_latency_ms: float = 0.0
    signal_timestamp: datetime | None = None
    fill_timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
