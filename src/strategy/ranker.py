from __future__ import annotations

from datetime import datetime

import numpy as np
import structlog

from src.core.config import RankingWeights, StrategySettings, get_settings
from src.core.models import BacktestResult, StrategyRanking

logger = structlog.get_logger(__name__)


class StrategyRanker:
    """Ranks strategies by composite score with configurable weights and thresholds."""

    def __init__(self, settings: StrategySettings | None = None) -> None:
        self._settings = settings or get_settings().strategy
        self._weights: RankingWeights = self._settings.ranking_weights

    def rank_strategies(
        self,
        results: list[BacktestResult],
        walk_forward_results: dict[str, list[BacktestResult]] | None = None,
    ) -> list[StrategyRanking]:
        if not results:
            return []

        rankings: list[StrategyRanking] = []
        for result in results:
            consistency = 0.0
            if walk_forward_results and result.strategy_name in walk_forward_results:
                consistency = self._compute_consistency(walk_forward_results[result.strategy_name])

            ranking = self._score_result(result, consistency)
            rankings.append(ranking)

        rankings.sort(key=lambda r: r.composite_score, reverse=True)
        return rankings

    def _score_result(self, result: BacktestResult, consistency: float) -> StrategyRanking:
        # Normalize components to roughly [0, 1] range
        sharpe_norm = max(0.0, min(result.sharpe_ratio / 3.0, 1.0))
        sortino_norm = max(0.0, min(result.sortino_ratio / 4.0, 1.0))
        # Invert drawdown: lower DD = higher score
        dd_norm = max(0.0, 1.0 - result.max_drawdown_pct / 50.0)
        pf_norm = max(0.0, min((result.profit_factor - 1.0) / 2.0, 1.0))
        consistency_norm = max(0.0, min(consistency, 1.0))

        composite = (
            self._weights.sharpe * sharpe_norm
            + self._weights.sortino * sortino_norm
            + self._weights.max_drawdown_inverse * dd_norm
            + self._weights.profit_factor * pf_norm
            + self._weights.consistency * consistency_norm
        )

        meets = self._check_thresholds(result)

        return StrategyRanking(
            strategy_name=result.strategy_name,
            composite_score=round(composite, 4),
            sharpe_ratio=result.sharpe_ratio,
            sortino_ratio=result.sortino_ratio,
            max_drawdown_pct=result.max_drawdown_pct,
            profit_factor=result.profit_factor,
            consistency_score=round(consistency_norm, 4),
            total_trades=result.total_trades,
            win_rate=result.win_rate,
            meets_thresholds=meets,
            ranked_at=datetime.utcnow(),
        )

    def _check_thresholds(self, result: BacktestResult) -> bool:
        return (
            result.sharpe_ratio > self._settings.min_sharpe_ratio
            and result.max_drawdown_pct < self._settings.max_drawdown_pct
            and result.profit_factor > self._settings.min_profit_factor
            and result.total_trades >= self._settings.min_trades
        )

    def _compute_consistency(self, wf_results: list[BacktestResult]) -> float:
        """Consistency score from walk-forward windows. Lower std dev of returns = better."""
        if len(wf_results) < 2:
            return 0.5

        returns = [r.total_return_pct for r in wf_results]
        std = float(np.std(returns))

        # Convert std to a 0-1 score: 0% std -> 1.0, 50%+ std -> 0.0
        score = max(0.0, 1.0 - std / 50.0)
        return score
