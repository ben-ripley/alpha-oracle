# Architecture Overview

This page provides a high-level overview of the **alpha-oracle** system architecture, core design patterns, and key interfaces.

## Architectural Style: Modular Monolith

The system uses a **modular monolith** architecture — a single deployable application with well-defined internal module boundaries.

### Why Not Microservices?

For a trading system under active development by a small team, a modular monolith provides:

- **Simplicity**: Single deployment, no distributed system complexity
- **Performance**: No network latency between modules, shared in-memory state
- **Transactions**: ACID guarantees across modules (single database)
- **Debugging**: Unified logs, no distributed tracing overhead
- **Evolution**: Easy to extract microservices later if needed

### Module Communication

Modules communicate via:

1. **Direct function calls** — For synchronous operations (e.g., risk checks, order generation)
2. **[Redis](../glossary.md#redis) pub/sub** — For asynchronous events (e.g., `signal:generated`, `order:filled`, `risk:alert`)
3. **Shared database** — [TimescaleDB](../glossary.md#timescaledb) for time-series data, Redis for cache/state

**Example Redis pub/sub channels:**

- `signals` — Strategy signals generated
- `orders` — Order lifecycle events (submitted, filled, rejected)
- `risk` — Risk alerts and circuit breaker activations
- `kill_switch` — Emergency halt events

## Core Abstractions

The system defines 5 abstract base classes (ABCs) in `src/core/interfaces.py` to enforce module boundaries and enable pluggability.

### 1. DataSourceInterface

Interface for market data providers.

```python
from abc import ABC, abstractmethod
from datetime import datetime
from src.core.models import OHLCV, FundamentalData

class DataSourceInterface(ABC):
    @abstractmethod
    async def get_historical_bars(
        self, symbol: str, start: datetime, end: datetime, timeframe: str = "1Day"
    ) -> list[OHLCV]:
        """Fetch historical OHLCV bars."""
        ...

    @abstractmethod
    async def get_latest_bar(self, symbol: str) -> OHLCV | None:
        """Fetch most recent bar."""
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> FundamentalData | None:
        """Fetch fundamental data (PE ratio, debt/equity, etc.)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify data source is accessible."""
        ...
```

**Implementations:**
- `IBKRDataAdapter` — Interactive Brokers market data
- `AlphaVantageAdapter` — Alpha Vantage REST API
- `EDGARAdapter` — SEC EDGAR filings
- `FINRAAdapter` — FINRA short interest data

### 2. BaseStrategy

Base class for trading strategies.

```python
from abc import ABC, abstractmethod
from src.core.models import OHLCV, Signal

class BaseStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier."""
        ...

    @property
    @abstractmethod
    def min_hold_days(self) -> int:
        """Minimum holding period (must be >= 2 for swing trading)."""
        ...

    @abstractmethod
    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        """Generate trading signals from market data."""
        ...

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """Return strategy parameters for logging/tuning."""
        ...

    @abstractmethod
    def get_required_data(self) -> list[str]:
        """Return data types needed: ['ohlcv', 'fundamentals', etc.]"""
        ...
```

**Implementations:**
- `MomentumStrategy` — Dual momentum (relative + absolute)
- `MeanReversionStrategy` — Bollinger Band reversals
- `BreakoutStrategy` — ATR-based breakouts
- `MLSignalStrategy` — XGBoost predictions

### 3. BrokerAdapter

Interface for broker integrations.

```python
from abc import ABC, abstractmethod
from src.core.models import Order, OrderStatus, Position, PortfolioSnapshot

class BrokerAdapter(ABC):
    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """Submit order to broker, return updated order with broker_order_id."""
        ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel pending order."""
        ...

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Query order status."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Fetch current positions."""
        ...

    @abstractmethod
    async def get_portfolio(self) -> PortfolioSnapshot:
        """Fetch portfolio snapshot (equity, cash, positions)."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify broker connection."""
        ...
```

**Implementations:**
- `IBKRBrokerAdapter` — Interactive Brokers via ib-async
- `SimulatedBroker` — In-memory broker for testing (realistic fills, slippage)
- `PaperStubBroker` — Demo stub with mock data

### 4. RiskManager

Interface for risk management checks.

```python
from abc import ABC, abstractmethod
from src.core.models import Order, PortfolioSnapshot, RiskCheckResult

class RiskManager(ABC):
    @abstractmethod
    async def check_pre_trade(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Run pre-trade risk checks (PDT, position limits, portfolio limits)."""
        ...

    @abstractmethod
    async def check_portfolio(
        self, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Run portfolio-level risk checks (drawdown, daily loss)."""
        ...

    @abstractmethod
    async def is_kill_switch_active(self) -> bool:
        """Check if emergency kill switch is active."""
        ...

    @abstractmethod
    async def activate_kill_switch(self, reason: str) -> None:
        """Activate kill switch and halt trading."""
        ...
```

**Implementations:**
- `PreTradeRiskManager` — Pre-trade checks (PDT, position limits)
- `PortfolioMonitor` — Real-time portfolio monitoring
- `PDTGuard` — Pattern Day Trader rule enforcement
- `CircuitBreakers` — VIX, stale data, reconciliation checks

### 5. BacktestEngine

Interface for backtesting frameworks.

```python
from abc import ABC, abstractmethod
from datetime import datetime
from src.core.models import BacktestResult

class BacktestEngine(ABC):
    @abstractmethod
    def run(
        self,
        strategy: BaseStrategy,
        data: dict[str, list[OHLCV]],
        initial_capital: float,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        """Run single backtest."""
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
        """Run walk-forward analysis."""
        ...
```

**Implementations:**
- `BacktraderEngine` — Backtrader framework integration
- `VectorBTEngine` — VectorBT for vectorized backtests (optional)

## Configuration System

Configuration uses **Pydantic Settings** with a two-tier hierarchy:

1. **YAML files** (`config/settings.yaml`, `config/risk_limits.yaml`)
2. **Environment variables** (with `SA_` prefix and `__` nesting)

### Loading Order

```python
from src.core.config import Settings

settings = Settings.from_yaml()  # Load YAML, then apply env overrides
```

**Example YAML** (`config/settings.yaml`):

```yaml
app:
  environment: development
  log_level: INFO

broker:
  provider: ibkr
  paper_trading: true
  ibkr:
    host: 127.0.0.1
    port: 4002

database:
  url: postgresql+asyncpg://trader:dev_password@localhost:5432/stock_analysis

redis:
  url: redis://localhost:6379/0
```

**Environment Variable Overrides**:

```bash
# Override nested config with __ delimiter
SA_BROKER__PROVIDER=simulated
SA_BROKER__IBKR__PORT=4001
SA_DATABASE__URL=postgresql+asyncpg://user:pass@prod-db:5432/trading
```

### Key Settings Modules

- `BrokerSettings` — Broker provider, IBKR connection
- `DataSettings` — Alpha Vantage rate limits, EDGAR user agent, feed config
- `StrategySettings` — Min Sharpe ratio, walk-forward params
- `ExecutionSettings` — Order type, Kelly sizing
- `RiskSettings` — Autonomy mode, position/portfolio limits, PDT guard, circuit breakers
- `MLSettings` — XGBoost params, confidence threshold, retraining schedule
- `SchedulerSettings` — Cron schedules for data jobs and model retraining

## Data Models

All Pydantic models live in `src/core/models.py`.

### Key Models

- **OHLCV** — Open/High/Low/Close/Volume bar
- **FundamentalData** — PE ratio, debt/equity, ROE, etc.
- **Signal** — Strategy signal (LONG/SHORT/FLAT) with strength and metadata
- **Order** — Order request (symbol, side, type, quantity, limit price)
- **Position** — Open position (symbol, quantity, entry price, P&L)
- **PortfolioSnapshot** — Account equity, cash, positions, drawdown
- **BacktestResult** — Sharpe, Sortino, max drawdown, equity curve, trades

### Key Enums

- `SignalDirection` — LONG, SHORT, FLAT
- `OrderSide` — BUY, SELL
- `OrderType` — MARKET, LIMIT, STOP, STOP_LIMIT, BRACKET
- `OrderStatus` — PENDING, SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED
- `RiskAction` — APPROVE, REJECT, REQUIRE_HUMAN_APPROVAL, REDUCE_SIZE
- `AutonomyMode` — PAPER_ONLY, MANUAL_APPROVAL, BOUNDED_AUTONOMOUS, FULL_AUTONOMOUS

## Lazy Imports

Modules with heavy dependencies (e.g., `backtrader`, `pandas_ta`) use **lazy imports** in `__init__.py` to avoid import-time overhead.

**Example** (`src/strategy/backtest/__init__.py`):

```python
# Don't import at module level
# from .backtrader_engine import BacktraderEngine  # ❌ Slow

# Instead, import on-demand
def get_backtrader_engine():
    from .backtrader_engine import BacktraderEngine  # ✅ Fast
    return BacktraderEngine()
```

This pattern is used in:
- `src/strategy/backtest/` — Backtrader, VectorBT
- `src/strategy/builtin/` — pandas_ta indicators
- `src/scheduling/jobs.py` — Adapter imports inside job functions

## Dependency Direction

Modules follow a strict dependency hierarchy (no circular deps):

```
api → execution → strategy → signals → data → core
  ↓       ↓          ↓          ↓        ↓
 risk → monitoring → scheduling
```

- **core** — Foundation (models, interfaces, config, DB, Redis)
- **data** — Adapters, feeds, storage, universe
- **signals** — Feature store, ML pipeline
- **strategy** — Strategy engine, backtesting
- **execution** — Order routing, broker adapters
- **risk** — Pre-trade checks, PDT guard, circuit breakers
- **scheduling** — Cron jobs, model registry
- **monitoring** — Metrics, alerts
- **api** — FastAPI routes, WebSocket

## Next Steps

- [Data Flows](data-flows.md) — Understand signal generation, execution, and risk flows
- [Module Map](module-map.md) — Detailed directory structure and entry points
