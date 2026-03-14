"""Unit tests for built-in strategies and StrategyEngine.

All tests use synthetic OHLCV data — no database, broker, or Backtrader required.
generate_signals() is pure Python; the tests verify correct behaviour and PDT
compliance without needing a full backtest run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sin

import pytest
from unittest.mock import MagicMock

from src.core.models import (
    OHLCV,
    BacktestResult,
    FundamentalData,
    Signal,
    SignalDirection,
    StrategyRanking,
)
from src.strategy.builtin.mean_reversion import MeanReversion
from src.strategy.builtin.swing_momentum import SwingMomentum
from src.strategy.builtin.value_factor import ValueFactor
from src.strategy.engine import StrategyEngine
from src.strategy.ranker import StrategyRanker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(symbol: str, days: int = 60, base: float = 150.0) -> list[OHLCV]:
    """Synthetic daily bars with a slow-oscillating price (sin wave).

    The sine period is long enough that the 50-day SMA and 10-day SMA both form
    cleanly without flat lines.  60 bars satisfies SwingMomentum's minimum
    (slow_period=50, requires slow_period+10=60).
    """
    start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    bars: list[OHLCV] = []
    for i in range(days):
        close = base * (1.0 + 0.03 * sin(i / 8.0))
        bars.append(
            OHLCV(
                symbol=symbol,
                timestamp=start + timedelta(days=i),
                open=close * 0.99,
                high=close * 1.015,
                low=close * 0.985,
                close=close,
                volume=1_000_000 + i * 1_000,
            )
        )
    return bars


def _make_fundamentals(symbol: str, pe: float, pb: float, ev: float) -> FundamentalData:
    return FundamentalData(
        symbol=symbol,
        timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        pe_ratio=pe,
        pb_ratio=pb,
        ev_ebitda=ev,
        sector="Technology",
    )


def _make_backtest_result(name: str, sharpe: float = 1.5) -> BacktestResult:
    return BacktestResult(
        strategy_name=name,
        start_date=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        initial_capital=20_000.0,
        final_capital=24_000.0,
        total_return_pct=20.0,
        annual_return_pct=9.5,
        sharpe_ratio=sharpe,
        sortino_ratio=1.8,
        max_drawdown_pct=8.0,
        profit_factor=1.6,
        total_trades=42,
        winning_trades=26,
        losing_trades=16,
        win_rate=61.9,
        avg_win_pct=2.1,
        avg_loss_pct=-1.3,
    )


# ---------------------------------------------------------------------------
# PDT compliance
# ---------------------------------------------------------------------------

class TestMinHoldDays:
    def test_swing_momentum_min_hold_days(self):
        assert SwingMomentum().min_hold_days >= 2

    def test_mean_reversion_min_hold_days(self):
        assert MeanReversion().min_hold_days >= 2

    def test_value_factor_min_hold_days(self):
        assert ValueFactor().min_hold_days >= 2

    def test_swing_momentum_specific_value(self):
        # Documented as 3 in the strategy
        assert SwingMomentum().min_hold_days == 3

    def test_mean_reversion_specific_value(self):
        assert MeanReversion().min_hold_days == 2

    def test_value_factor_specific_value(self):
        # Minimum 5 days (weekly rebalance)
        assert ValueFactor().min_hold_days == 5


# ---------------------------------------------------------------------------
# get_parameters()
# ---------------------------------------------------------------------------

class TestGetParameters:
    def test_swing_momentum_has_parameters(self):
        params = SwingMomentum().get_parameters()
        assert isinstance(params, dict)
        assert len(params) > 0
        assert "fast_period" in params
        assert "slow_period" in params

    def test_mean_reversion_has_parameters(self):
        params = MeanReversion().get_parameters()
        assert isinstance(params, dict)
        assert len(params) > 0
        assert "bb_period" in params
        assert "rsi_period" in params

    def test_value_factor_has_parameters(self):
        params = ValueFactor().get_parameters()
        assert isinstance(params, dict)
        assert len(params) > 0
        assert "rebalance_days" in params
        assert "top_pct" in params


# ---------------------------------------------------------------------------
# get_required_data()
# ---------------------------------------------------------------------------

class TestRequiredData:
    def test_swing_momentum_requires_ohlcv(self):
        required = SwingMomentum().get_required_data()
        assert isinstance(required, list)
        assert len(required) > 0
        assert "ohlcv" in required

    def test_mean_reversion_requires_ohlcv(self):
        required = MeanReversion().get_required_data()
        assert "ohlcv" in required

    def test_value_factor_requires_ohlcv_and_fundamentals(self):
        required = ValueFactor().get_required_data()
        assert "ohlcv" in required
        assert "fundamentals" in required


# ---------------------------------------------------------------------------
# generate_signals() — no exception, returns list
# ---------------------------------------------------------------------------

class TestSwingMomentumSignals:
    def test_returns_list_of_signals(self):
        bars = _make_ohlcv("AAPL", days=60)
        signals = SwingMomentum().generate_signals({"AAPL": bars})
        assert isinstance(signals, list)
        assert all(isinstance(s, Signal) for s in signals)

    def test_insufficient_data_returns_empty(self):
        # 10 bars is far less than the 60 minimum
        bars = _make_ohlcv("AAPL", days=10)
        signals = SwingMomentum().generate_signals({"AAPL": bars})
        assert signals == []

    def test_multiple_symbols(self):
        data = {
            "AAPL": _make_ohlcv("AAPL", days=60),
            "MSFT": _make_ohlcv("MSFT", days=60, base=300.0),
        }
        signals = SwingMomentum().generate_signals(data)
        assert isinstance(signals, list)

    def test_empty_data_returns_empty(self):
        assert SwingMomentum().generate_signals({}) == []

    def test_signal_fields_valid(self):
        """Any emitted signal must have required fields in valid ranges."""
        bars = _make_ohlcv("AAPL", days=60)
        signals = SwingMomentum().generate_signals({"AAPL": bars})
        for s in signals:
            assert s.symbol == "AAPL"
            assert s.direction in (SignalDirection.LONG, SignalDirection.FLAT)
            assert 0.0 <= s.strength <= 1.0
            assert s.strategy_name == "swing_momentum"


class TestMeanReversionSignals:
    def test_returns_list_of_signals(self):
        bars = _make_ohlcv("AAPL", days=60)
        signals = MeanReversion().generate_signals({"AAPL": bars})
        assert isinstance(signals, list)
        assert all(isinstance(s, Signal) for s in signals)

    def test_insufficient_data_returns_empty(self):
        bars = _make_ohlcv("AAPL", days=5)
        signals = MeanReversion().generate_signals({"AAPL": bars})
        assert signals == []

    def test_multiple_symbols(self):
        data = {
            "AAPL": _make_ohlcv("AAPL", days=60),
            "MSFT": _make_ohlcv("MSFT", days=60, base=300.0),
        }
        signals = MeanReversion().generate_signals(data)
        assert isinstance(signals, list)

    def test_signal_fields_valid(self):
        bars = _make_ohlcv("AAPL", days=60)
        signals = MeanReversion().generate_signals({"AAPL": bars})
        for s in signals:
            assert s.symbol == "AAPL"
            assert 0.0 <= s.strength <= 1.0
            assert s.strategy_name == "mean_reversion"


class TestValueFactorSignals:
    def _make_data_and_strategy(self) -> tuple[ValueFactor, dict]:
        strategy = ValueFactor()
        # Need >= 3 symbols with fundamentals for _compute_value_scores
        fundamentals = {
            "AAPL": _make_fundamentals("AAPL", pe=18.0, pb=6.0, ev=15.0),
            "MSFT": _make_fundamentals("MSFT", pe=30.0, pb=12.0, ev=22.0),
            "JPM":  _make_fundamentals("JPM",  pe=10.0, pb=1.5, ev=8.0),
            "XOM":  _make_fundamentals("XOM",  pe=12.0, pb=2.0, ev=6.0),
            "UNH":  _make_fundamentals("UNH",  pe=22.0, pb=5.0, ev=18.0),
        }
        strategy.set_fundamentals(fundamentals)
        data = {sym: _make_ohlcv(sym, days=10) for sym in fundamentals}
        return strategy, data

    def test_returns_list_of_signals(self):
        strategy, data = self._make_data_and_strategy()
        signals = strategy.generate_signals(data)
        assert isinstance(signals, list)
        assert all(isinstance(s, Signal) for s in signals)

    def test_no_fundamentals_returns_empty(self):
        strategy = ValueFactor()
        data = {"AAPL": _make_ohlcv("AAPL", days=10)}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_fewer_than_three_fundamentals_returns_empty(self):
        strategy = ValueFactor()
        strategy.set_fundamentals({
            "AAPL": _make_fundamentals("AAPL", pe=18.0, pb=6.0, ev=15.0),
            "MSFT": _make_fundamentals("MSFT", pe=30.0, pb=12.0, ev=22.0),
        })
        data = {sym: _make_ohlcv(sym, days=10) for sym in ["AAPL", "MSFT"]}
        signals = strategy.generate_signals(data)
        assert signals == []

    def test_produces_long_signals_for_top_quintile(self):
        strategy, data = self._make_data_and_strategy()
        signals = strategy.generate_signals(data)
        long_signals = [s for s in signals if s.direction == SignalDirection.LONG]
        assert len(long_signals) > 0

    def test_signal_fields_valid(self):
        strategy, data = self._make_data_and_strategy()
        signals = strategy.generate_signals(data)
        for s in signals:
            assert 0.0 <= s.strength <= 1.0
            assert s.strategy_name == "value_factor"
            assert s.direction in (SignalDirection.LONG, SignalDirection.SHORT)


# ---------------------------------------------------------------------------
# StrategyEngine
# ---------------------------------------------------------------------------

class TestStrategyEngine:
    def test_register_strategy_succeeds(self):
        engine = StrategyEngine()
        engine.register_strategy(SwingMomentum())
        assert "swing_momentum" in engine.list_strategies()

    def test_register_rejects_min_hold_days_below_2(self):
        """PDT safety: strategies with min_hold_days < 2 must be rejected."""

        class BadStrategy(SwingMomentum):
            @property
            def min_hold_days(self) -> int:
                return 1

        engine = StrategyEngine()
        with pytest.raises(ValueError, match="min_hold_days"):
            engine.register_strategy(BadStrategy())

    def test_get_strategy_raises_for_unknown(self):
        engine = StrategyEngine()
        with pytest.raises(KeyError):
            engine.get_strategy("nonexistent")

    def test_list_strategies_empty_initially(self):
        engine = StrategyEngine()
        assert engine.list_strategies() == []

    def test_get_live_signals_aggregates_all_strategies(self):
        engine = StrategyEngine()
        engine.register_strategy(SwingMomentum())
        engine.register_strategy(MeanReversion())

        data = {
            "AAPL": _make_ohlcv("AAPL", days=60),
            "MSFT": _make_ohlcv("MSFT", days=60, base=300.0),
        }
        signals = engine.get_live_signals(data)
        # Signals come from both strategies — result is a flat list
        assert isinstance(signals, list)
        strategy_names = {s.strategy_name for s in signals}
        # Both strategies processed data without error
        # (signals list may be empty if no crossovers/touches occurred)
        for name in strategy_names:
            assert name in ("swing_momentum", "mean_reversion")

    def test_get_live_signals_isolates_strategy_errors(self):
        """A crashing strategy must not prevent others from running."""

        class CrashingStrategy(SwingMomentum):
            @property
            def name(self) -> str:
                return "crashing"

            def generate_signals(self, data):
                raise RuntimeError("simulated crash")

        engine = StrategyEngine()
        engine.register_strategy(CrashingStrategy())
        engine.register_strategy(MeanReversion())

        data = {"AAPL": _make_ohlcv("AAPL", days=60)}
        # Should not raise — crashing strategy is skipped
        signals = engine.get_live_signals(data)
        assert isinstance(signals, list)


# ---------------------------------------------------------------------------
# StrategyRanker
# ---------------------------------------------------------------------------

class TestStrategyRanker:
    def test_rank_returns_list_of_rankings(self):
        ranker = StrategyRanker()
        results = [
            _make_backtest_result("swing_momentum", sharpe=1.8),
            _make_backtest_result("mean_reversion", sharpe=1.2),
            _make_backtest_result("value_factor", sharpe=0.9),
        ]
        rankings = ranker.rank_strategies(results)
        assert len(rankings) == 3
        assert all(isinstance(r, StrategyRanking) for r in rankings)

    def test_rank_sorts_by_composite_score_descending(self):
        ranker = StrategyRanker()
        results = [
            _make_backtest_result("low_sharpe", sharpe=0.5),
            _make_backtest_result("high_sharpe", sharpe=2.5),
            _make_backtest_result("mid_sharpe", sharpe=1.5),
        ]
        rankings = ranker.rank_strategies(results)
        scores = [r.composite_score for r in rankings]
        assert scores == sorted(scores, reverse=True)

    def test_rank_composite_scores_are_finite(self):
        ranker = StrategyRanker()
        results = [_make_backtest_result("swing_momentum", sharpe=1.5)]
        rankings = ranker.rank_strategies(results)
        import math
        assert math.isfinite(rankings[0].composite_score)

    def test_rank_empty_returns_empty(self):
        ranker = StrategyRanker()
        assert ranker.rank_strategies([]) == []

    def test_higher_sharpe_ranks_higher(self):
        ranker = StrategyRanker()
        results = [
            _make_backtest_result("weak", sharpe=0.3),
            _make_backtest_result("strong", sharpe=2.5),
        ]
        rankings = ranker.rank_strategies(results)
        assert rankings[0].strategy_name == "strong"


# ---------------------------------------------------------------------------
# BacktraderEngine position sizing (Task 1)
# ---------------------------------------------------------------------------

class TestBacktraderPositionSizing:
    """Verify equal-weight sizing and capacity cap in SignalStrategy."""

    def _make_signals(
        self,
        symbols: list[str],
        buy_day: int,
        sell_day: int,
        base_date: datetime,
    ) -> list[Signal]:
        """Generate LONG signals on buy_day and FLAT signals on sell_day for each symbol."""
        signals = []
        for sym in symbols:
            signals.append(Signal(
                symbol=sym,
                timestamp=base_date + timedelta(days=buy_day),
                direction=SignalDirection.LONG,
                strength=0.8,
                strategy_name="test",
            ))
            signals.append(Signal(
                symbol=sym,
                timestamp=base_date + timedelta(days=sell_day),
                direction=SignalDirection.FLAT,
                strength=0.8,
                strategy_name="test",
            ))
        return signals

    def test_capacity_cap_limits_open_positions(self):
        """With max_positions=1, only 1 of 2 simultaneous LONG signals should execute."""
        from src.strategy.backtest.backtrader_engine import BacktraderEngine

        base = datetime(2024, 1, 2, tzinfo=timezone.utc)
        bars = {
            "AAPL": _make_ohlcv("AAPL", days=20, base=100.0),
            "MSFT": _make_ohlcv("MSFT", days=20, base=100.0),
        }
        signals = self._make_signals(["AAPL", "MSFT"], buy_day=2, sell_day=10, base_date=base)

        engine = BacktraderEngine(max_positions=1)
        strategy_stub = MagicMock()
        strategy_stub.name = "test"
        strategy_stub.min_hold_days = 2
        strategy_stub.generate_signals = MagicMock(return_value=signals)

        result = engine.run(
            strategy_stub,
            bars,
            initial_capital=10000.0,
            start=base,
            end=base + timedelta(days=19),
        )

        # With max_positions=1, at most 1 round-trip trade can complete
        assert result.total_trades == 1
