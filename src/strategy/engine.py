from __future__ import annotations

from datetime import datetime

import structlog

from src.core.config import StrategySettings, get_settings
from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, BacktestResult, Signal, StrategyRanking
from src.strategy.backtest.backtrader_engine import BacktraderEngine
from src.strategy.ranker import StrategyRanker

logger = structlog.get_logger(__name__)


class StrategyEngine:
    """Orchestrates strategy registration, backtesting, walk-forward analysis, and ranking."""

    def __init__(self, settings: StrategySettings | None = None) -> None:
        self._settings = settings or get_settings().strategy
        self._strategies: dict[str, BaseStrategy] = {}
        self._backtest_engine = BacktraderEngine()
        self._ranker = StrategyRanker(self._settings)
        self._results: dict[str, BacktestResult] = {}
        self._wf_results: dict[str, list[BacktestResult]] = {}

    def register_strategy(self, strategy: BaseStrategy) -> None:
        if strategy.min_hold_days < 2:
            raise ValueError(
                f"Strategy '{strategy.name}' has min_hold_days={strategy.min_hold_days}. "
                "Minimum is 2 days (PDT rule)."
            )
        self._strategies[strategy.name] = strategy
        logger.info("strategy_registered", name=strategy.name, params=strategy.get_parameters())

    def get_strategy(self, name: str) -> BaseStrategy:
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not registered")
        return self._strategies[name]

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def run_backtest(
        self,
        strategy_name: str,
        data: dict[str, list[OHLCV]],
        initial_capital: float = 100_000.0,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> BacktestResult:
        strategy = self.get_strategy(strategy_name)

        if start is None or end is None:
            all_dates = [b.timestamp for bars in data.values() for b in bars]
            if not all_dates:
                raise ValueError("No data provided")
            start = start or min(all_dates)
            end = end or max(all_dates)

        logger.info(
            "running_backtest",
            strategy=strategy_name,
            start=start.isoformat(),
            end=end.isoformat(),
            capital=initial_capital,
        )

        result = self._backtest_engine.run(strategy, data, initial_capital, start, end)
        self._results[strategy_name] = result

        logger.info(
            "backtest_complete",
            strategy=strategy_name,
            total_return=f"{result.total_return_pct:.2f}%",
            sharpe=result.sharpe_ratio,
            trades=result.total_trades,
        )

        return result

    def run_walk_forward(
        self,
        strategy_name: str,
        data: dict[str, list[OHLCV]],
        initial_capital: float = 100_000.0,
        train_months: int | None = None,
        test_months: int | None = None,
        step_months: int | None = None,
    ) -> list[BacktestResult]:
        strategy = self.get_strategy(strategy_name)
        wf = self._settings.walk_forward

        train = train_months or wf.train_months
        test = test_months or wf.test_months
        step = step_months or wf.step_months

        logger.info(
            "running_walk_forward",
            strategy=strategy_name,
            train_months=train,
            test_months=test,
            step_months=step,
        )

        results = self._backtest_engine.walk_forward(
            strategy, data, initial_capital, train, test, step
        )
        self._wf_results[strategy_name] = results

        logger.info(
            "walk_forward_complete",
            strategy=strategy_name,
            windows=len(results),
        )

        return results

    def rank_all(self) -> list[StrategyRanking]:
        if not self._results:
            logger.warning("no_backtest_results_to_rank")
            return []

        results = list(self._results.values())
        rankings = self._ranker.rank_strategies(results, self._wf_results)

        for rank in rankings:
            logger.info(
                "strategy_ranked",
                name=rank.strategy_name,
                score=rank.composite_score,
                meets_thresholds=rank.meets_thresholds,
            )

        return rankings

    def get_live_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        all_signals: list[Signal] = []

        for name, strategy in self._strategies.items():
            try:
                signals = strategy.generate_signals(data)
                all_signals.extend(signals)
                logger.info("live_signals_generated", strategy=name, count=len(signals))
            except Exception:
                logger.exception("signal_generation_error", strategy=name)

        return all_signals
