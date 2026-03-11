"""Tests for ReconciliationEngine: compares internal vs broker positions."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.core.models import Position
from src.risk.reconciliation import Discrepancy, ReconciliationEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_settings():
    """Mock settings with reconciliation drift limit."""
    settings = MagicMock()
    settings.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
    return settings


@pytest.fixture
def engine(mock_settings):
    """ReconciliationEngine instance with mocked settings."""
    with patch("src.risk.reconciliation.get_settings", return_value=mock_settings):
        return ReconciliationEngine()


def _make_position(
    symbol: str,
    quantity: float,
    market_value: float = 0.0,
    avg_entry_price: float = 100.0,
) -> Position:
    """Helper to create Position for testing."""
    if market_value == 0.0:
        market_value = quantity * avg_entry_price

    return Position(
        symbol=symbol,
        quantity=quantity,
        avg_entry_price=avg_entry_price,
        current_price=avg_entry_price,
        market_value=market_value,
        unrealized_pnl=0.0,
        unrealized_pnl_pct=0.0,
        entry_date=datetime.utcnow() - timedelta(days=3),
        strategy_name="TestStrategy",
    )


# ---------------------------------------------------------------------------
# TestReconcile
# ---------------------------------------------------------------------------

class TestReconcile:
    """Test the reconcile method."""

    def test_identical_positions_empty_list(self, engine):
        """Should return empty list when positions are identical."""
        internal = [_make_position("AAPL", 10), _make_position("MSFT", 5)]
        broker = [_make_position("AAPL", 10), _make_position("MSFT", 5)]

        discrepancies = engine.reconcile(internal, broker)

        assert len(discrepancies) == 0

    def test_broker_has_extra_position_critical(self, engine):
        """Should report critical discrepancy when broker has extra position."""
        internal = [_make_position("AAPL", 10)]
        broker = [_make_position("AAPL", 10), _make_position("TSLA", 5)]

        discrepancies = engine.reconcile(internal, broker)

        assert len(discrepancies) == 1
        assert discrepancies[0].symbol == "TSLA"
        assert discrepancies[0].field == "position"
        assert discrepancies[0].severity == "critical"
        assert discrepancies[0].internal_value == 0.0
        assert discrepancies[0].broker_value == 5.0
        assert discrepancies[0].drift_pct == 100.0

    def test_internal_has_extra_position_critical(self, engine):
        """Should report critical discrepancy when internal has extra position."""
        internal = [_make_position("AAPL", 10), _make_position("GOOG", 8)]
        broker = [_make_position("AAPL", 10)]

        discrepancies = engine.reconcile(internal, broker)

        assert len(discrepancies) == 1
        assert discrepancies[0].symbol == "GOOG"
        assert discrepancies[0].field == "position"
        assert discrepancies[0].severity == "critical"
        assert discrepancies[0].internal_value == 8.0
        assert discrepancies[0].broker_value == 0.0
        assert discrepancies[0].drift_pct == 100.0

    def test_quantity_mismatch_severity_based_on_drift(self, engine):
        """Should set severity based on drift pct (>max_drift_pct = critical)."""
        # max_drift_pct = 1.0
        # Mismatch: internal=10, broker=10.05 -> drift ~0.5% -> warning
        internal = [_make_position("AAPL", 10.0)]
        broker = [_make_position("AAPL", 10.05)]

        discrepancies = engine.reconcile(internal, broker)

        assert len(discrepancies) == 1
        assert discrepancies[0].symbol == "AAPL"
        assert discrepancies[0].field == "quantity"
        assert discrepancies[0].severity == "warning"
        assert discrepancies[0].drift_pct < 1.0

        # Now test critical case: internal=10, broker=11 -> drift ~9.1% -> critical
        internal = [_make_position("AAPL", 10.0)]
        broker = [_make_position("AAPL", 11.0)]

        discrepancies = engine.reconcile(internal, broker)

        # Will have both quantity and market_value discrepancies
        assert len(discrepancies) >= 1
        quantity_disc = [d for d in discrepancies if d.field == "quantity"][0]
        assert quantity_disc.severity == "critical"
        assert quantity_disc.drift_pct > 1.0

    def test_market_value_mismatch_warning(self, engine):
        """Should report warning for market value mismatch exceeding drift."""
        # Same quantity, but different market values (>1% drift)
        internal = [_make_position("MSFT", 10, market_value=4200.0)]
        broker = [_make_position("MSFT", 10, market_value=4300.0)]  # ~2.3% drift

        discrepancies = engine.reconcile(internal, broker)

        # Should have market_value discrepancy
        market_value_discrepancy = [d for d in discrepancies if d.field == "market_value"]
        assert len(market_value_discrepancy) == 1
        assert market_value_discrepancy[0].severity == "warning"
        assert market_value_discrepancy[0].drift_pct > 1.0

    def test_mixed_symbols_with_various_mismatches(self, engine):
        """Should handle multiple symbols with different types of mismatches."""
        internal = [
            _make_position("AAPL", 10),
            _make_position("MSFT", 5),
            _make_position("GOOG", 8),
        ]
        broker = [
            _make_position("AAPL", 10),  # Matches perfectly
            _make_position("MSFT", 6),   # Quantity mismatch
            _make_position("TSLA", 3),   # Extra in broker
        ]

        discrepancies = engine.reconcile(internal, broker)

        # Should have:
        # 1. MSFT quantity mismatch (also market_value mismatch)
        # 2. GOOG missing in broker
        # 3. TSLA extra in broker
        # Total: 4 discrepancies (MSFT has 2)
        assert len(discrepancies) >= 3

        symbols = {d.symbol for d in discrepancies}
        assert symbols == {"MSFT", "GOOG", "TSLA"}

        # Verify we have the expected types
        assert any(d.symbol == "MSFT" and d.field == "quantity" for d in discrepancies)
        assert any(d.symbol == "GOOG" and d.field == "position" for d in discrepancies)
        assert any(d.symbol == "TSLA" and d.field == "position" for d in discrepancies)

    def test_both_empty_lists_empty_result(self, engine):
        """Should return empty list when both position lists are empty."""
        internal = []
        broker = []

        discrepancies = engine.reconcile(internal, broker)

        assert len(discrepancies) == 0


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------

class TestHelpers:
    """Test helper methods: max_drift and has_critical."""

    def test_max_drift_returns_highest(self, engine):
        """Should return highest drift_pct from list."""
        discrepancies = [
            Discrepancy("AAPL", "quantity", 10, 10.5, 4.76, "warning"),
            Discrepancy("MSFT", "quantity", 5, 5.2, 3.85, "warning"),
            Discrepancy("GOOG", "quantity", 8, 10, 20.0, "critical"),
        ]

        max_drift = engine.max_drift(discrepancies)

        assert max_drift == 20.0

    def test_empty_list_returns_zero(self, engine):
        """Should return 0.0 for empty list."""
        discrepancies = []

        max_drift = engine.max_drift(discrepancies)

        assert max_drift == 0.0

    def test_has_critical_returns_true(self, engine):
        """Should return True when any severity is 'critical'."""
        discrepancies = [
            Discrepancy("AAPL", "quantity", 10, 10.5, 4.76, "warning"),
            Discrepancy("MSFT", "quantity", 5, 10, 50.0, "critical"),
        ]

        result = engine.has_critical(discrepancies)

        assert result is True

    def test_has_critical_returns_false(self, engine):
        """Should return False when no critical discrepancies."""
        discrepancies = [
            Discrepancy("AAPL", "quantity", 10, 10.5, 4.76, "warning"),
            Discrepancy("MSFT", "quantity", 5, 5.2, 3.85, "warning"),
        ]

        result = engine.has_critical(discrepancies)

        assert result is False
