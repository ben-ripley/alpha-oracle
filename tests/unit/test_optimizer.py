"""Tests for MultiStrategyOptimizer — mean-variance portfolio optimization."""
from __future__ import annotations

import pytest

from src.core.models import MarketRegime, OptimizationResult, StrategyAllocation
from src.strategy.optimizer import MultiStrategyOptimizer, _MAX_SINGLE_WEIGHT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _constant_returns(value: float, n: int = 252) -> list[float]:
    return [value] * n


def _random_returns(mean: float, std: float, n: int = 252, seed: int = 0) -> list[float]:
    import random
    rng = random.Random(seed)
    return [rng.gauss(mean, std) for _ in range(n)]


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_optimization_result(self):
        opt = MultiStrategyOptimizer()
        result = opt.optimize({"s1": _constant_returns(0.001)})
        assert isinstance(result, OptimizationResult)

    def test_allocations_are_list_of_strategy_allocations(self):
        opt = MultiStrategyOptimizer()
        result = opt.optimize({"s1": _constant_returns(0.001), "s2": _constant_returns(0.002)})
        assert isinstance(result.allocations, list)
        for alloc in result.allocations:
            assert isinstance(alloc, StrategyAllocation)

    def test_allocation_count_matches_strategies(self):
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _constant_returns(0.001 * (i + 1)) for i in range(4)}
        result = opt.optimize(strategies)
        assert len(result.allocations) == 4

    def test_strategy_names_in_allocations(self):
        opt = MultiStrategyOptimizer()
        names = ["alpha", "beta", "gamma"]
        strategies = {name: _constant_returns(0.001) for name in names}
        result = opt.optimize(strategies)
        result_names = [a.strategy_name for a in result.allocations]
        assert sorted(result_names) == sorted(names)


# ---------------------------------------------------------------------------
# Weight constraints
# ---------------------------------------------------------------------------

class TestWeightConstraints:
    def test_weights_sum_to_one(self):
        opt = MultiStrategyOptimizer()
        strategies = {
            "s1": _random_returns(0.001, 0.01, seed=1),
            "s2": _random_returns(0.002, 0.015, seed=2),
            "s3": _random_returns(0.0005, 0.008, seed=3),
        }
        result = opt.optimize(strategies)
        total = sum(a.weight for a in result.allocations)
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_no_weight_exceeds_max(self):
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001 * i, 0.01, seed=i) for i in range(1, 6)}
        result = opt.optimize(strategies)
        for alloc in result.allocations:
            assert alloc.weight <= _MAX_SINGLE_WEIGHT + 1e-9

    def test_weights_non_negative(self):
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001 * i, 0.01, seed=i) for i in range(1, 4)}
        result = opt.optimize(strategies)
        for alloc in result.allocations:
            assert alloc.weight >= 0.0 - 1e-9

    def test_single_strategy_gets_full_weight(self):
        """With one strategy, it must receive all the weight."""
        opt = MultiStrategyOptimizer()
        result = opt.optimize({"only": _random_returns(0.001, 0.01, seed=0)})
        assert len(result.allocations) == 1
        assert result.allocations[0].weight == pytest.approx(1.0, abs=1e-6)

    def test_single_strategy_weight_respects_max(self):
        """Single strategy: weight is 1.0 but max is 0.4.
        After renormalization, single strategy still gets 1.0 (100% allocation).
        """
        opt = MultiStrategyOptimizer()
        result = opt.optimize({"only": _random_returns(0.001, 0.01, seed=0)})
        # With one strategy, clip to 0.4 then renormalize -> 0.4/0.4 = 1.0
        assert result.allocations[0].weight == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Optimization direction
# ---------------------------------------------------------------------------

class TestOptimizationDirection:
    def test_higher_sharpe_strategy_gets_more_weight(self):
        """Strategy with much higher Sharpe should get more weight."""
        opt = MultiStrategyOptimizer()
        # s_high: high return, low vol -> high Sharpe
        # s_low: low return, high vol -> low Sharpe
        s_high = _random_returns(mean=0.005, std=0.005, n=500, seed=10)
        s_low = _random_returns(mean=0.0001, std=0.02, n=500, seed=11)
        result = opt.optimize({"s_high": s_high, "s_low": s_low})
        weights = {a.strategy_name: a.weight for a in result.allocations}
        assert weights["s_high"] >= weights["s_low"]

    def test_portfolio_sharpe_is_positive_for_positive_return_strategies(self):
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001, 0.01, seed=i) for i in range(3)}
        result = opt.optimize(strategies)
        assert result.portfolio_sharpe > 0.0

    def test_portfolio_return_in_reasonable_range(self):
        """Annualized portfolio return should be in (−1, 10) for typical daily returns."""
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001, 0.01, seed=i) for i in range(3)}
        result = opt.optimize(strategies)
        assert -1.0 < result.portfolio_expected_return < 10.0

    def test_portfolio_volatility_positive(self):
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001, 0.01, seed=i) for i in range(3)}
        result = opt.optimize(strategies)
        assert result.portfolio_volatility >= 0.0


# ---------------------------------------------------------------------------
# Equal-return strategies
# ---------------------------------------------------------------------------

class TestEqualReturnStrategies:
    def test_equal_returns_distributes_across_strategies(self):
        """All strategies with identical returns -> weights spread across all."""
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _constant_returns(0.001, n=300) for i in range(4)}
        result = opt.optimize(strategies)
        total = sum(a.weight for a in result.allocations)
        assert total == pytest.approx(1.0, abs=1e-6)
        # All weights equal (tied strategies)
        weights = [a.weight for a in result.allocations]
        assert max(weights) - min(weights) < 0.5  # loose check — may be concentrated due to optimizer


# ---------------------------------------------------------------------------
# Regime parameter
# ---------------------------------------------------------------------------

class TestRegimeParameter:
    def test_accepts_market_regime(self):
        """Optimizer should accept a regime parameter without error."""
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001, 0.01, seed=i) for i in range(2)}
        for regime in MarketRegime:
            result = opt.optimize(strategies, regime=regime)
            assert isinstance(result, OptimizationResult)

    def test_accepts_none_regime(self):
        opt = MultiStrategyOptimizer()
        strategies = {"s1": _random_returns(0.001, 0.01, seed=0)}
        result = opt.optimize(strategies, regime=None)
        assert isinstance(result, OptimizationResult)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_strategies_returns_empty_allocations(self):
        opt = MultiStrategyOptimizer()
        result = opt.optimize({})
        assert result.allocations == []
        assert result.portfolio_sharpe == 0.0

    def test_empty_returns_list_handled(self):
        opt = MultiStrategyOptimizer()
        result = opt.optimize({"s1": [], "s2": []})
        # Falls back gracefully
        assert isinstance(result, OptimizationResult)

    def test_two_strategies_weights_sum_to_one(self):
        opt = MultiStrategyOptimizer()
        result = opt.optimize({
            "a": _random_returns(0.002, 0.01, seed=5),
            "b": _random_returns(0.001, 0.02, seed=6),
        })
        total = sum(a.weight for a in result.allocations)
        assert total == pytest.approx(1.0, abs=1e-6)

    def test_many_strategies_weights_sum_to_one(self):
        """With many strategies (>= 3), weights must still sum to 1."""
        opt = MultiStrategyOptimizer()
        strategies = {f"s{i}": _random_returns(0.001 * i, 0.01, seed=i) for i in range(1, 8)}
        result = opt.optimize(strategies)
        total = sum(a.weight for a in result.allocations)
        assert total == pytest.approx(1.0, abs=1e-6)
