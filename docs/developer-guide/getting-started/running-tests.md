# Running Tests

The **alpha-oracle** project uses **pytest** for testing, with 669 unit tests covering all major subsystems. This page documents how to run the test suite, test organization, and key testing patterns.

## Running All Tests

From the project root (with venv activated):

```bash
python -m pytest tests/ -v
```

**Flags:**
- `-v`: Verbose output (shows each test name)
- `-s`: Show print statements (disable output capture)
- `-x`: Stop on first failure
- `--lf`: Run only last failed tests
- `--ff`: Run failed tests first, then others

**Parallel execution** (faster, requires `pytest-xdist`):

```bash
pip install pytest-xdist
python -m pytest tests/ -n auto
```

## Running Specific Tests

### Run a Single Test File

```bash
python -m pytest tests/unit/test_pdt_guard.py -v
```

### Run a Specific Test Function

```bash
python -m pytest tests/unit/test_pdt_guard.py::test_pdt_guard_allows_swing_trades -v
```

### Run Tests by Marker

The project uses pytest markers for categorization:

```bash
# Run only slow tests
python -m pytest -m slow

# Run only integration tests
python -m pytest -m integration

# Skip slow tests
python -m pytest -m "not slow"
```

Markers are defined in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: marks tests as slow",
    "integration: marks integration tests",
]
```

### Run Tests by Pattern

```bash
# Run all tests matching "pdt"
python -m pytest tests/ -k pdt -v

# Run all tests matching "strategy" but not "backtest"
python -m pytest tests/ -k "strategy and not backtest" -v
```

## Test Organization

Tests are organized in `tests/unit/` with file names mirroring the `src/` module structure:

```
tests/
├── conftest.py                    # Shared pytest fixtures
└── unit/
    ├── test_pdt_guard.py          # src/risk/pdt_guard.py
    ├── test_pre_trade.py          # src/risk/pre_trade.py
    ├── test_strategy_engine.py    # src/strategy/engine.py
    ├── test_ml_strategy.py        # src/signals/ml_strategy.py
    ├── test_ml_pipeline.py        # src/signals/ml/pipeline.py
    ├── test_feature_store.py      # src/signals/feature_store.py
    ├── test_smart_router.py       # src/execution/router.py
    ├── test_ibkr_adapter.py       # src/execution/broker_adapters/ibkr_adapter.py
    ├── test_simulated_broker.py   # src/execution/broker_adapters/simulated.py
    ├── test_market_feed.py        # src/data/feeds/ibkr_feed.py
    ├── test_jobs.py               # src/scheduling/jobs.py
    ├── test_retrain_job.py        # src/scheduling/weekly_retrain_job.py
    ├── test_model_registry.py     # src/signals/ml/registry.py
    ├── test_model_monitoring.py   # src/signals/ml/monitoring.py
    └── ...
```

## Key Test Patterns

### 1. Async Tests

Most tests use `pytest-asyncio` for async functions:

```python
import pytest

@pytest.mark.asyncio
async def test_submit_order():
    adapter = IBKRBrokerAdapter(...)
    order = Order(symbol="AAPL", side=OrderSide.BUY, ...)
    result = await adapter.submit_order(order)
    assert result.status == OrderStatus.SUBMITTED
```

The `asyncio_mode = "auto"` setting in `pyproject.toml` automatically detects async tests.

### 2. Fixtures

Shared fixtures are defined in `tests/conftest.py`:

```python
@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    return MagicMock(spec=Redis)

@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy async session."""
    session = AsyncMock(spec=AsyncSession)
    return session

@pytest.fixture
def sample_ohlcv():
    """Sample OHLCV data for testing strategies."""
    return [
        OHLCV(symbol="AAPL", timestamp=datetime(2024, 1, 1), open=150.0, ...),
        OHLCV(symbol="AAPL", timestamp=datetime(2024, 1, 2), open=151.0, ...),
    ]
```

Use fixtures in tests:

```python
def test_strategy_signal_generation(sample_ohlcv):
    strategy = MomentumStrategy()
    signals = strategy.generate_signals({"AAPL": sample_ohlcv})
    assert len(signals) > 0
```

### 3. Mocking with `unittest.mock`

Tests use `patch` to mock external dependencies:

```python
from unittest.mock import patch, AsyncMock

@pytest.mark.asyncio
async def test_daily_bars_job():
    # Patch at the source module path (due to lazy imports in job functions)
    with patch('src.data.storage.TimeSeriesStorage') as MockStorage:
        mock_storage = AsyncMock()
        MockStorage.return_value = mock_storage

        # Run job
        await daily_bars_job()

        # Assert storage was called
        mock_storage.store_bars.assert_called()
```

**Important**: Always patch at the **source module path** (e.g., `src.data.storage.TimeSeriesStorage`), not the import path, because job functions use lazy imports (imports inside the function body, not at module top-level).

### 4. Property-Based Testing

Some tests use `hypothesis` for property-based testing:

```python
from hypothesis import given
from hypothesis.strategies import floats, integers

@given(price=floats(min_value=1.0, max_value=1000.0),
       quantity=integers(min_value=1, max_value=1000))
def test_kelly_criterion_sizing(price, quantity):
    """Kelly sizing should never exceed account equity."""
    order = generate_order(price=price, quantity=quantity)
    assert order.notional <= ACCOUNT_EQUITY
```

## Important Test Suites

### PDT Guard Tests

The [PDT guard](../glossary.md#pdt) is the most critical safety component. Test coverage includes:

```bash
python -m pytest tests/unit/test_pdt_guard.py -v
```

**Key tests:**
- `test_pdt_guard_allows_swing_trades` — Holds >= 2 days are approved
- `test_pdt_guard_rejects_day_trades` — Same-day round trips are rejected
- `test_pdt_guard_counts_rolling_window` — Respects 5 business day window
- `test_pdt_guard_allows_under_25k` — Accounts under $25K get strict enforcement
- `test_pdt_guard_bypasses_over_25k` — Accounts over $25K are exempt

### Risk Check Tests

Pre-trade and portfolio risk checks:

```bash
python -m pytest tests/unit/test_pre_trade.py -v
python -m pytest tests/unit/test_portfolio_monitor.py -v
```

### Strategy Engine Tests

Strategy signal generation and backtesting:

```bash
python -m pytest tests/unit/test_strategy_engine.py -v
python -m pytest tests/unit/test_strategy_backtests.py -v
```

### ML Pipeline Tests

Feature store, model training, and prediction:

```bash
python -m pytest tests/unit/test_feature_store.py -v
python -m pytest tests/unit/test_ml_pipeline.py -v
python -m pytest tests/unit/test_ml_strategy.py -v
python -m pytest tests/unit/test_ml_validation.py -v
```

### Execution Tests

Smart order router and broker adapters:

```bash
python -m pytest tests/unit/test_smart_router.py -v
python -m pytest tests/unit/test_ibkr_adapter.py -v
python -m pytest tests/unit/test_simulated_broker.py -v
```

### Scheduler Tests

APScheduler cron jobs and model registry:

```bash
python -m pytest tests/unit/test_jobs.py -v
python -m pytest tests/unit/test_retrain_job.py -v
python -m pytest tests/unit/test_model_registry.py -v
```

### API Route Tests

FastAPI endpoint tests (when available):

```bash
python -m pytest tests/unit/test_api_routes.py -v
```

## Test Coverage

Generate a coverage report:

```bash
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=html
```

Open `htmlcov/index.html` in a browser to view line-by-line coverage.

**Coverage goals:**
- Core modules (`core/`, `risk/`, `execution/`): 95%+
- Data/strategy modules: 85%+
- API routes: 80%+

## Continuous Integration

The test suite runs on every commit via GitHub Actions (if configured). The CI pipeline:

1. Installs dependencies (including TA-Lib)
2. Starts Docker services (TimescaleDB, Redis)
3. Runs `pytest tests/ --cov=src`
4. Uploads coverage reports to Codecov

## Troubleshooting

### Tests Fail with "No module named 'src'"

**Solution**: Ensure you're running pytest from the project root and have installed the package in editable mode:

```bash
pip install -e .
```

### Tests Hang on Async Functions

**Symptom**: Tests time out or hang indefinitely.

**Solution**: Check for missing `await` keywords or unclosed async resources (sessions, clients). Use `pytest-timeout`:

```bash
pip install pytest-timeout
python -m pytest tests/ --timeout=10  # Fail tests after 10s
```

### Import Errors for TA-Lib

**Symptom**: `ModuleNotFoundError: No module named 'talib'`

**Solution**: The project uses a fallback (`ta` library) if TA-Lib is unavailable. Tests should pass without it. To install TA-Lib, see [Prerequisites](prerequisites.md#ta-lib-c-library).

### Mock Patching Not Working

**Symptom**: Mocked functions are still called or assertions fail.

**Solution**: Patch at the **source module path**, not the import path. For lazy imports in job functions:

```python
# Correct: patch where the class is defined
with patch('src.data.storage.TimeSeriesStorage') as MockStorage:
    ...

# Incorrect: patching the import target won't work for lazy imports
with patch('src.scheduling.jobs.TimeSeriesStorage') as MockStorage:
    ...
```

## Next Steps

- [Architecture Overview](../architecture/overview.md) — Understand the system design
- [Module Map](../architecture/module-map.md) — Explore tested modules
- [Extending](../extending/index.md) — Write custom strategies with tests
