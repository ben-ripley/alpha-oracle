"""Unit tests for StrategyEngine."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, BacktestResult, Signal, SignalDirection
from src.strategy.engine import StrategyEngine


class MockStrategy(BaseStrategy):
    """Mock strategy for testing."""

    def __init__(self, strategy_name: str, min_hold_days: int = 2):
        self._name = strategy_name
        self._min_hold_days = min_hold_days
        self._params = {"test_param": 42}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Mock strategy for testing"

    @property
    def min_hold_days(self) -> int:
        return self._min_hold_days

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        return [
            Signal(
                symbol=list(data.keys())[0] if data else "AAPL",
                timestamp=datetime.utcnow(),
                direction=SignalDirection.LONG,
                strength=0.8,
                strategy_name=self.name,
            )
        ]

    def get_parameters(self) -> dict:
        return self._params

    def get_required_data(self) -> list[str]:
        return ["ohlcv"]


class TestRegistration:
    """Tests for strategy registration."""

    def test_register_strategy_with_valid_min_hold_days(self):
        """Strategy with min_hold_days >= 2 succeeds."""
        engine = StrategyEngine()
        strategy = MockStrategy("TestStrat", min_hold_days=2)

        engine.register_strategy(strategy)

        assert "TestStrat" in engine.list_strategies()
        assert engine.get_strategy("TestStrat") == strategy

    def test_register_strategy_with_invalid_min_hold_days_raises(self):
        """Strategy with min_hold_days < 2 raises ValueError (PDT gate)."""
        engine = StrategyEngine()
        strategy = MockStrategy("BadStrat", min_hold_days=1)

        with pytest.raises(ValueError) as exc_info:
            engine.register_strategy(strategy)

        assert "min_hold_days=1" in str(exc_info.value)
        assert "PDT rule" in str(exc_info.value)

    def test_get_unregistered_strategy_raises(self):
        """get_strategy for unregistered name raises KeyError."""
        engine = StrategyEngine()

        with pytest.raises(KeyError) as exc_info:
            engine.get_strategy("NonExistent")

        assert "NonExistent" in str(exc_info.value)
        assert "not registered" in str(exc_info.value)

    def test_list_strategies_returns_registered_names(self):
        """list_strategies returns registered names."""
        engine = StrategyEngine()
        strat1 = MockStrategy("Strategy1", min_hold_days=2)
        strat2 = MockStrategy("Strategy2", min_hold_days=3)

        engine.register_strategy(strat1)
        engine.register_strategy(strat2)

        names = engine.list_strategies()
        assert len(names) == 2
        assert "Strategy1" in names
        assert "Strategy2" in names


class TestBacktest:
    """Tests for backtesting."""

    def test_backtest_delegates_to_engine(self, make_backtest_result, make_ohlcv_bars):
        """Delegates to backtest engine, returns result."""
        engine = StrategyEngine()
        strategy = MockStrategy("TestStrat", min_hold_days=2)
        engine.register_strategy(strategy)

        data = {"AAPL": make_ohlcv_bars("AAPL", days=50)}
        expected_result = make_backtest_result(strategy_name="TestStrat")

        # Mock the backtest engine
        engine._backtest_engine = MagicMock()
        engine._backtest_engine.run = MagicMock(return_value=expected_result)

        result = engine.run_backtest(
            "TestStrat",
            data,
            initial_capital=100_000.0,
            start=datetime(2024, 1, 1),
            end=datetime(2024, 3, 1),
        )

        assert result == expected_result
        engine._backtest_engine.run.assert_called_once()
        assert result.strategy_name == "TestStrat"

    def test_backtest_with_empty_data_raises(self):
        """No data (empty dict values) raises ValueError."""
        engine = StrategyEngine()
        strategy = MockStrategy("TestStrat", min_hold_days=2)
        engine.register_strategy(strategy)

        empty_data = {"AAPL": []}

        with pytest.raises(ValueError) as exc_info:
            engine.run_backtest("TestStrat", empty_data)

        assert "No data provided" in str(exc_info.value)

    def test_backtest_infers_dates_from_data(self, make_ohlcv_bars):
        """Infers start/end dates from data when not provided."""
        engine = StrategyEngine()
        strategy = MockStrategy("TestStrat", min_hold_days=2)
        engine.register_strategy(strategy)

        bars = make_ohlcv_bars("AAPL", days=50)
        data = {"AAPL": bars}

        expected_result = BacktestResult(
            strategy_name="TestStrat",
            start_date=bars[0].timestamp,
            end_date=bars[-1].timestamp,
            initial_capital=100_000.0,
            final_capital=110_000.0,
            total_return_pct=10.0,
            annual_return_pct=10.0,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown_pct=5.0,
            profit_factor=2.0,
            total_trades=100,
            winning_trades=55,
            losing_trades=45,
            win_rate=0.55,
            avg_win_pct=3.0,
            avg_loss_pct=1.5,
        )

        engine._backtest_engine = MagicMock()
        engine._backtest_engine.run = MagicMock(return_value=expected_result)

        engine.run_backtest("TestStrat", data)

        # Verify run was called with inferred dates
        call_args = engine._backtest_engine.run.call_args
        assert call_args[0][3] == bars[0].timestamp  # start
        assert call_args[0][4] == bars[-1].timestamp  # end


class TestRankAll:
    """Tests for ranking strategies."""

    def test_empty_results_returns_empty_list(self):
        """Empty results returns empty list."""
        engine = StrategyEngine()

        rankings = engine.rank_all()

        assert rankings == []

    def test_rank_all_delegates_to_ranker(self, make_backtest_result):
        """With results delegates to ranker."""
        engine = StrategyEngine()

        # Add mock results
        result1 = make_backtest_result(strategy_name="Strat1", sharpe_ratio=2.0)
        result2 = make_backtest_result(strategy_name="Strat2", sharpe_ratio=1.5)
        engine._results = {"Strat1": result1, "Strat2": result2}

        # Mock ranker
        mock_rankings = [
            MagicMock(strategy_name="Strat1", composite_score=0.85, meets_thresholds=True),
            MagicMock(strategy_name="Strat2", composite_score=0.72, meets_thresholds=True),
        ]
        engine._ranker = MagicMock()
        engine._ranker.rank_strategies = MagicMock(return_value=mock_rankings)

        rankings = engine.rank_all()

        assert len(rankings) == 2
        engine._ranker.rank_strategies.assert_called_once()


class TestLiveSignals:
    """Tests for live signal generation."""

    def test_live_signals_aggregates_from_all_strategies(self, make_ohlcv_bars):
        """Calls generate_signals on all registered strategies, aggregates results."""
        engine = StrategyEngine()

        strat1 = MockStrategy("Strat1", min_hold_days=2)
        strat2 = MockStrategy("Strat2", min_hold_days=2)

        engine.register_strategy(strat1)
        engine.register_strategy(strat2)

        data = {
            "AAPL": make_ohlcv_bars("AAPL", days=10),
            "MSFT": make_ohlcv_bars("MSFT", days=10),
        }

        signals = engine.get_live_signals(data)

        # Each strategy should generate 1 signal (from MockStrategy implementation)
        assert len(signals) == 2
        assert signals[0].strategy_name in ["Strat1", "Strat2"]
        assert signals[1].strategy_name in ["Strat1", "Strat2"]
