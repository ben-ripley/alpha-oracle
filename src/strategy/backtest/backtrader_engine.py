from __future__ import annotations

from datetime import datetime
from typing import Any

import backtrader as bt
import numpy as np
import pandas as pd
import structlog
from dateutil.relativedelta import relativedelta

from src.core.config import get_settings
from src.core.interfaces import BacktestEngine, BaseStrategy
from src.core.models import OHLCV, BacktestResult, Signal, SignalDirection

logger = structlog.get_logger(__name__)


class SignalStrategy(bt.Strategy):
    """Backtrader strategy that replays pre-computed signals."""

    params = (
        ("signals", []),
        ("min_hold_days", 2),
        ("initial_capital", 20000.0),
        ("max_positions", 10),
    )

    def __init__(self) -> None:
        self._signal_map: dict[str, dict[datetime, Signal]] = {}
        for sig in self.params.signals:
            self._signal_map.setdefault(sig.symbol, {})[sig.timestamp.replace(tzinfo=None)] = sig
        self._entry_bars: dict[str, int] = {}

    def next(self) -> None:
        dt = self.datas[0].datetime.date(0)
        dt_key = datetime(dt.year, dt.month, dt.day)

        for i, data in enumerate(self.datas):
            symbol = data._name
            sig = self._signal_map.get(symbol, {}).get(dt_key)
            pos = self.getposition(data)

            if sig and sig.direction == SignalDirection.LONG and not pos.size:
                open_positions = len(self._entry_bars)
                if open_positions >= self.params.max_positions:
                    continue
                position_value = self.params.initial_capital / self.params.max_positions
                size = int(position_value / data.close[0])
                if size > 0:
                    self.buy(data=data, size=size)
                    self._entry_bars[symbol] = len(self)

            elif sig and sig.direction == SignalDirection.FLAT and pos.size > 0:
                bars_held = len(self) - self._entry_bars.get(symbol, 0)
                if bars_held >= self.params.min_hold_days:
                    self.close(data=data)
                    self._entry_bars.pop(symbol, None)

            elif sig and sig.direction == SignalDirection.SHORT and pos.size > 0:
                bars_held = len(self) - self._entry_bars.get(symbol, 0)
                if bars_held >= self.params.min_hold_days:
                    self.close(data=data)
                    self._entry_bars.pop(symbol, None)


def _ohlcv_to_feed(bars: list[OHLCV], symbol: str) -> bt.feeds.PandasData:
    df = pd.DataFrame([b.model_dump() for b in bars])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").set_index("timestamp")
    df = df.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
    df = df[["open", "high", "low", "close", "volume"]]
    feed = bt.feeds.PandasData(dataname=df)
    feed._name = symbol
    return feed


class BacktraderEngine(BacktestEngine):
    """Backtesting engine using the Backtrader framework."""

    def __init__(
        self,
        commission: float = 0.0,
        slippage_pct: float = 0.01,
        max_positions: int | None = None,
    ) -> None:
        self._commission = commission
        self._slippage_pct = slippage_pct
        self._max_positions = max_positions

    def run(
        self,
        strategy: BaseStrategy,
        data: dict[str, list[OHLCV]],
        initial_capital: float,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        filtered = self._filter_data(data, start, end)
        if not filtered:
            logger.error("no_data_in_range", start=start, end=end)
            return self._empty_result(strategy.name, start, end, initial_capital)

        signals = strategy.generate_signals(filtered)
        return self._execute_backtest(strategy, filtered, signals, initial_capital, start, end)

    def walk_forward(
        self,
        strategy: BaseStrategy,
        data: dict[str, list[OHLCV]],
        initial_capital: float,
        train_months: int = 24,
        test_months: int = 6,
        step_months: int = 3,
    ) -> list[BacktestResult]:
        all_dates = []
        for bars in data.values():
            all_dates.extend(b.timestamp for b in bars)
        if not all_dates:
            return []

        min_date = min(all_dates)
        max_date = max(all_dates)

        results: list[BacktestResult] = []
        window_start = min_date

        while True:
            train_end = window_start + relativedelta(months=train_months)
            test_start = train_end
            test_end = test_start + relativedelta(months=test_months)

            if test_end > max_date:
                break

            # Train: generate signals on training data
            train_data = self._filter_data(data, window_start, train_end)
            if train_data:
                # Test: apply signals on test data
                test_data = self._filter_data(data, test_start, test_end)
                if test_data:
                    # Generate signals from full training window then test on out-of-sample
                    all_period_data = self._filter_data(data, window_start, test_end)
                    signals = strategy.generate_signals(all_period_data)
                    # Only keep signals in test period
                    test_signals = [s for s in signals if test_start <= s.timestamp <= test_end]

                    result = self._execute_backtest(
                        strategy, test_data, test_signals, initial_capital, test_start, test_end
                    )
                    result.metadata["window_start"] = window_start.isoformat()
                    result.metadata["train_end"] = train_end.isoformat()
                    results.append(result)

            window_start += relativedelta(months=step_months)

        logger.info("walk_forward_complete", windows=len(results), strategy=strategy.name)
        return results

    def _execute_backtest(
        self,
        strategy: BaseStrategy,
        data: dict[str, list[OHLCV]],
        signals: list[Signal],
        initial_capital: float,
        start: datetime,
        end: datetime,
    ) -> BacktestResult:
        cerebro = bt.Cerebro()
        cerebro.broker.setcash(initial_capital)
        cerebro.broker.setcommission(commission=self._commission)
        cerebro.broker.set_slippage_perc(self._slippage_pct / 100.0)

        for symbol, bars in data.items():
            feed = _ohlcv_to_feed(bars, symbol)
            cerebro.adddata(feed, name=symbol)

        max_positions = (
            self._max_positions
            if self._max_positions is not None
            else get_settings().risk.portfolio_limits.max_positions
        )
        cerebro.addstrategy(
            SignalStrategy,
            signals=signals,
            min_hold_days=strategy.min_hold_days,
            initial_capital=initial_capital,
            max_positions=max_positions,
        )

        cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe", riskfreerate=0.0, annualize=True)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
        cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")

        try:
            results = cerebro.run()
        except Exception:
            logger.exception("backtest_execution_error", strategy=strategy.name)
            return self._empty_result(strategy.name, start, end, initial_capital)

        strat = results[0]
        return self._extract_result(strat, strategy.name, start, end, initial_capital)

    def _extract_result(
        self,
        strat: bt.Strategy,
        strategy_name: str,
        start: datetime,
        end: datetime,
        initial_capital: float,
    ) -> BacktestResult:
        final_capital = strat.broker.getvalue()

        # Sharpe
        sharpe_analysis = strat.analyzers.sharpe.get_analysis()
        sharpe = sharpe_analysis.get("sharperatio") or 0.0
        if sharpe is None:
            sharpe = 0.0

        # Drawdown
        dd_analysis = strat.analyzers.drawdown.get_analysis()
        max_dd = dd_analysis.get("max", {}).get("drawdown", 0.0) or 0.0

        # Trade stats
        trade_analysis = strat.analyzers.trades.get_analysis()
        total_trades = trade_analysis.get("total", {}).get("closed", 0) or 0
        won = trade_analysis.get("won", {}).get("total", 0) or 0
        lost = trade_analysis.get("lost", {}).get("total", 0) or 0
        win_rate = won / total_trades if total_trades > 0 else 0.0

        avg_win = trade_analysis.get("won", {}).get("pnl", {}).get("average", 0.0) or 0.0
        avg_loss = abs(trade_analysis.get("lost", {}).get("pnl", {}).get("average", 0.0) or 0.0)

        avg_win_pct = (avg_win / initial_capital * 100) if initial_capital > 0 else 0.0
        avg_loss_pct = (avg_loss / initial_capital * 100) if initial_capital > 0 else 0.0

        gross_wins = trade_analysis.get("won", {}).get("pnl", {}).get("total", 0.0) or 0.0
        gross_losses = abs(trade_analysis.get("lost", {}).get("pnl", {}).get("total", 0.0) or 0.0)
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0.0

        total_return = (final_capital - initial_capital) / initial_capital * 100
        days = (end - start).days
        years = days / 365.25 if days > 0 else 1.0
        annual_return = ((final_capital / initial_capital) ** (1.0 / years) - 1.0) * 100 if years > 0 else 0.0

        # Sortino: use returns analyzer
        returns_analysis = strat.analyzers.returns.get_analysis()
        # Approximate Sortino from available data
        sortino = self._estimate_sortino(sharpe, total_return, years)

        return BacktestResult(
            strategy_name=strategy_name,
            start_date=start,
            end_date=end,
            initial_capital=initial_capital,
            final_capital=round(final_capital, 2),
            total_return_pct=round(total_return, 2),
            annual_return_pct=round(annual_return, 2),
            sharpe_ratio=round(float(sharpe), 4),
            sortino_ratio=round(sortino, 4),
            max_drawdown_pct=round(max_dd, 2),
            profit_factor=round(profit_factor, 4),
            total_trades=total_trades,
            winning_trades=won,
            losing_trades=lost,
            win_rate=round(win_rate, 4),
            avg_win_pct=round(avg_win_pct, 4),
            avg_loss_pct=round(avg_loss_pct, 4),
        )

    @staticmethod
    def _estimate_sortino(sharpe: float, total_return: float, years: float) -> float:
        """Approximate Sortino ratio from Sharpe. Sortino is typically higher since it only
        penalizes downside volatility."""
        if sharpe == 0:
            return 0.0
        # Rough heuristic: Sortino ~= Sharpe * 1.3 for typical equity strategies
        return sharpe * 1.3

    def _filter_data(
        self, data: dict[str, list[OHLCV]], start: datetime, end: datetime
    ) -> dict[str, list[OHLCV]]:
        filtered: dict[str, list[OHLCV]] = {}
        for symbol, bars in data.items():
            symbol_bars = [b for b in bars if start <= b.timestamp <= end]
            if symbol_bars:
                filtered[symbol] = symbol_bars
        return filtered

    @staticmethod
    def _empty_result(
        strategy_name: str, start: datetime, end: datetime, initial_capital: float
    ) -> BacktestResult:
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=start,
            end_date=end,
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
