"""Analysis API routes: Monte Carlo simulation, market regime detection, portfolio optimizer."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class MonteCarloRequest(BaseModel):
    historical_returns: list[float]
    time_horizon_days: int = 252
    initial_value: float = 10000.0
    num_simulations: int = 10000
    num_paths_for_chart: int = 100


class RegimeRequest(BaseModel):
    spy_prices: list[float]
    vix_values: list[float]


class OptimizeRequest(BaseModel):
    strategy_returns: dict[str, list[float]]
    regime: str | None = None


@router.post("/monte-carlo")
async def run_monte_carlo(request: MonteCarloRequest):
    """Run a Monte Carlo simulation on the provided historical returns.

    Returns percentile bands (p5/p25/p50/p75/p95), probability of loss,
    VaR at 95% confidence, and a subset of simulation paths for charting.
    """
    if not request.historical_returns:
        raise HTTPException(status_code=400, detail="historical_returns must not be empty")

    if request.time_horizon_days <= 0:
        raise HTTPException(status_code=400, detail="time_horizon_days must be positive")

    from src.strategy.monte_carlo import MonteCarloSimulator

    simulator = MonteCarloSimulator(num_simulations=request.num_simulations)
    result = simulator.simulate(
        historical_returns=request.historical_returns,
        time_horizon_days=request.time_horizon_days,
        initial_value=request.initial_value,
        num_paths_for_chart=request.num_paths_for_chart,
    )
    return result.model_dump()


@router.get("/regime")
async def get_regime(spy_prices: str = "", vix_values: str = ""):
    """Get current market regime based on SPY prices and VIX values.

    Accepts comma-separated spy_prices and vix_values query parameters.
    If not provided, returns a stub response indicating insufficient data.

    For historical data already loaded in the system, pass the price series
    as query parameters or use POST /api/analysis/regime.
    """
    if not spy_prices or not vix_values:
        from src.core.models import MarketRegime, RegimeAnalysis
        return RegimeAnalysis(
            current_regime=MarketRegime.SIDEWAYS,
            regime_probability=0.5,
            strategy_performance_by_regime={},
            regime_history=[],
        ).model_dump()

    try:
        spy_list = [float(x) for x in spy_prices.split(",") if x.strip()]
        vix_list = [float(x) for x in vix_values.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="spy_prices and vix_values must be comma-separated floats",
        )

    from src.strategy.regime import RegimeDetector

    detector = RegimeDetector()
    result = detector.detect(spy_prices=spy_list, vix_values=vix_list)
    return result.model_dump()


@router.post("/regime")
async def detect_regime(request: RegimeRequest):
    """Detect market regime from SPY price series and VIX values.

    Returns current_regime, regime_probability, and regime_history.
    Minimum 200 data points required for a reliable regime call.
    """
    if not request.spy_prices or not request.vix_values:
        raise HTTPException(
            status_code=400,
            detail="spy_prices and vix_values must not be empty",
        )

    from src.strategy.regime import RegimeDetector

    detector = RegimeDetector()
    result = detector.detect(
        spy_prices=request.spy_prices,
        vix_values=request.vix_values,
    )
    return result.model_dump()


@router.post("/optimize")
async def optimize_allocation(request: OptimizeRequest):
    """Run mean-variance optimization across strategies to maximize Sharpe ratio.

    strategy_returns: dict mapping strategy name to list of daily returns.
    regime: Optional current market regime string (BULL/BEAR/SIDEWAYS/HIGH_VOLATILITY).

    Returns optimal weights per strategy, portfolio Sharpe, expected return, and volatility.
    """
    if not request.strategy_returns:
        raise HTTPException(
            status_code=400,
            detail="strategy_returns must not be empty",
        )

    from src.strategy.optimizer import MultiStrategyOptimizer
    from src.core.models import MarketRegime

    regime = None
    if request.regime:
        try:
            regime = MarketRegime(request.regime)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown regime '{request.regime}'. "
                       f"Valid values: {[r.value for r in MarketRegime]}",
            )

    optimizer = MultiStrategyOptimizer()
    result = optimizer.optimize(
        strategy_returns=request.strategy_returns,
        regime=regime,
    )
    return result.model_dump()
