"""Reconciliation engine: compares internal vs broker positions."""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.core.config import get_settings
from src.core.models import Position

logger = structlog.get_logger(__name__)


@dataclass
class Discrepancy:
    symbol: str
    field: str
    internal_value: float
    broker_value: float
    drift_pct: float
    severity: str  # "info", "warning", "critical"


class ReconciliationEngine:
    """Compares internal position tracking vs broker-reported positions."""

    def __init__(self) -> None:
        self._max_drift_pct = (
            get_settings().risk.circuit_breakers.max_reconciliation_drift_pct
        )

    def reconcile(
        self,
        internal_positions: list[Position],
        broker_positions: list[Position],
    ) -> list[Discrepancy]:
        """Compare internal vs broker positions and return discrepancies."""
        discrepancies: list[Discrepancy] = []

        internal_map = {p.symbol: p for p in internal_positions}
        broker_map = {p.symbol: p for p in broker_positions}

        all_symbols = set(internal_map.keys()) | set(broker_map.keys())

        for symbol in all_symbols:
            internal = internal_map.get(symbol)
            broker = broker_map.get(symbol)

            if internal is None and broker is not None:
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    field="position",
                    internal_value=0.0,
                    broker_value=broker.quantity,
                    drift_pct=100.0,
                    severity="critical",
                ))
                continue

            if broker is None and internal is not None:
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    field="position",
                    internal_value=internal.quantity,
                    broker_value=0.0,
                    drift_pct=100.0,
                    severity="critical",
                ))
                continue

            # Both exist — compare quantity
            assert internal is not None and broker is not None
            if internal.quantity != broker.quantity:
                base = max(abs(internal.quantity), abs(broker.quantity), 1.0)
                drift = abs(internal.quantity - broker.quantity) / base * 100
                severity = "critical" if drift > self._max_drift_pct else "warning"
                discrepancies.append(Discrepancy(
                    symbol=symbol,
                    field="quantity",
                    internal_value=internal.quantity,
                    broker_value=broker.quantity,
                    drift_pct=round(drift, 2),
                    severity=severity,
                ))

            # Compare market value if available
            if internal.market_value > 0 and broker.market_value > 0:
                base = max(internal.market_value, broker.market_value, 1.0)
                drift = abs(internal.market_value - broker.market_value) / base * 100
                if drift > self._max_drift_pct:
                    discrepancies.append(Discrepancy(
                        symbol=symbol,
                        field="market_value",
                        internal_value=internal.market_value,
                        broker_value=broker.market_value,
                        drift_pct=round(drift, 2),
                        severity="warning",
                    ))

        if discrepancies:
            logger.warning(
                "reconciliation_discrepancies_found",
                count=len(discrepancies),
                critical=sum(1 for d in discrepancies if d.severity == "critical"),
            )
        else:
            logger.info("reconciliation_clean", symbols_checked=len(all_symbols))

        return discrepancies

    def max_drift(self, discrepancies: list[Discrepancy]) -> float:
        """Return the maximum drift percentage across all discrepancies."""
        if not discrepancies:
            return 0.0
        return max(d.drift_pct for d in discrepancies)

    def has_critical(self, discrepancies: list[Discrepancy]) -> bool:
        """Return True if any critical discrepancies exist."""
        return any(d.severity == "critical" for d in discrepancies)
