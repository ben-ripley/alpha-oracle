from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, FundamentalData, Signal, SignalDirection

logger = structlog.get_logger(__name__)


class ValueFactor(BaseStrategy):
    """Value factor strategy that ranks stocks by composite value score.

    Ranks by PE, PB, and EV/EBITDA ratios. Buys top quintile, sells bottom quintile.
    Rebalances on a configurable schedule (weekly/monthly).
    """

    def __init__(
        self,
        rebalance_days: int = 5,
        top_pct: float = 20.0,
        value_weights: dict[str, float] | None = None,
    ) -> None:
        self._rebalance_days = max(rebalance_days, 5)  # min 5 days (weekly)
        self._top_pct = top_pct
        self._value_weights = value_weights or {
            "pe_ratio": 0.40,
            "pb_ratio": 0.30,
            "ev_ebitda": 0.30,
        }
        self._fundamentals: dict[str, FundamentalData] = {}

    @property
    def name(self) -> str:
        return "value_factor"

    @property
    def description(self) -> str:
        return (
            f"Value factor ranking (PE/PB/EV-EBITDA) "
            f"with {self._rebalance_days}-day rebalance, top {self._top_pct}%"
        )

    @property
    def min_hold_days(self) -> int:
        return 5

    def get_parameters(self) -> dict[str, Any]:
        return {
            "rebalance_days": self._rebalance_days,
            "top_pct": self._top_pct,
            "value_weights": self._value_weights,
        }

    def get_required_data(self) -> list[str]:
        return ["ohlcv", "fundamentals"]

    def set_fundamentals(self, fundamentals: dict[str, FundamentalData]) -> None:
        self._fundamentals = fundamentals

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        if not self._fundamentals:
            logger.warning("no_fundamentals_data", strategy=self.name)
            return []

        scores = self._compute_value_scores()
        if not scores:
            return []

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        n_top = max(1, int(len(sorted_scores) * self._top_pct / 100.0))
        n_bottom = max(1, int(len(sorted_scores) * self._top_pct / 100.0))

        top_symbols = {s for s, _ in sorted_scores[:n_top]}
        bottom_symbols = {s for s, _ in sorted_scores[-n_bottom:]}

        signals: list[Signal] = []

        for symbol, bars in data.items():
            if len(bars) < self._rebalance_days:
                continue

            rebalance_signals = self._generate_rebalance_signals(
                symbol, bars, top_symbols, bottom_symbols, scores
            )
            signals.extend(rebalance_signals)

        return signals

    def _compute_value_scores(self) -> dict[str, float]:
        records = []
        for symbol, fund in self._fundamentals.items():
            if fund.pe_ratio is None and fund.pb_ratio is None and fund.ev_ebitda is None:
                continue
            records.append({
                "symbol": symbol,
                "pe_ratio": fund.pe_ratio,
                "pb_ratio": fund.pb_ratio,
                "ev_ebitda": fund.ev_ebitda,
            })

        if len(records) < 3:
            return {}

        df = pd.DataFrame(records).set_index("symbol")

        # Lower ratios = better value, so we invert the rank (higher rank = better value)
        scores: dict[str, float] = {}
        for symbol in df.index:
            score = 0.0
            total_weight = 0.0
            for metric, weight in self._value_weights.items():
                val = df.loc[symbol, metric]
                if pd.notna(val) and val > 0:
                    # Rank percentile: lower ratio -> higher score
                    col_values = df[metric].dropna()
                    col_values = col_values[col_values > 0]
                    rank_pct = (col_values < val).sum() / len(col_values)
                    # Invert: low ratio = high value score
                    score += (1.0 - rank_pct) * weight
                    total_weight += weight

            if total_weight > 0:
                scores[symbol] = score / total_weight

        return scores

    def _generate_rebalance_signals(
        self,
        symbol: str,
        bars: list[OHLCV],
        top_symbols: set[str],
        bottom_symbols: set[str],
        scores: dict[str, float],
    ) -> list[Signal]:
        signals: list[Signal] = []
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)

        for i in range(0, len(sorted_bars), self._rebalance_days):
            bar = sorted_bars[i]
            ts = bar.timestamp

            if symbol in top_symbols:
                signals.append(
                    Signal(
                        symbol=symbol,
                        timestamp=ts,
                        direction=SignalDirection.LONG,
                        strength=min(1.0, scores.get(symbol, 0.5)),
                        strategy_name=self.name,
                        metadata={"value_score": scores.get(symbol, 0.0), "action": "buy_top_quintile"},
                    )
                )
            elif symbol in bottom_symbols:
                signals.append(
                    Signal(
                        symbol=symbol,
                        timestamp=ts,
                        direction=SignalDirection.SHORT,
                        strength=min(1.0, 1.0 - scores.get(symbol, 0.5)),
                        strategy_name=self.name,
                        metadata={"value_score": scores.get(symbol, 0.0), "action": "sell_bottom_quintile"},
                    )
                )

        return signals
