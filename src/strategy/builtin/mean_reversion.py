from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import structlog

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, Signal, SignalDirection
from src.strategy.builtin._indicators import bbands, rsi

logger = structlog.get_logger(__name__)


class MeanReversion(BaseStrategy):
    """Mean reversion strategy using Bollinger Bands + RSI.

    Buy when price touches lower BB and RSI < oversold threshold.
    Sell when price reaches middle BB or RSI > exit threshold or stop-loss hit.
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_exit: float = 60.0,
        stop_loss_pct: float = 5.0,
    ) -> None:
        self._bb_period = bb_period
        self._bb_std = bb_std
        self._rsi_period = rsi_period
        self._rsi_oversold = rsi_oversold
        self._rsi_exit = rsi_exit
        self._stop_loss_pct = stop_loss_pct

    @property
    def name(self) -> str:
        return "mean_reversion"

    @property
    def description(self) -> str:
        return (
            f"Bollinger Band ({self._bb_period},{self._bb_std}) "
            f"mean reversion with RSI({self._rsi_period}) filter"
        )

    @property
    def min_hold_days(self) -> int:
        return 2

    def get_parameters(self) -> dict[str, Any]:
        return {
            "bb_period": self._bb_period,
            "bb_std": self._bb_std,
            "rsi_period": self._rsi_period,
            "rsi_oversold": self._rsi_oversold,
            "rsi_exit": self._rsi_exit,
            "stop_loss_pct": self._stop_loss_pct,
        }

    def get_required_data(self) -> list[str]:
        return ["ohlcv"]

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        signals: list[Signal] = []

        for symbol, bars in data.items():
            required = max(self._bb_period, self._rsi_period) + 10
            if len(bars) < required:
                logger.warning(
                    "insufficient_data",
                    symbol=symbol,
                    bars=len(bars),
                    required=required,
                )
                continue

            symbol_signals = self._generate_for_symbol(symbol, bars)
            signals.extend(symbol_signals)

        return signals

    def _generate_for_symbol(self, symbol: str, bars: list[OHLCV]) -> list[Signal]:
        df = pd.DataFrame([b.model_dump() for b in bars])
        df = df.sort_values("timestamp").reset_index(drop=True)

        bb_data = bbands(df["close"], length=self._bb_period, std=self._bb_std)
        if bb_data is None or bb_data.empty:
            return []

        lower_col = f"BBL_{self._bb_period}_{self._bb_std}"
        mid_col = f"BBM_{self._bb_period}_{self._bb_std}"
        df["bb_lower"] = bb_data[lower_col]
        df["bb_mid"] = bb_data[mid_col]
        df["rsi"] = rsi(df["close"], length=self._rsi_period)
        df = df.dropna(subset=["bb_lower", "bb_mid", "rsi"]).reset_index(drop=True)

        if len(df) < 2:
            return []

        signals: list[Signal] = []
        in_position = False
        entry_price = 0.0
        entry_idx = 0

        for i in range(len(df)):
            row = df.iloc[i]
            ts = row["timestamp"]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()

            # Buy: price touches/crosses lower BB and RSI oversold
            if (
                not in_position
                and row["close"] <= row["bb_lower"]
                and row["rsi"] < self._rsi_oversold
            ):
                strength = min(1.0, max(0.1, (self._rsi_oversold - row["rsi"]) / 50.0))
                signals.append(
                    Signal(
                        symbol=symbol,
                        timestamp=ts,
                        direction=SignalDirection.LONG,
                        strength=strength,
                        strategy_name=self.name,
                        metadata={
                            "rsi": row["rsi"],
                            "close": row["close"],
                            "bb_lower": row["bb_lower"],
                        },
                    )
                )
                in_position = True
                entry_price = row["close"]
                entry_idx = i

            # Sell: price reaches mid BB, RSI above exit, or stop-loss
            elif in_position and (i - entry_idx) >= self.min_hold_days:
                loss_pct = (row["close"] - entry_price) / entry_price * 100
                stop_hit = loss_pct <= -self._stop_loss_pct
                at_mid = row["close"] >= row["bb_mid"]
                rsi_exit = row["rsi"] > self._rsi_exit

                if stop_hit or at_mid or rsi_exit:
                    reason = "stop_loss" if stop_hit else ("rsi_exit" if rsi_exit else "bb_mid_reached")
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
