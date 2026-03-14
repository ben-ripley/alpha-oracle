"""Monte Carlo simulation for portfolio/strategy return distributions."""
from __future__ import annotations

import numpy as np
import structlog

from src.core.models import MonteCarloResult

logger = structlog.get_logger(__name__)


class MonteCarloSimulator:
    """Bootstrapped Monte Carlo simulation from historical returns."""

    def __init__(self, num_simulations: int = 10000) -> None:
        self.num_simulations = num_simulations

    def simulate(
        self,
        historical_returns: list[float],
        time_horizon_days: int = 252,
        initial_value: float = 10000.0,
        num_paths_for_chart: int = 100,
        seed: int | None = None,
    ) -> MonteCarloResult:
        """Bootstrap simulation: sample with replacement from historical returns.

        Args:
            historical_returns: Daily return values (e.g. 0.01 for +1%).
            time_horizon_days: Number of days to simulate forward.
            initial_value: Starting portfolio value.
            num_paths_for_chart: Number of paths to include in result for charting.
            seed: Optional random seed for reproducibility.

        Returns:
            MonteCarloResult with percentile bands, VaR, probability of loss,
            and a subset of simulation paths for charting.
        """
        if not historical_returns:
            logger.warning("monte_carlo_no_returns", msg="Empty historical returns, returning zeros")
            return MonteCarloResult(
                num_simulations=self.num_simulations,
                time_horizon_days=time_horizon_days,
                percentiles={"p5": [], "p25": [], "p50": [], "p75": [], "p95": []},
                probability_of_loss=0.0,
                value_at_risk_95=0.0,
                simulation_paths=[],
            )

        rng = np.random.default_rng(seed)
        returns_arr = np.array(historical_returns, dtype=float)

        # Bootstrap: sample with replacement for each simulation path
        # Shape: (num_simulations, time_horizon_days)
        sampled = rng.choice(returns_arr, size=(self.num_simulations, time_horizon_days), replace=True)

        # Compute cumulative portfolio values along each path
        # (1 + r1) * (1 + r2) * ... — use cumprod of (1 + returns)
        growth_factors = 1.0 + sampled
        cum_products = np.cumprod(growth_factors, axis=1)  # shape: (num_simulations, time_horizon_days)
        portfolio_values = initial_value * cum_products  # shape: (num_simulations, time_horizon_days)

        # Percentile bands across all simulations at each time step
        pct_levels = [5, 25, 50, 75, 95]
        pct_keys = ["p5", "p25", "p50", "p75", "p95"]
        percentiles: dict[str, list[float]] = {}
        for key, level in zip(pct_keys, pct_levels):
            percentiles[key] = np.percentile(portfolio_values, level, axis=0).tolist()

        # Final values at end of horizon
        final_values = portfolio_values[:, -1]

        # Probability of loss: fraction of paths ending below initial_value
        probability_of_loss = float(np.mean(final_values < initial_value))

        # VaR at 95% confidence: the 5th percentile loss (positive number = loss)
        p5_final = float(np.percentile(final_values, 5))
        value_at_risk_95 = float(max(initial_value - p5_final, 0.0))

        # Subset of paths for charting
        chart_indices = rng.choice(self.num_simulations, size=min(num_paths_for_chart, self.num_simulations), replace=False)
        simulation_paths = portfolio_values[chart_indices].tolist()

        logger.info(
            "monte_carlo_complete",
            num_simulations=self.num_simulations,
            time_horizon_days=time_horizon_days,
            probability_of_loss=round(probability_of_loss, 4),
            value_at_risk_95=round(value_at_risk_95, 2),
        )

        return MonteCarloResult(
            num_simulations=self.num_simulations,
            time_horizon_days=time_horizon_days,
            percentiles=percentiles,
            probability_of_loss=probability_of_loss,
            value_at_risk_95=value_at_risk_95,
            simulation_paths=simulation_paths,
        )
