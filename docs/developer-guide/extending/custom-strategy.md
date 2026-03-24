---
title: Writing a Custom Strategy
nav_order: 1
parent: Extending
---

# Writing a Custom Strategy

Strategies generate buy/sell signals based on market data and indicators. All strategies implement the [BaseStrategy](../glossary.md#abc) abstract base class.

## BaseStrategy Interface

**Location:** `src/core/interfaces.py`

```python
from abc import ABC, abstractmethod
from typing import Any
from src.core.models import OHLCV, Signal

class BaseStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique strategy identifier (lowercase_underscore)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable strategy description."""
        ...

    @property
    @abstractmethod
    def min_hold_days(self) -> int:
        """Minimum holding period in days (must be >= 2 for swing trading)."""
        ...

    @abstractmethod
    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        """Generate trading signals from market data."""
        ...

    @abstractmethod
    def get_parameters(self) -> dict[str, Any]:
        """Return strategy parameters for logging and backtesting."""
        ...

    @abstractmethod
    def get_required_data(self) -> list[str]:
        """Return list of data types needed: ['ohlcv', 'fundamentals', etc.]"""
        ...
```

---

## Example: Simple RSI Strategy

### 1. Create Strategy File

**Location:** `src/strategy/builtin/rsi_simple.py`

```python
from __future__ import annotations

from typing import Any
import pandas as pd
import structlog

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, Signal, SignalDirection
from src.strategy.builtin._indicators import rsi  # Lazy-imported indicators

logger = structlog.get_logger(__name__)


class SimpleRSI(BaseStrategy):
    """Simple RSI mean reversion strategy.

    Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought).
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold_threshold: float = 30.0,
        overbought_threshold: float = 70.0,
    ) -> None:
        self._rsi_period = rsi_period
        self._oversold = oversold_threshold
        self._overbought = overbought_threshold

    @property
    def name(self) -> str:
        return "simple_rsi"

    @property
    def description(self) -> str:
        return f"RSI({self._rsi_period}) mean reversion: buy < {self._oversold}, sell > {self._overbought}"

    @property
    def min_hold_days(self) -> int:
        # CRITICAL: Must be >= 2 for PDT compliance (swing trading)
        return 2

    def get_parameters(self) -> dict[str, Any]:
        return {
            "rsi_period": self._rsi_period,
            "oversold_threshold": self._oversold,
            "overbought_threshold": self._overbought,
        }

    def get_required_data(self) -> list[str]:
        return ["ohlcv"]

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        signals: list[Signal] = []

        for symbol, bars in data.items():
            # Require sufficient data for indicator calculation
            required = self._rsi_period + 10
            if len(bars) < required:
                logger.warning(
                    "insufficient_data",
                    symbol=symbol,
                    bars=len(bars),
                    required=required,
                )
                continue

            # Convert to pandas DataFrame
            df = pd.DataFrame([bar.model_dump() for bar in bars])
            df = df.sort_values("timestamp")

            # Calculate RSI
            rsi_values = rsi(df["close"], period=self._rsi_period)
            if rsi_values is None or len(rsi_values) < 2:
                continue

            # Get current and previous RSI
            current_rsi = rsi_values.iloc[-1]
            prev_rsi = rsi_values.iloc[-2]

            # Generate signals
            direction = None
            strength = 0.0

            # BUY signal: RSI crosses below oversold threshold
            if prev_rsi > self._oversold >= current_rsi:
                direction = SignalDirection.BUY
                # Strength based on how far below threshold
                strength = min(1.0, (self._oversold - current_rsi) / self._oversold)

            # SELL signal: RSI crosses above overbought threshold
            elif prev_rsi < self._overbought <= current_rsi:
                direction = SignalDirection.SELL
                # Strength based on how far above threshold
                strength = min(1.0, (current_rsi - self._overbought) / (100 - self._overbought))

            # HOLD: No signal
            else:
                direction = SignalDirection.HOLD
                strength = 0.0

            if direction and strength > 0:
                signal = Signal(
                    symbol=symbol,
                    direction=direction,
                    strength=strength,
                    strategy_name=self.name,
                    metadata={
                        "rsi": float(current_rsi),
                        "prev_rsi": float(prev_rsi),
                        "threshold": self._oversold if direction == SignalDirection.BUY else self._overbought,
                    },
                )
                signals.append(signal)
                logger.info(
                    "signal_generated",
                    symbol=symbol,
                    direction=direction,
                    strength=strength,
                    rsi=current_rsi,
                )

        return signals
```

---

## Key Requirements

### 1. PDT Compliance

**CRITICAL:** `min_hold_days` must be >= 2 for swing trading.

```python
@property
def min_hold_days(self) -> int:
    return 2  # Minimum for PDT compliance
```

Day trading (holding < 1 day) triggers PDT restrictions (max 3 day trades per 5 business days for accounts under $25K). Strategies must enforce minimum 2-day holds.

---

### 2. Indicator Calculation

Use the `_indicators.py` shim for technical indicators:

```python
from src.strategy.builtin._indicators import rsi, sma, ema, bbands, macd
```

**Shim behavior:**
- Tries `pandas_ta` first (preferred)
- Falls back to `ta` library if `pandas_ta` unavailable
- Returns `None` if neither library is installed

**Handling None:**
```python
rsi_values = rsi(df["close"], period=14)
if rsi_values is None:
    logger.warning("rsi_calculation_failed", symbol=symbol)
    continue
```

---

### 3. Data Validation

Always check for sufficient data:

```python
required = max(rsi_period, sma_period) + 10  # Buffer for indicator warm-up
if len(bars) < required:
    logger.warning("insufficient_data", symbol=symbol, bars=len(bars))
    continue
```

---

### 4. Signal Strength

Signal strength is a float from 0.0 to 1.0:
- **0.0:** No signal (HOLD)
- **0.1-0.3:** Weak signal
- **0.4-0.6:** Moderate signal
- **0.7-0.9:** Strong signal
- **1.0:** Very strong signal (rare)

Strength is used for position sizing (Kelly criterion) and order prioritization.

---

### 5. Logging

Use structured logging for debugging:

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("signal_generated", symbol=symbol, direction=direction, strength=strength)
logger.warning("insufficient_data", symbol=symbol, bars=len(bars))
logger.error("indicator_calculation_failed", symbol=symbol, error=str(exc))
```

---

## Register Strategy

### Option 1: Add to Strategy Engine

**Location:** `src/strategy/engine.py`

```python
from src.strategy.builtin.rsi_simple import SimpleRSI

class StrategyEngine:
    def __init__(self):
        self._strategies = {
            "simple_rsi": SimpleRSI(),
            "momentum_crossover": MomentumCrossover(),
            # ... other strategies
        }
```

### Option 2: Dynamic Registration

```python
from src.strategy.engine import StrategyEngine
from src.strategy.builtin.rsi_simple import SimpleRSI

engine = StrategyEngine()
engine.register_strategy(SimpleRSI())
```

---

## Testing Your Strategy

### Unit Test

**Location:** `tests/unit/test_rsi_simple.py`

```python
import pytest
from datetime import datetime, timezone
from src.core.models import OHLCV, SignalDirection
from src.strategy.builtin.rsi_simple import SimpleRSI


def test_simple_rsi_buy_signal():
    """Test RSI oversold generates BUY signal."""
    strategy = SimpleRSI(rsi_period=14, oversold_threshold=30.0)

    # Generate OHLCV data with declining prices (RSI will drop)
    bars = []
    base_price = 100.0
    for i in range(50):
        bars.append(
            OHLCV(
                symbol="AAPL",
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                open=base_price - i * 0.5,
                high=base_price - i * 0.5 + 1,
                low=base_price - i * 0.5 - 1,
                close=base_price - i * 0.5,
                volume=1000000,
            )
        )

    signals = strategy.generate_signals({"AAPL": bars})

    assert len(signals) > 0
    assert signals[0].symbol == "AAPL"
    assert signals[0].direction == SignalDirection.BUY
    assert 0.0 < signals[0].strength <= 1.0
```

### Backtest

```python
from src.strategy.backtest import BacktestEngine
from src.strategy.builtin.rsi_simple import SimpleRSI

strategy = SimpleRSI()
engine = BacktestEngine()

result = await engine.run_backtest(
    strategy=strategy,
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    initial_capital=10000.0,
)

print(f"Sharpe ratio: {result.sharpe_ratio:.2f}")
print(f"Max drawdown: {result.max_drawdown_pct:.2f}%")
print(f"Win rate: {result.win_rate:.2f}%")
```

---

## Walk-Forward Validation

**Critical for preventing overfitting:**

```python
from src.strategy.backtest import walk_forward_validation

results = await walk_forward_validation(
    strategy=SimpleRSI(),
    start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
    end_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    train_window_days=180,  # 6 months training
    test_window_days=60,    # 2 months testing
    step_days=30,           # Slide forward 1 month
)

# Aggregate results
avg_sharpe = sum(r.sharpe_ratio for r in results) / len(results)
avg_drawdown = sum(r.max_drawdown_pct for r in results) / len(results)

print(f"Avg Sharpe (walk-forward): {avg_sharpe:.2f}")
print(f"Avg Max Drawdown: {avg_drawdown:.2f}%")
```

**Accept strategy if:**
- Walk-forward Sharpe > 1.0
- Max drawdown < 20%
- Consistent performance across periods

---

## Advanced: Multi-Indicator Strategy

Combine multiple indicators:

```python
from src.strategy.builtin._indicators import rsi, macd, bbands

class AdvancedStrategy(BaseStrategy):
    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        for symbol, bars in data.items():
            df = pd.DataFrame([bar.model_dump() for bar in bars])

            # Calculate indicators
            rsi_val = rsi(df["close"], period=14)
            macd_line, signal_line, _ = macd(df["close"])
            upper_bb, middle_bb, lower_bb = bbands(df["close"], period=20, std=2.0)

            # Confluence: All three indicators agree
            if (rsi_val.iloc[-1] < 30 and
                macd_line.iloc[-1] > signal_line.iloc[-1] and
                df["close"].iloc[-1] < lower_bb.iloc[-1]):
                # Strong BUY signal
                signal = Signal(
                    symbol=symbol,
                    direction=SignalDirection.BUY,
                    strength=0.9,  # High confidence
                    strategy_name=self.name,
                )
                signals.append(signal)
```

---

## Best Practices

1. **Keep it simple:** Start with one indicator, add complexity only if it improves performance
2. **Validate thoroughly:** Backtest on 2+ years, walk-forward validation, out-of-sample holdout
3. **Handle edge cases:** Missing data, indicator failures, symbol delisting
4. **Log everything:** Signals, rejections, errors — essential for debugging
5. **PDT compliance:** Never set `min_hold_days < 2`
6. **Avoid overfitting:** Don't optimize parameters to death; simple robust strategies beat complex fragile ones
7. **Paper trade first:** 30 days minimum before live capital

---

## Next Steps

- Read [Backtesting](../../specs/adrs/005-backtesting.md) for validation protocol
- See `src/strategy/builtin/` for more examples (momentum, mean reversion, ML)
- Check [Strategy Ranking](../modules/strategy.md) for performance metrics

---

<!-- DIAGRAM: Strategy lifecycle from signal generation through risk checks to order execution -->
