from __future__ import annotations

from datetime import datetime
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
import structlog

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, BacktestResult

logger = structlog.get_logger(__name__)


class VectorBTEngine:
    """Vectorized backtesting engine for rapid parameter optimization.

    Uses vectorbt for fast grid-search over strategy parameter ranges.
    Much faster than Backtrader for parameter sweeps due to vectorized operations.
    """

    def __init__(self, commission_pct: float = 0.0, slippage_pct: float = 0.01) -> None:
        self._commission_pct = commission_pct
        self._slippage_pct = slippage_pct

    def optimize_parameters(
        self,
        strategy_class: type[BaseStrategy],
        param_ranges: dict[str, list[Any]],
        data: dict[str, list[OHLCV]],
        initial_capital: float = 100_000.0,
        start: datetime | None = None,
        end: datetime | None = None,
        metric: str = "sharpe_ratio",
    ) -> tuple[dict[str, Any], BacktestResult]:
        """Run grid search over parameter ranges and return the best combination.

        Args:
            strategy_class: Strategy class to instantiate with each parameter set.
            param_ranges: Dict mapping parameter names to lists of values to try.
            data: OHLCV data keyed by symbol.
            initial_capital: Starting capital for each backtest.
            start: Optional start date filter.
            end: Optional end date filter.
            metric: Metric to optimize (sharpe_ratio, sortino_ratio, total_return_pct, profit_factor).

        Returns:
            Tuple of (best_params, best_result).
        """
        import vectorbt as vbt

        filtered = self._filter_data(data, start, end)
        if not filtered:
            raise ValueError("No data available in the specified date range")

        # Build price DataFrame for vectorbt
        price_frames = {}
        for symbol, bars in filtered.items():
            df = pd.DataFrame([b.model_dump() for b in bars])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").set_index("timestamp")
            price_frames[symbol] = df["close"]

        prices = pd.DataFrame(price_frames)

        # Generate all parameter combinations
        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        combinations = list(product(*param_values))

        logger.info(
            "starting_parameter_optimization",
            strategy=strategy_class.__name__,
            combinations=len(combinations),
            params=param_names,
        )

        best_result: BacktestResult | None = None
        best_params: dict[str, Any] = {}
        best_metric_value = float("-inf")

        for combo in combinations:
            params = dict(zip(param_names, combo))

            try:
                strategy = strategy_class(**params)
                signals = strategy.generate_signals(filtered)
            except Exception:
                logger.debug("param_combo_failed", params=params)
                continue

            if not signals:
                continue

            result = self._vectorized_backtest(
                strategy, prices, signals, initial_capital, filtered
            )

            metric_value = getattr(result, metric, 0.0)
            if metric_value > best_metric_value:
                best_metric_value = metric_value
                best_result = result
                best_params = params

        if best_result is None:
            raise ValueError("No valid parameter combination found")

        logger.info(
            "optimization_complete",
            best_params=best_params,
            best_metric=f"{metric}={best_metric_value:.4f}",
        )

        return best_params, best_result

    def _vectorized_backtest(
        self,
        strategy: BaseStrategy,
        prices: pd.DataFrame,
        signals: list,
        initial_capital: float,
        data: dict[str, list[OHLCV]],
    ) -> BacktestResult:
        import vectorbt as vbt

        # Build entry/exit boolean arrays from signals
        entries = pd.DataFrame(False, index=prices.index, columns=prices.columns)
        exits = pd.DataFrame(False, index=prices.index, columns=prices.columns)

        from src.core.models import SignalDirection

        for sig in signals:
            ts = pd.Timestamp(sig.timestamp)
            if sig.symbol in entries.columns and ts in entries.index:
                if sig.direction == SignalDirection.LONG:
                    entries.loc[ts, sig.symbol] = True
                elif sig.direction in (SignalDirection.FLAT, SignalDirection.SHORT):
                    exits.loc[ts, sig.symbol] = True

        try:
            portfolio = vbt.Portfolio.from_signals(
                prices,
                entries=entries,
                exits=exits,
                init_cash=initial_capital,
                fees=self._commission_pct / 100.0,
                slippage=self._slippage_pct / 100.0,
                freq="1D",
            )

            total_return = float(portfolio.total_return() * 100) if np.isscalar(portfolio.total_return()) else float(portfolio.total_return().mean() * 100)
            sharpe = float(portfolio.sharpe_ratio()) if np.isscalar(portfolio.sharpe_ratio()) else float(portfolio.sharpe_ratio().mean())
            sortino = float(portfolio.sortino_ratio()) if np.isscalar(portfolio.sortino_ratio()) else float(portfolio.sortino_ratio().mean())
            max_dd = float(portfolio.max_drawdown() * 100) if np.isscalar(portfolio.max_drawdown()) else float(portfolio.max_drawdown().mean() * 100)
            final_value = float(portfolio.final_value()) if np.isscalar(portfolio.final_value()) else float(portfolio.final_value().sum())
            total_trades_val = int(portfolio.trades.count()) if hasattr(portfolio, "trades") else 0

        except Exception:
            logger.debug("vectorbt_backtest_failed", strategy=strategy.name)
            return self._empty_result(strategy.name, initial_capital, prices)

        # Handle NaN values
        sharpe = 0.0 if np.isnan(sharpe) else sharpe
        sortino = 0.0 if np.isnan(sortino) else sortino
        max_dd = 0.0 if np.isnan(max_dd) else abs(max_dd)

        start_date = prices.index.min().to_pydatetime()
        end_date = prices.index.max().to_pydatetime()
        days = (end_date - start_date).days
        years = days / 365.25 if days > 0 else 1.0
        annual_return = ((final_value / initial_capital) ** (1.0 / years) - 1.0) * 100 if years > 0 and initial_capital > 0 else 0.0

        return BacktestResult(
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=round(final_value, 2),
            total_return_pct=round(total_return, 2),
            annual_return_pct=round(annual_return, 2),
            sharpe_ratio=round(sharpe, 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown_pct=round(max_dd, 2),
            profit_factor=0.0,  # vectorbt doesn't provide this directly
            total_trades=total_trades_val,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
        )

    def _filter_data(
        self,
        data: dict[str, list[OHLCV]],
        start: datetime | None,
        end: datetime | None,
    ) -> dict[str, list[OHLCV]]:
        filtered: dict[str, list[OHLCV]] = {}
        for symbol, bars in data.items():
            symbol_bars = bars
            if start:
                symbol_bars = [b for b in symbol_bars if b.timestamp >= start]
            if end:
                symbol_bars = [b for b in symbol_bars if b.timestamp <= end]
            if symbol_bars:
                filtered[symbol] = symbol_bars
        return filtered

    @staticmethod
    def _empty_result(
        strategy_name: str, initial_capital: float, prices: pd.DataFrame
    ) -> BacktestResult:
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=prices.index.min().to_pydatetime(),
            end_date=prices.index.max().to_pydatetime(),
            initial_capital=initial_capital,
            final_capital=initial_capital,
            total_return_pct=0.0,
            annual_return_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown_pct=0.0,
            profit_factor=0.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            avg_win_pct=0.0,
            avg_loss_pct=0.0,
        )
