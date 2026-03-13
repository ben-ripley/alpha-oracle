# Adding API Routes

The FastAPI backend exposes REST endpoints for the dashboard and external integrations. All routes follow a consistent pattern using FastAPI routers and dependency injection.

## Router Pattern

**Location:** `src/api/routes/`

Each module has its own router file:
- `portfolio.py` — Portfolio and position endpoints
- `strategies.py` — Strategy management endpoints
- `risk.py` — Risk metrics and circuit breaker endpoints
- `trades.py` — Trade history and order book endpoints
- `system.py` — System health and scheduler endpoints
- `websocket.py` — WebSocket endpoint for real-time updates

---

## Example: Add a New Route

### Scenario: Add a `/api/backtest` endpoint to trigger backtests

### 1. Create Router File

**Location:** `src/api/routes/backtest.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.strategy.backtest import BacktestEngine
from src.strategy.builtin.momentum import MomentumCrossover
from src.core.models import BacktestResult

logger = structlog.get_logger()

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


# Request/Response Models
class BacktestRequest(BaseModel):
    """Request model for triggering a backtest."""
    strategy_name: str = Field(..., description="Strategy to backtest")
    start_date: datetime = Field(..., description="Backtest start date (UTC)")
    end_date: datetime = Field(..., description="Backtest end date (UTC)")
    initial_capital: float = Field(10000.0, description="Starting capital (USD)")


class BacktestResponse(BaseModel):
    """Response model for backtest results."""
    strategy_name: str
    sharpe_ratio: float
    max_drawdown_pct: float
    total_return_pct: float
    total_trades: int
    win_rate: float


# Dependency: Get BacktestEngine instance
async def get_backtest_engine() -> BacktestEngine:
    """Dependency to provide BacktestEngine instance."""
    return BacktestEngine()


# Routes
@router.post("/run", response_model=BacktestResponse)
async def run_backtest(
    request: BacktestRequest,
    engine: BacktestEngine = Depends(get_backtest_engine),
) -> BacktestResponse:
    """Run a backtest for the specified strategy.

    Args:
        request: Backtest parameters
        engine: BacktestEngine instance (injected)

    Returns:
        Backtest performance metrics

    Raises:
        HTTPException: If strategy not found or backtest fails
    """
    logger.info(
        "backtest.run_requested",
        strategy=request.strategy_name,
        start=request.start_date,
        end=request.end_date,
    )

    # Map strategy name to strategy instance
    strategy_map = {
        "momentum_crossover": MomentumCrossover(),
        # Add other strategies here
    }

    strategy = strategy_map.get(request.strategy_name)
    if not strategy:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{request.strategy_name}' not found",
        )

    try:
        result = await engine.run_backtest(
            strategy=strategy,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
        )

        logger.info(
            "backtest.completed",
            strategy=request.strategy_name,
            sharpe=result.sharpe_ratio,
            drawdown=result.max_drawdown_pct,
        )

        return BacktestResponse(
            strategy_name=request.strategy_name,
            sharpe_ratio=result.sharpe_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            total_return_pct=result.total_return_pct,
            total_trades=result.total_trades,
            win_rate=result.win_rate,
        )

    except Exception as exc:
        logger.error("backtest.failed", strategy=request.strategy_name, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Backtest failed: {str(exc)}",
        )


@router.get("/history", response_model=list[BacktestResult])
async def get_backtest_history(
    strategy_name: Optional[str] = Query(None, description="Filter by strategy"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
) -> list[BacktestResult]:
    """Retrieve historical backtest results.

    Args:
        strategy_name: Optional strategy filter
        limit: Maximum number of results (1-100)

    Returns:
        List of backtest results, most recent first
    """
    logger.info("backtest.history_requested", strategy=strategy_name, limit=limit)

    # Query database for backtest results
    from src.core.database import get_session

    async with get_session() as session:
        query = "SELECT * FROM backtest_results"
        if strategy_name:
            query += f" WHERE strategy_name = '{strategy_name}'"
        query += f" ORDER BY run_at DESC LIMIT {limit}"

        result = await session.execute(query)
        rows = result.fetchall()

        return [BacktestResult(**dict(row)) for row in rows]
```

---

### 2. Register Router

**Location:** `src/api/main.py`

```python
from src.api.routes import portfolio, strategies, risk, trades, system, websocket, backtest

app = FastAPI(title="Stock Analysis API")

# Register routers
app.include_router(portfolio.router)
app.include_router(strategies.router)
app.include_router(risk.router)
app.include_router(trades.router)
app.include_router(system.router)
app.include_router(websocket.router)
app.include_router(backtest.router)  # NEW
```

---

### 3. Test the Route

**Manual test:**
```bash
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "momentum_crossover",
    "start_date": "2024-01-01T00:00:00Z",
    "end_date": "2024-12-31T23:59:59Z",
    "initial_capital": 10000.0
  }'
```

**Response:**
```json
{
  "strategy_name": "momentum_crossover",
  "sharpe_ratio": 1.23,
  "max_drawdown_pct": -8.5,
  "total_return_pct": 15.2,
  "total_trades": 42,
  "win_rate": 58.3
}
```

---

## Dependency Injection

FastAPI's dependency injection provides clean separation of concerns:

### Database Session

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_session

@router.get("/portfolio")
async def get_portfolio(session: AsyncSession = Depends(get_session)):
    result = await session.execute("SELECT * FROM portfolio_snapshots ORDER BY timestamp DESC LIMIT 1")
    return result.fetchone()
```

### Broker Adapter

```python
from src.api.dependencies import get_broker
from src.core.interfaces import BrokerAdapter

@router.post("/orders")
async def submit_order(order: Order, broker: BrokerAdapter = Depends(get_broker)):
    submitted_order = await broker.submit_order(order)
    return submitted_order
```

### Settings

```python
from src.core.config import Settings, get_settings

@router.get("/config")
async def get_config(settings: Settings = Depends(get_settings)):
    return {
        "paper_trading": settings.broker.paper_trading,
        "autonomy_mode": settings.risk.autonomy_mode,
    }
```

---

## Request/Response Models

Use Pydantic models for type safety and automatic validation:

```python
from pydantic import BaseModel, Field, validator

class OrderRequest(BaseModel):
    """Request model for submitting an order."""
    symbol: str = Field(..., min_length=1, max_length=10)
    side: str = Field(..., regex="^(BUY|SELL)$")
    quantity: float = Field(..., gt=0)
    order_type: str = Field("MARKET", regex="^(MARKET|LIMIT|STOP|STOP_LIMIT)$")
    limit_price: Optional[float] = Field(None, gt=0)

    @validator("limit_price")
    def limit_price_required_for_limit_orders(cls, v, values):
        if values.get("order_type") == "LIMIT" and v is None:
            raise ValueError("limit_price is required for LIMIT orders")
        return v


@router.post("/orders", response_model=OrderResponse)
async def submit_order(request: OrderRequest):
    # FastAPI automatically validates request body
    # Invalid requests return 422 Unprocessable Entity
    ...
```

**Benefits:**
- Automatic validation (422 errors for invalid input)
- Auto-generated OpenAPI documentation
- Type safety and IDE autocomplete

---

## Error Handling

Use `HTTPException` for expected errors:

```python
from fastapi import HTTPException

@router.get("/portfolio/{account_id}")
async def get_portfolio(account_id: str):
    portfolio = await fetch_portfolio(account_id)
    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail=f"Portfolio not found for account {account_id}",
        )
    return portfolio
```

**Common status codes:**
- `400 Bad Request` — Invalid input (use validation instead)
- `401 Unauthorized` — Missing authentication (future)
- `403 Forbidden` — Insufficient permissions
- `404 Not Found` — Resource doesn't exist
- `422 Unprocessable Entity` — Validation error (automatic)
- `500 Internal Server Error` — Unexpected error
- `503 Service Unavailable` — Dependency unavailable (e.g., IB Gateway down)

---

## WebSocket Event Broadcasting

Publish events to Redis pub/sub for WebSocket clients:

```python
from src.core.redis import get_redis
import json

@router.post("/orders")
async def submit_order(order: Order):
    # Submit order to broker
    submitted = await broker.submit_order(order)

    # Broadcast order status to WebSocket clients
    redis = await get_redis()
    await redis.publish(
        "order:status",
        json.dumps({
            "id": submitted.id,
            "symbol": submitted.symbol,
            "status": submitted.status,
            "broker_order_id": submitted.broker_order_id,
        })
    )

    return submitted
```

**Channels:** See [WebSocket Events](../frontend/websocket-events.md) for full list.

---

## OpenAPI Documentation

FastAPI auto-generates OpenAPI (Swagger) docs:

**Access:** http://localhost:8000/docs

**Customize:**
```python
@router.post(
    "/backtest/run",
    response_model=BacktestResponse,
    summary="Run a backtest",
    description="Execute a backtest for a strategy over a specified date range",
    tags=["backtest"],
    status_code=200,
)
async def run_backtest(request: BacktestRequest):
    ...
```

---

## Testing API Routes

### Unit Test (pytest)

**Location:** `tests/unit/test_backtest_routes.py`

```python
import pytest
from httpx import AsyncClient
from src.api.main import app


@pytest.mark.asyncio
async def test_run_backtest_success():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/backtest/run",
            json={
                "strategy_name": "momentum_crossover",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
                "initial_capital": 10000.0,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["strategy_name"] == "momentum_crossover"
    assert "sharpe_ratio" in data


@pytest.mark.asyncio
async def test_run_backtest_invalid_strategy():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/backtest/run",
            json={
                "strategy_name": "nonexistent",
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-12-31T23:59:59Z",
            },
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
```

---

## Best Practices

1. **Use routers for organization** — Group related endpoints in separate files
2. **Define request/response models** — Pydantic models for validation and docs
3. **Dependency injection** — Use `Depends()` for database, settings, services
4. **Log all requests** — Structured logging with context
5. **Return typed responses** — `response_model` ensures consistent output
6. **Handle errors explicitly** — Use `HTTPException` for expected errors
7. **Document endpoints** — Add `summary`, `description`, `tags` for OpenAPI
8. **Validate input** — Use Pydantic validators for complex rules
9. **Broadcast events** — Publish to Redis pub/sub for WebSocket clients
10. **Test thoroughly** — Unit tests with `AsyncClient`, mock dependencies

---

## Advanced: Background Tasks

For long-running operations, use background tasks:

```python
from fastapi import BackgroundTasks

async def run_backtest_async(strategy_name: str, start_date: datetime, end_date: datetime):
    """Background task to run backtest."""
    result = await backtest_engine.run_backtest(...)
    # Store result in database
    await store_result(result)
    # Publish completion event
    await redis.publish("backtest:completed", json.dumps(result.dict()))


@router.post("/backtest/run-async")
async def run_backtest_async_endpoint(
    request: BacktestRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger a backtest as a background task."""
    task_id = str(uuid.uuid4())
    background_tasks.add_task(
        run_backtest_async,
        request.strategy_name,
        request.start_date,
        request.end_date,
    )
    return {"task_id": task_id, "status": "started"}
```

**For heavy workloads**, consider using a task queue (Celery, Dramatiq) instead.

---

## Next Steps

- Explore existing routes in `src/api/routes/` for examples
- Read [FastAPI documentation](https://fastapi.tiangolo.com/) for advanced features
- Check [OpenAPI spec](http://localhost:8000/openapi.json) for API contract

---

<!-- DIAGRAM: FastAPI request flow showing router → dependency injection → business logic → response model → client -->
