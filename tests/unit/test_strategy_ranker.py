"""Unit tests for StrategyRanker."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import RankingWeights, StrategySettings, WalkForwardSettings
from src.strategy.ranker import StrategyRanker


class TestScoring:
    """Tests for scoring logic."""

    @patch("src.strategy.ranker.get_settings")
    def test_perfect_result_scores_near_one(self, mock_get_settings, make_backtest_result):
        """Perfect result (high Sharpe, Sortino, low DD, high PF) scores near 1.0."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        # Perfect-ish result
        result = make_backtest_result(
            strategy_name="PerfectStrat",
            sharpe_ratio=3.0,  # Max normalized value
            sortino_ratio=4.0,  # Max normalized value
            max_drawdown_pct=1.0,  # Very low
            profit_factor=3.0,  # High
            total_trades=200,
        )

        rankings = ranker.rank_strategies([result])

        assert len(rankings) == 1
        assert rankings[0].composite_score >= 0.84  # Should be very high
        assert rankings[0].strategy_name == "PerfectStrat"

    @patch("src.strategy.ranker.get_settings")
    def test_terrible_result_scores_near_zero(self, mock_get_settings, make_backtest_result):
        """Terrible result (negative Sharpe, high DD) scores near 0.0."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        result = make_backtest_result(
            strategy_name="TerribleStrat",
            sharpe_ratio=-1.0,  # Negative
            sortino_ratio=-0.5,
            max_drawdown_pct=50.0,  # Very high
            profit_factor=0.5,  # Low
            total_trades=50,
        )

        rankings = ranker.rank_strategies([result])

        assert len(rankings) == 1
        assert rankings[0].composite_score < 0.2  # Should be very low

    @patch("src.strategy.ranker.get_settings")
    def test_weights_sum_correctly(self, mock_get_settings):
        """Weights sum correctly (the default weights should sum to ~1.0)."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        weights = ranker._weights
        total = (
            weights.sharpe
            + weights.sortino
            + weights.max_drawdown_inverse
            + weights.profit_factor
            + weights.consistency
        )

        assert abs(total - 1.0) < 0.01  # Should sum to ~1.0

    @patch("src.strategy.ranker.get_settings")
    def test_normalization_clamps_values(self, mock_get_settings, make_backtest_result):
        """Normalization clamps values to [0, 1] range."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        # Extreme values
        result = make_backtest_result(
            strategy_name="ExtremeStrat",
            sharpe_ratio=10.0,  # Way above normal
            sortino_ratio=15.0,
            max_drawdown_pct=-10.0,  # Impossible but tests clamping
            profit_factor=10.0,
            total_trades=500,
        )

        rankings = ranker.rank_strategies([result])

        # Score should be clamped to reasonable range
        assert 0.0 <= rankings[0].composite_score <= 1.0

    @patch("src.strategy.ranker.get_settings")
    def test_consistency_from_walk_forward_affects_score(
        self, mock_get_settings, make_backtest_result
    ):
        """Consistency from walk-forward affects score."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        result = make_backtest_result(
            strategy_name="TestStrat",
            sharpe_ratio=2.0,
            sortino_ratio=2.5,
            max_drawdown_pct=10.0,
            profit_factor=2.0,
        )

        # Without walk-forward
        rankings_no_wf = ranker.rank_strategies([result])

        # With consistent walk-forward results (low std)
        wf_results = [
            make_backtest_result(strategy_name="TestStrat", total_return_pct=20.0),
            make_backtest_result(strategy_name="TestStrat", total_return_pct=22.0),
            make_backtest_result(strategy_name="TestStrat", total_return_pct=21.0),
        ]
        rankings_with_wf = ranker.rank_strategies([result], {"TestStrat": wf_results})

        # Score with consistent WF should be higher due to consistency component
        assert rankings_with_wf[0].composite_score >= rankings_no_wf[0].composite_score
        assert rankings_with_wf[0].consistency_score > 0.0


class TestThresholds:
    """Tests for threshold checking."""

    @patch("src.strategy.ranker.get_settings")
    def test_all_thresholds_met_returns_true(self, mock_get_settings, make_backtest_result):
        """All thresholds met returns True."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        result = make_backtest_result(
            strategy_name="GoodStrat",
            sharpe_ratio=1.5,  # > 1.0
            profit_factor=2.0,  # > 1.5
            max_drawdown_pct=15.0,  # < 20.0
            total_trades=150,  # >= 100
        )

        rankings = ranker.rank_strategies([result])

        assert rankings[0].meets_thresholds is True

    @patch("src.strategy.ranker.get_settings")
    def test_low_sharpe_returns_false(self, mock_get_settings, make_backtest_result):
        """Low Sharpe (below min_sharpe_ratio) returns False."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        result = make_backtest_result(
            strategy_name="LowSharpe",
            sharpe_ratio=0.8,  # Below threshold
            profit_factor=2.0,
            max_drawdown_pct=15.0,
            total_trades=150,
        )

        rankings = ranker.rank_strategies([result])

        assert rankings[0].meets_thresholds is False

    @patch("src.strategy.ranker.get_settings")
    def test_few_trades_returns_false(self, mock_get_settings, make_backtest_result):
        """Few trades (below min_trades) returns False."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        result = make_backtest_result(
            strategy_name="FewTrades",
            sharpe_ratio=1.5,
            profit_factor=2.0,
            max_drawdown_pct=15.0,
            total_trades=50,  # Below threshold
        )

        rankings = ranker.rank_strategies([result])

        assert rankings[0].meets_thresholds is False


class TestRanking:
    """Tests for ranking and sorting."""

    @patch("src.strategy.ranker.get_settings")
    def test_results_sorted_descending_by_score(self, mock_get_settings, make_backtest_result):
        """Results sorted descending by composite_score."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        results = [
            make_backtest_result(strategy_name="Low", sharpe_ratio=1.0, sortino_ratio=1.5),
            make_backtest_result(strategy_name="High", sharpe_ratio=2.5, sortino_ratio=3.0),
            make_backtest_result(strategy_name="Medium", sharpe_ratio=1.8, sortino_ratio=2.2),
        ]

        rankings = ranker.rank_strategies(results)

        assert len(rankings) == 3
        # Should be sorted descending by score
        assert rankings[0].composite_score >= rankings[1].composite_score
        assert rankings[1].composite_score >= rankings[2].composite_score
        # Highest sharpe/sortino should be first
        assert rankings[0].strategy_name == "High"

    @patch("src.strategy.ranker.get_settings")
    def test_empty_input_returns_empty_list(self, mock_get_settings):
        """Empty input returns empty list."""
        mock_settings = MagicMock()
        mock_settings.strategy = StrategySettings(
            min_sharpe_ratio=1.0,
            min_profit_factor=1.5,
            max_drawdown_pct=20.0,
            min_trades=100,
            ranking_weights=RankingWeights(
                sharpe=0.30,
                sortino=0.20,
                max_drawdown_inverse=0.20,
                profit_factor=0.15,
                consistency=0.15,
            ),
            walk_forward=WalkForwardSettings(
                train_months=12,
                test_months=3,
                step_months=1,
            ),
        )
        mock_get_settings.return_value = mock_settings

        ranker = StrategyRanker()

        rankings = ranker.rank_strategies([])

        assert rankings == []
