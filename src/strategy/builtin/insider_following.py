from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from src.core.interfaces import BaseStrategy
from src.core.models import OHLCV, InsiderTransaction, Signal, SignalDirection

logger = structlog.get_logger(__name__)


class InsiderFollowing(BaseStrategy):
    """Strategy that follows significant insider buying clusters.

    Generates LONG signals when multiple distinct insiders purchase stock within
    a rolling lookback window, totalling enough shares to suggest conviction.
    Exits after a fixed hold period, on net insider selling, or on stop-loss.
    """

    def __init__(
        self,
        lookback_days: int = 90,
        min_net_shares: float = 5_000.0,
        min_buy_count: int = 2,
        hold_days: int = 21,
        stop_loss_pct: float = 10.0,
    ) -> None:
        self._lookback_days = lookback_days
        self._min_net_shares = min_net_shares
        self._min_buy_count = min_buy_count
        self._hold_days = hold_days
        self._stop_loss_pct = stop_loss_pct
        self._transactions: dict[str, list[InsiderTransaction]] = {}

    @property
    def name(self) -> str:
        return "insider_following"

    @property
    def description(self) -> str:
        return (
            f"Insider cluster buying: ≥{self._min_buy_count} insiders, "
            f"≥{self._min_net_shares:,.0f} shares, {self._lookback_days}-day window, "
            f"{self._hold_days}-day hold"
        )

    @property
    def min_hold_days(self) -> int:
        return 10

    def get_parameters(self) -> dict[str, Any]:
        return {
            "lookback_days": self._lookback_days,
            "min_net_shares": self._min_net_shares,
            "min_buy_count": self._min_buy_count,
            "hold_days": self._hold_days,
            "stop_loss_pct": self._stop_loss_pct,
        }

    def get_required_data(self) -> list[str]:
        return ["ohlcv", "insider_transactions"]

    def set_insider_transactions(
        self, transactions: dict[str, list[InsiderTransaction]]
    ) -> None:
        """Provide insider transaction data before calling generate_signals."""
        self._transactions = transactions

    def generate_signals(self, data: dict[str, list[OHLCV]]) -> list[Signal]:
        signals: list[Signal] = []
        for symbol, bars in data.items():
            if len(bars) < self.min_hold_days:
                logger.warning(
                    "insufficient_data",
                    symbol=symbol,
                    bars=len(bars),
                    required=self.min_hold_days,
                )
                continue
            txns = self._transactions.get(symbol, [])
            signals.extend(self._generate_for_symbol(symbol, bars, txns))
        return signals

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _cluster_buy_strength(
        self, as_of: datetime, txns: list[InsiderTransaction]
    ) -> float:
        """Return signal strength [0, 1] for the purchase cluster visible as of *as_of*.

        Returns 0 if the cluster does not meet the minimum thresholds.
        Strength scales logarithmically with total net shares above the minimum.
        """
        cutoff = as_of - timedelta(days=self._lookback_days)
        purchases = [
            t for t in txns
            if t.transaction_type == "P" and cutoff <= t.filed_date <= as_of
        ]
        if len(purchases) < self._min_buy_count:
            return 0.0
        net_shares = sum(t.shares for t in purchases)
        if net_shares < self._min_net_shares:
            return 0.0
        # log10 scale: 1× threshold → 0.0, 10× → 1.0, capped at 1.0
        return min(1.0, math.log10(max(1.0, net_shares / self._min_net_shares)))

    def _has_net_selling(
        self, as_of: datetime, txns: list[InsiderTransaction]
    ) -> bool:
        """True if insiders are net sellers over the lookback window as of *as_of*."""
        cutoff = as_of - timedelta(days=self._lookback_days)
        window = [
            t for t in txns
            if t.transaction_type in ("P", "S") and cutoff <= t.filed_date <= as_of
        ]
        net = sum(
            t.shares if t.transaction_type == "P" else -t.shares
            for t in window
        )
        return net < 0

    def _generate_for_symbol(
        self,
        symbol: str,
        bars: list[OHLCV],
        txns: list[InsiderTransaction],
    ) -> list[Signal]:
        df = pd.DataFrame([b.model_dump() for b in bars])
        df = df.sort_values("timestamp").reset_index(drop=True)

        signals: list[Signal] = []
        in_position = False
        entry_price = 0.0
        entry_idx = 0

        for i in range(len(df)):
            row = df.iloc[i]
            ts = row["timestamp"]
            if not isinstance(ts, datetime):
                ts = pd.Timestamp(ts).to_pydatetime()

            if not in_position:
                strength = self._cluster_buy_strength(ts, txns)
                if strength > 0:
                    signals.append(
                        Signal(
                            symbol=symbol,
                            timestamp=ts,
                            direction=SignalDirection.LONG,
                            strength=strength,
                            strategy_name=self.name,
                            metadata={
                                "cluster_strength": strength,
                                "lookback_days": self._lookback_days,
                            },
                        )
                    )
                    in_position = True
                    entry_price = row["close"]
                    entry_idx = i
            else:
                hold = i - entry_idx
                if hold < self.min_hold_days:
                    continue

                loss_pct = (row["close"] - entry_price) / entry_price * 100
                stop_hit = loss_pct <= -self._stop_loss_pct
                hold_complete = hold >= self._hold_days
                selling_detected = self._has_net_selling(ts, txns)

                if stop_hit or hold_complete or selling_detected:
                    reason = (
                        "stop_loss" if stop_hit
                        else ("insider_selling" if selling_detected else "hold_complete")
                    )
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
