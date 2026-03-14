"""Mean-variance portfolio optimizer for multi-strategy allocation."""
from __future__ import annotations

import numpy as np
import structlog
from scipy.optimize import minimize

from src.core.models import MarketRegime, OptimizationResult, StrategyAllocation

logger = structlog.get_logger(__name__)

_MAX_SINGLE_WEIGHT = 0.40
_MIN_SINGLE_WEIGHT = 0.0
_ANNUALIZATION_FACTOR = 252


class MultiStrategyOptimizer:
    """Mean-variance optimization to maximize Sharpe ratio across strategies.

    Constraints:
    - Weights sum to 1.0
    - Each weight in [0, 0.40] (long-only, max 40% per strategy)
    """

    def optimize(
        self,
        strategy_returns: dict[str, list[float]],
        regime: MarketRegime | None = None,
    ) -> OptimizationResult:
        """Maximize Sharpe ratio subject to weight constraints.

        Args:
            strategy_returns: Map of strategy name -> list of daily returns.
            regime: Optional current market regime (reserved for future regime-aware weighting).

        Returns:
            OptimizationResult with optimal allocations and portfolio statistics.
        """
        strategy_names = list(strategy_returns.keys())
        n = len(strategy_names)

        if n == 0:
            logger.warning("optimizer_no_strategies")
            return OptimizationResult(
                allocations=[],
                portfolio_sharpe=0.0,
                portfolio_expected_return=0.0,
                portfolio_volatility=0.0,
            )

        # Build returns matrix; pad shorter series with NaN then drop NaN rows
        min_len = min(len(v) for v in strategy_returns.values())
        if min_len == 0:
            logger.warning("optimizer_empty_returns")
            return self._equal_weight_result(strategy_names, strategy_returns)

        returns_matrix = np.array(
            [strategy_returns[name][-min_len:] for name in strategy_names],
            dtype=float,
        ).T  # shape: (T, n)

        # Per-strategy annualized stats
        mu = np.mean(returns_matrix, axis=0) * _ANNUALIZATION_FACTOR  # annualized mean
        cov_raw = np.cov(returns_matrix, rowvar=False) * _ANNUALIZATION_FACTOR  # annualized cov
        # np.cov on a single column returns a scalar; ensure shape is always (n, n)
        cov = np.atleast_2d(cov_raw)

        # --- Optimization ---
        # Objective: minimize negative Sharpe (maximize Sharpe)
        def neg_sharpe(weights: np.ndarray) -> float:
            port_return = float(np.dot(weights, mu))
            port_var = float(np.dot(weights, np.dot(cov, weights)))
            port_vol = float(np.sqrt(max(port_var, 1e-12)))
            return -(port_return / port_vol) if port_vol > 0 else 0.0

        # Initial guess: equal weights
        w0 = np.ones(n) / n

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        bounds = [(_MIN_SINGLE_WEIGHT, _MAX_SINGLE_WEIGHT)] * n

        result = minimize(
            neg_sharpe,
            w0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"ftol": 1e-9, "maxiter": 1000},
        )

        if result.success:
            weights = result.x
        else:
            logger.warning("optimizer_did_not_converge", message=result.message)
            # Fall back to equal weights
            weights = w0

        # Clip and renormalise to handle floating point drift
        weights = np.clip(weights, _MIN_SINGLE_WEIGHT, _MAX_SINGLE_WEIGHT)
        weights_sum = weights.sum()
        if weights_sum > 0:
            weights = weights / weights_sum
        else:
            weights = w0

        # Compute portfolio-level statistics
        port_return = float(np.dot(weights, mu))
        port_var = float(np.dot(weights, np.dot(cov, weights)))
        port_vol = float(np.sqrt(max(port_var, 0.0)))
        port_sharpe = (port_return / port_vol) if port_vol > 0 else 0.0

        # Contribution to risk: weight * marginal contribution (w_i * (Cov * w)_i / port_vol)
        if port_vol > 0:
            marginal = np.dot(cov, weights)
            risk_contribution = weights * marginal / port_vol
        else:
            risk_contribution = weights.copy()

        # Round weights to 6 dp, then distribute any residual onto the largest
        # weight so the allocation weights always sum to exactly 1.0.
        rounded_weights = [round(float(weights[i]), 6) for i in range(n)]
        residual = round(1.0 - sum(rounded_weights), 6)
        if residual != 0.0:
            largest_idx = int(np.argmax(rounded_weights))
            rounded_weights[largest_idx] = round(rounded_weights[largest_idx] + residual, 6)

        allocations = [
            StrategyAllocation(
                strategy_name=name,
                weight=rounded_weights[i],
                expected_return=float(round(mu[i], 6)),
                contribution_to_risk=float(round(risk_contribution[i], 6)),
            )
            for i, name in enumerate(strategy_names)
        ]

        logger.info(
            "optimizer_complete",
            strategies=strategy_names,
            portfolio_sharpe=round(port_sharpe, 4),
            portfolio_return=round(port_return, 4),
            portfolio_vol=round(port_vol, 4),
        )

        return OptimizationResult(
            allocations=allocations,
            portfolio_sharpe=round(port_sharpe, 6),
            portfolio_expected_return=round(port_return, 6),
            portfolio_volatility=round(port_vol, 6),
        )

    def _equal_weight_result(
        self,
        strategy_names: list[str],
        strategy_returns: dict[str, list[float]],
    ) -> OptimizationResult:
        """Return equal-weight allocation when optimization isn't possible."""
        n = len(strategy_names)
        w = 1.0 / n
        allocations = [
            StrategyAllocation(
                strategy_name=name,
                weight=w,
                expected_return=0.0,
                contribution_to_risk=w,
            )
            for name in strategy_names
        ]
        return OptimizationResult(
            allocations=allocations,
            portfolio_sharpe=0.0,
            portfolio_expected_return=0.0,
            portfolio_volatility=0.0,
        )
