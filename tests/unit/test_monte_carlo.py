"""Tests for MonteCarloSimulator."""
from __future__ import annotations

import pytest

from src.core.models import MonteCarloResult
from src.strategy.monte_carlo import MonteCarloSimulator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flat_returns(n: int = 500, value: float = 0.001) -> list[float]:
    """All returns equal to `value`."""
    return [value] * n


def _random_returns(n: int = 500, seed: int = 42) -> list[float]:
    import random
    rng = random.Random(seed)
    return [rng.gauss(0.0005, 0.01) for _ in range(n)]


# ---------------------------------------------------------------------------
# Basic construction and return type
# ---------------------------------------------------------------------------

class TestMonteCarloBasics:
    def test_returns_monte_carlo_result(self):
        sim = MonteCarloSimulator(num_simulations=100)
        result = sim.simulate(_flat_returns(), time_horizon_days=10)
        assert isinstance(result, MonteCarloResult)

    def test_default_num_simulations(self):
        sim = MonteCarloSimulator()
        assert sim.num_simulations == 10000

    def test_custom_num_simulations(self):
        sim = MonteCarloSimulator(num_simulations=500)
        result = sim.simulate(_flat_returns(), time_horizon_days=10)
        assert result.num_simulations == 500

    def test_time_horizon_stored(self):
        sim = MonteCarloSimulator(num_simulations=100)
        result = sim.simulate(_flat_returns(), time_horizon_days=30)
        assert result.time_horizon_days == 30


# ---------------------------------------------------------------------------
# Percentile bands
# ---------------------------------------------------------------------------

class TestPercentileBands:
    def test_percentile_keys_present(self):
        sim = MonteCarloSimulator(num_simulations=200)
        result = sim.simulate(_flat_returns(), time_horizon_days=20)
        for key in ["p5", "p25", "p50", "p75", "p95"]:
            assert key in result.percentiles

    def test_percentile_length_matches_horizon(self):
        horizon = 30
        sim = MonteCarloSimulator(num_simulations=200)
        result = sim.simulate(_flat_returns(), time_horizon_days=horizon)
        for key in ["p5", "p25", "p50", "p75", "p95"]:
            assert len(result.percentiles[key]) == horizon

    def test_percentile_ordering(self):
        """p5 <= p25 <= p50 <= p75 <= p95 at every time step."""
        sim = MonteCarloSimulator(num_simulations=500)
        result = sim.simulate(_random_returns(), time_horizon_days=50)
        p = result.percentiles
        for i in range(50):
            assert p["p5"][i] <= p["p25"][i] <= p["p50"][i] <= p["p75"][i] <= p["p95"][i]

    def test_positive_returns_p50_above_initial(self):
        """With consistently positive returns, median final value exceeds initial."""
        sim = MonteCarloSimulator(num_simulations=1000)
        result = sim.simulate(_flat_returns(n=500, value=0.001), time_horizon_days=252, initial_value=10000.0)
        assert result.percentiles["p50"][-1] > 10000.0

    def test_negative_returns_p50_below_initial(self):
        """With consistently negative returns, median final value is below initial."""
        sim = MonteCarloSimulator(num_simulations=1000)
        result = sim.simulate(_flat_returns(n=500, value=-0.001), time_horizon_days=252, initial_value=10000.0)
        assert result.percentiles["p50"][-1] < 10000.0


# ---------------------------------------------------------------------------
# Probability of loss
# ---------------------------------------------------------------------------

class TestProbabilityOfLoss:
    def test_probability_in_range(self):
        sim = MonteCarloSimulator(num_simulations=500)
        result = sim.simulate(_random_returns(), time_horizon_days=50)
        assert 0.0 <= result.probability_of_loss <= 1.0

    def test_zero_loss_probability_with_strong_positive_returns(self):
        """Very high positive daily returns -> nearly 0 probability of loss."""
        sim = MonteCarloSimulator(num_simulations=1000, )
        result = sim.simulate(_flat_returns(n=500, value=0.05), time_horizon_days=5, seed=0)
        assert result.probability_of_loss == pytest.approx(0.0, abs=0.01)

    def test_high_loss_probability_with_negative_returns(self):
        """Uniformly negative returns -> high probability of loss."""
        sim = MonteCarloSimulator(num_simulations=1000)
        result = sim.simulate(_flat_returns(n=500, value=-0.005), time_horizon_days=252, seed=0)
        assert result.probability_of_loss > 0.9


# ---------------------------------------------------------------------------
# Value at Risk
# ---------------------------------------------------------------------------

class TestValueAtRisk:
    def test_var_non_negative(self):
        sim = MonteCarloSimulator(num_simulations=500)
        result = sim.simulate(_random_returns(), time_horizon_days=50)
        assert result.value_at_risk_95 >= 0.0

    def test_var_zero_with_guaranteed_positive_returns(self):
        """When all paths gain value, VaR should be 0 (no loss at 95% confidence)."""
        sim = MonteCarloSimulator(num_simulations=1000)
        result = sim.simulate(_flat_returns(n=500, value=0.05), time_horizon_days=10, initial_value=10000.0, seed=1)
        assert result.value_at_risk_95 == pytest.approx(0.0, abs=1.0)

    def test_var_positive_with_volatile_returns(self):
        """High-volatility returns should produce a positive VaR."""
        import random
        rng = random.Random(99)
        volatile = [rng.gauss(0.0, 0.05) for _ in range(500)]
        sim = MonteCarloSimulator(num_simulations=2000)
        result = sim.simulate(volatile, time_horizon_days=252, initial_value=10000.0, seed=2)
        assert result.value_at_risk_95 > 0.0


# ---------------------------------------------------------------------------
# Simulation paths
# ---------------------------------------------------------------------------

class TestSimulationPaths:
    def test_paths_count_limited(self):
        sim = MonteCarloSimulator(num_simulations=500)
        result = sim.simulate(_random_returns(), time_horizon_days=50, num_paths_for_chart=20)
        assert len(result.simulation_paths) == 20

    def test_paths_capped_at_num_simulations(self):
        sim = MonteCarloSimulator(num_simulations=10)
        result = sim.simulate(_random_returns(), time_horizon_days=10, num_paths_for_chart=100)
        assert len(result.simulation_paths) <= 10

    def test_path_length_matches_horizon(self):
        horizon = 30
        sim = MonteCarloSimulator(num_simulations=200)
        result = sim.simulate(_random_returns(), time_horizon_days=horizon, num_paths_for_chart=10)
        for path in result.simulation_paths:
            assert len(path) == horizon


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_returns_returns_result(self):
        sim = MonteCarloSimulator(num_simulations=100)
        result = sim.simulate([], time_horizon_days=10)
        assert isinstance(result, MonteCarloResult)
        assert result.probability_of_loss == 0.0
        assert result.value_at_risk_95 == 0.0

    def test_single_return_value(self):
        sim = MonteCarloSimulator(num_simulations=100)
        result = sim.simulate([0.01], time_horizon_days=5)
        assert isinstance(result, MonteCarloResult)

    def test_reproducible_with_seed(self):
        sim = MonteCarloSimulator(num_simulations=500)
        returns = _random_returns()
        r1 = sim.simulate(returns, time_horizon_days=50, seed=42)
        r2 = sim.simulate(returns, time_horizon_days=50, seed=42)
        assert r1.probability_of_loss == pytest.approx(r2.probability_of_loss)
        assert r1.value_at_risk_95 == pytest.approx(r2.value_at_risk_95)

    def test_different_seeds_give_different_results(self):
        sim = MonteCarloSimulator(num_simulations=200)
        returns = _random_returns()
        r1 = sim.simulate(returns, time_horizon_days=50, seed=1)
        r2 = sim.simulate(returns, time_horizon_days=50, seed=999)
        # Not guaranteed to differ, but with 200 sims on random returns this is virtually certain
        assert r1.probability_of_loss != r2.probability_of_loss or r1.value_at_risk_95 != r2.value_at_risk_95
