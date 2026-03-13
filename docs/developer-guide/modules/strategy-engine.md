# Strategy Engine Module

The `src/strategy/` module orchestrates trading strategy registration, backtesting, walk-forward validation, and composite ranking. All strategies implement the `BaseStrategy` interface and enforce a minimum 2-day hold period for [PDT](../glossary.md#pdt) compliance.

## Purpose

The strategy engine provides:

- **Strategy registration** with validation (min_hold_days >= 2)
- **Backtesting** via pluggable engines (Backtrader, VectorBT)
- **Walk-forward analysis** for time-series robustness testing
- **Composite ranking** with configurable weights (Sharpe, Sortino, drawdown, profit factor, consistency)
- **Built-in strategies** (Swing Momentum, Mean Reversion, Value Factor) and ML strategy integration

## Key Components

### `StrategyEngine` (src/strategy/engine.py)

Central orchestrator for strategy lifecycle.

**Methods:**

| Method | Purpose | Returns |
|--------|---------|---------|
| `register_strategy(strategy: BaseStrategy)` | Register a strategy (validates `min_hold_days >= 2`) | None (raises ValueError if invalid) |
| `get_strategy(name: str)` | Retrieve registered strategy by name | BaseStrategy |
| `list_strategies()` | List all registered strategy names | list[str] |
| `run_backtest(strategy_name, data, initial_capital, start, end)` | Run single-period backtest | BacktestResult |
| `run_walk_forward(strategy_name, data, initial_capital)` | Run walk-forward validation | list[BacktestResult] |
| `rank_strategies(strategy_names)` | Rank strategies by composite score | list[StrategyRanking] |

**Validation:**
```python
def register_strategy(self, strategy: BaseStrategy) -> None:
    if strategy.min_hold_days < 2:
        raise ValueError(
            f"Strategy '{strategy.name}' has min_hold_days={strategy.min_hold_days}. "
            "Minimum is 2 days (PDT rule)."
        )
    self._strategies[strategy.name] = strategy
```

All strategies must hold positions for at least 2 days to avoid [PDT](../glossary.md#pdt) violations (4 day trades in 5 business days triggers account restrictions for accounts under $25K).

### `BaseStrategy` Interface (src/core/interfaces.py)

All strategies inherit from `BaseStrategy` ABC.

**Required Properties:**
- `name: str` — Unique identifier (e.g., "SwingMomentum")
- `description: str` — Human-readable explanation
- `min_hold_days: int` — Minimum holding period (must be >= 2)

**Required Methods:**
- `generate_signals(data: dict[str, list[OHLCV]]) -> list[Signal]` — Core logic. Takes symbol → bars mapping, returns list of signals.
- `get_parameters() -> dict[str, Any]` — Return strategy hyperparameters (e.g., `{"rsi_period": 14}`).
- `get_required_data() -> list[str]` — Declare data dependencies (e.g., `["ohlcv", "fundamentals"]`).

**Example:**
```python
from src.core.interfaces import BaseStrategy
from src.core.models import Signal, SignalDirection, OHLCV

class MyStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "MyStrategy"

    @property
    def description(self) -> str:
        return "Simple RSI strategy"

    @property
    def min_hold_days(self) -> int:
        return 3  # Hold for at least 3 days

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        signals = []
        for symbol, bars in data.items():
            # Compute indicators using _indicators.py shim (see below)
            # Generate LONG/SHORT/FLAT signals
            signals.append(Signal(
                symbol=symbol,
                timestamp=bars[-1].timestamp,
                direction=SignalDirection.LONG,
                strength=0.75,
                strategy_name=self.name,
            ))
        return signals

    def get_parameters(self) -> dict[str, Any]:
        return {"rsi_period": 14, "rsi_overbought": 70, "rsi_oversold": 30}

    def get_required_data(self) -> list[str]:
        return ["ohlcv"]
```

### Built-in Strategies

Three strategies in `src/strategy/builtin/`:

#### 1. `SwingMomentumStrategy` (src/strategy/builtin/swing_momentum.py)

**Logic:**
- LONG: RSI(14) < 30 (oversold) + price > SMA(50) (uptrend)
- SHORT: RSI(14) > 70 (overbought) + price < SMA(50) (downtrend)
- Signal strength: Scaled by distance from RSI threshold

**Parameters:**
- `rsi_period`: 14
- `sma_period`: 50
- `rsi_oversold`: 30
- `rsi_overbought`: 70

**min_hold_days:** 3

**Required Data:** `["ohlcv"]`

#### 2. `MeanReversionStrategy` (src/strategy/builtin/mean_reversion.py)

**Logic:**
- LONG: Price < Bollinger Lower Band (2 std dev below 20-period SMA)
- SHORT: Price > Bollinger Upper Band (2 std dev above 20-period SMA)
- Signal strength: Scaled by distance from band

**Parameters:**
- `bb_period`: 20
- `bb_std`: 2.0

**min_hold_days:** 2

**Required Data:** `["ohlcv"]`

#### 3. `ValueFactorStrategy` (src/strategy/builtin/value_factor.py)

**Logic:**
- LONG: P/E < sector average, ROE > 15%, debt-to-equity < 0.5, positive revenue growth
- Signal strength: Composite of valuation, profitability, and growth scores

**Parameters:**
- `min_roe`: 15.0
- `max_debt_to_equity`: 0.5
- `min_revenue_growth`: 0.0

**min_hold_days:** 5 (longer hold for fundamental strategies)

**Required Data:** `["ohlcv", "fundamentals"]`

### Technical Indicators Shim

#### `_indicators.py` (src/strategy/builtin/_indicators.py)

Provides fallback mechanism for technical indicators:

1. **Try pandas_ta first** (full-featured, 130+ indicators)
2. **Fall back to ta library** (lightweight, 50+ indicators)
3. **Raise ImportError** if neither is available

**Usage:**
```python
from src.strategy.builtin._indicators import compute_rsi, compute_sma, compute_bbands

bars = [...]  # list[OHLCV]
closes = [b.close for b in bars]

rsi = compute_rsi(closes, period=14)
sma = compute_sma(closes, period=50)
upper, middle, lower = compute_bbands(closes, period=20, std=2.0)
```

**Why the shim?**
- pandas_ta has complex dependencies (requires pandas, numpy, scipy) and can be slow to import.
- ta library is lighter but less feature-rich.
- Lazy import: `_indicators.py` imports pandas_ta/ta inside function bodies, not at module top-level, avoiding load-time errors if ML deps are missing.

### Strategy Ranker

#### `StrategyRanker` (src/strategy/ranker.py)

Ranks strategies by a composite score combining multiple performance metrics.

**Ranking Weights** (configurable via `config/settings.yaml`):
- `sharpe`: 30% (risk-adjusted return)
- `sortino`: 20% (downside risk-adjusted return)
- `max_drawdown_inverse`: 20% (lower drawdown = higher score)
- `profit_factor`: 15% (gross profit / gross loss)
- `consistency`: 15% (walk-forward stability)

**Thresholds** (must meet ALL to be considered production-ready):
- `min_sharpe_ratio`: 1.0
- `min_profit_factor`: 1.5
- `max_drawdown_pct`: 20.0
- `min_trades`: 100

**Composite Score Calculation:**
```python
# Normalize each component to [0, 1]
sharpe_norm = max(0.0, min(sharpe_ratio / 3.0, 1.0))
sortino_norm = max(0.0, min(sortino_ratio / 4.0, 1.0))
dd_norm = max(0.0, 1.0 - max_drawdown_pct / 50.0)
pf_norm = max(0.0, min((profit_factor - 1.0) / 2.0, 1.0))
consistency_norm = max(0.0, min(consistency, 1.0))

composite = (
    0.30 * sharpe_norm +
    0.20 * sortino_norm +
    0.20 * dd_norm +
    0.15 * pf_norm +
    0.15 * consistency_norm
)
```

**Consistency Score** (for walk-forward results):
```python
consistency = 1.0 - (std_dev(annual_returns) / mean(annual_returns))
```

High consistency means stable performance across train/test splits.

**Usage:**
```python
from src.strategy.ranker import StrategyRanker

ranker = StrategyRanker()
results = [backtest_result_1, backtest_result_2, ...]
wf_results = {"Strategy1": [wf_result_1, wf_result_2, ...], ...}

rankings = ranker.rank_strategies(results, walk_forward_results=wf_results)
# Returns list of StrategyRanking sorted by composite_score (highest first)

for rank in rankings:
    print(f"{rank.strategy_name}: {rank.composite_score:.4f} (meets thresholds: {rank.meets_thresholds})")
```

### Backtest Engines

Pluggable backtest engines implement `BacktestEngine` interface.

#### `BacktraderEngine` (src/strategy/backtest/backtrader_engine.py)

Event-driven backtest engine using [Backtrader](https://www.backtrader.com/) framework.

**Methods:**
- `run(strategy, data, initial_capital, start, end) -> BacktestResult`
- `walk_forward(strategy, data, initial_capital, train_months=24, test_months=6, step_months=3) -> list[BacktestResult]`

**Walk-Forward Logic:**
1. Split data into overlapping train/test windows (e.g., train on 24 months, test on 6 months, step forward 3 months).
2. For each window:
   - Train strategy on training period (if strategy supports training, e.g., ML models).
   - Run backtest on test period.
   - Collect `BacktestResult`.
3. Return list of results (one per test window).

**Features:**
- Commission: 0.005% per trade (IBKR tier)
- Slippage: 0.05% (configurable)
- Position sizing: Uses Kelly criterion via `OrderGenerator`
- Stop-loss orders: Automatic via `Order.stop_price`

#### `VectorBTEngine` (src/strategy/backtest/vectorbt_engine.py)

Vectorized backtest engine using [VectorBT](https://vectorbt.dev/) for faster computation.

**Advantages:**
- 10-100x faster than Backtrader for simple strategies (no event-driven overhead)
- Matrix operations via NumPy/Pandas

**Limitations:**
- Less flexible for complex order logic (brackets, conditional orders)
- Not suitable for strategies with dynamic position sizing

### Walk-Forward Validation

Walk-forward analysis tests strategy robustness by simulating real-world conditions:

1. **Rolling window:** Train on 24 months, test on 6 months.
2. **Step forward:** Advance 3 months, re-train, re-test.
3. **Out-of-sample results:** Test periods never overlap with training periods.

**Configuration** (config/settings.yaml):
```yaml
strategy:
  walk_forward:
    train_months: 24
    test_months: 6
    step_months: 3
```

**Example:**
```
Data: 2020-01-01 to 2023-12-31 (4 years)

Window 1:
  Train: 2020-01-01 to 2021-12-31 (24 months)
  Test:  2022-01-01 to 2022-06-30 (6 months)

Window 2:
  Train: 2020-04-01 to 2022-03-31 (24 months)
  Test:  2022-04-01 to 2022-09-30 (6 months)

Window 3:
  Train: 2020-07-01 to 2022-06-30 (24 months)
  Test:  2022-07-01 to 2022-12-31 (6 months)

...and so on
```

**Output:**
- Multiple `BacktestResult` objects (one per window)
- Consistency score computed from variance across windows
- Reveals overfitting: strategy with high backtest return but low walk-forward consistency is likely curve-fit

## Integration with Other Modules

- **ML Pipeline** (`src/signals/ml_strategy.py`): `MLSignalStrategy` wraps XGBoost predictions as a strategy. Sets `min_hold_days=3`.
- **Execution Engine** (`src/execution/engine.py`): Converts signals → orders via `OrderGenerator`.
- **Risk Manager** (`src/risk/manager.py`): Validates orders against position/portfolio limits before execution.
- **API** (`src/api/routes/strategies.py`): Exposes endpoints to list strategies, trigger backtests, fetch rankings.

## Configuration

**Settings (config/settings.yaml):**
```yaml
strategy:
  min_sharpe_ratio: 1.0
  min_profit_factor: 1.5
  max_drawdown_pct: 20.0
  min_trades: 100
  walk_forward:
    train_months: 24
    test_months: 6
    step_months: 3
  ranking_weights:
    sharpe: 0.30
    sortino: 0.20
    max_drawdown_inverse: 0.20
    profit_factor: 0.15
    consistency: 0.15
```

**Environment Variable Overrides:**
```bash
export SA_STRATEGY__MIN_SHARPE_RATIO=1.5
export SA_STRATEGY__WALK_FORWARD__TRAIN_MONTHS=18
export SA_STRATEGY__RANKING_WEIGHTS__SHARPE=0.40
```

## Critical Patterns

1. **PDT enforcement:** `StrategyEngine.register_strategy()` rejects strategies with `min_hold_days < 2`.
2. **Signal strength [0.0, 1.0]:** Higher strength → larger position size (via Kelly criterion).
3. **Metadata for order generation:** Signals include `metadata={"win_rate": 0.55, "avg_win_pct": 2.0, "avg_loss_pct": 1.0}` for Kelly sizing.
4. **Data alignment:** Strategies receive `dict[str, list[OHLCV]]` — all symbols aligned to same date range.
5. **Lazy indicator imports:** `_indicators.py` shim avoids load-time errors if pandas_ta is missing.

## Glossary Links

- [PDT](../glossary.md#pdt) — Pattern Day Trader rule
- [OHLCV](../glossary.md#ohlcv) — Open/High/Low/Close/Volume bar data
- [Sharpe Ratio](../glossary.md#sharpe-ratio) — Risk-adjusted return metric
- [Sortino Ratio](../glossary.md#sortino-ratio) — Downside risk-adjusted return metric
- [XGBoost](../glossary.md#xgboost) — Gradient boosting ML library

<!-- DIAGRAM: Strategy engine flow — registration → backtest → walk-forward → ranking → signal generation → execution -->
