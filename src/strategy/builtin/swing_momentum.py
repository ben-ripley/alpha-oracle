from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import structlog

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, Signal, SignalDirection
from src.strategy.builtin._indicators import rsi, sma

logger = structlog.get_logger(__name__)


class SwingMomentum(BaseStrategy):
    """Swing trading strategy based on moving average crossover + RSI filter.

    Buy when fast MA crosses above slow MA AND RSI < overbought threshold.
    Sell when fast MA crosses below slow MA OR RSI > sell threshold OR stop-loss hit.
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 50,
        rsi_period: int = 14,
        rsi_overbought: float = 70.0,
        rsi_sell_threshold: float = 80.0,
        stop_loss_pct: float = 5.0,
    ) -> None:
        self._fast_period = fast_period
        self._slow_period = slow_period
        self._rsi_period = rsi_period
        self._rsi_overbought = rsi_overbought
        self._rsi_sell_threshold = rsi_sell_threshold
        self._stop_loss_pct = stop_loss_pct

    @property
    def name(self) -> str:
        return "swing_momentum"

    @property
    def description(self) -> str:
        return (
            f"MA crossover ({self._fast_period}/{self._slow_period}) "
            f"with RSI({self._rsi_period}) filter"
        )

    @property
    def min_hold_days(self) -> int:
        return 3

    def get_parameters(self) -> dict[str, Any]:
        return {
            "fast_period": self._fast_period,
            "slow_period": self._slow_period,
            "rsi_period": self._rsi_period,
            "rsi_overbought": self._rsi_overbought,
            "rsi_sell_threshold": self._rsi_sell_threshold,
            "stop_loss_pct": self._stop_loss_pct,
        }

    def get_required_data(self) -> list[str]:
        return ["ohlcv"]

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        signals: list[Signal] = []

        for symbol, bars in data.items():
            if len(bars) < self._slow_period + 10:
                logger.warning(
                    "insufficient_data",
                    symbol=symbol,
                    bars=len(bars),
                    required=self._slow_period + 10,
                )
                continue

            symbol_signals = self._generate_for_symbol(symbol, bars)
            signals.extend(symbol_signals)

        return signals

    def _generate_for_symbol(self, symbol: str, bars: list[OHLCV]) -> list[Signal]:
        df = pd.DataFrame([b.model_dump() for b in bars])
        df = df.sort_values("timestamp").reset_index(drop=True)

        df["fast_ma"] = sma(df["close"], length=self._fast_period)
        df["slow_ma"] = sma(df["close"], length=self._slow_period)
        df["rsi"] = rsi(df["close"], length=self._rsi_period)
        df = df.dropna(subset=["fast_ma", "slow_ma", "rsi"]).reset_index(drop=True)

        if len(df) < 2:
            return []

        signals: list[Signal] = []
        in_position = False
        entry_price = 0.0
        entry_idx = 0

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            ts = row["timestamp"]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()

            # Buy signal: fast MA crosses above slow MA and RSI not overbought
            if (
                not in_position
                and prev["fast_ma"] <= prev["slow_ma"]
                and row["fast_ma"] > row["slow_ma"]
                and row["rsi"] < self._rsi_overbought
            ):
                strength = min(1.0, max(0.1, (self._rsi_overbought - row["rsi"]) / 100.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        timestamp=ts,
                        direction=SignalDirection.LONG,
                        strength=strength,
                        strategy_name=self.name,
                        metadata={"rsi": row["rsi"], "fast_ma": row["fast_ma"], "slow_ma": row["slow_ma"]},
                    )
                )
                in_position = True
                entry_price = row["close"]
                entry_idx = i

            # Sell signal
            elif in_position and (i - entry_idx) >= self.min_hold_days:
                loss_pct = (row["close"] - entry_price) / entry_price * 100
                stop_hit = loss_pct <= -self._stop_loss_pct
                ma_cross_down = row["fast_ma"] < row["slow_ma"]
                rsi_high = row["rsi"] > self._rsi_sell_threshold

                if stop_hit or ma_cross_down or rsi_high:
                    reason = "stop_loss" if stop_hit else ("rsi_sell" if rsi_high else "ma_cross_down")
                    signals.append(
                        Signal(
                            symbol=symbol,
                            timestamp=ts,
                            direction=SignalDirection.FLAT,
                            strength=0.8 if stop_hit else 0.6,
                            strategy_name=self.name,
                            metadata={"reason": reason, "pnl_pct": loss_pct},
                        )
                    )
                    in_position = False

        return signals
