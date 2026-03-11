"""Tests for Circuit Breakers — independent safety switches that halt trading.

Circuit breakers MUST:
- Trip when their specific conditions are met
- Persist state in Redis
- Return clear reasons for tripping
- Be conservative: trip when data is missing (for most breakers)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.models import PortfolioSnapshot
from src.risk.circuit_breaker import (
    REDIS_CB_PREFIX,
    CircuitBreakerManager,
    DailyLossBreaker,
    DeadManSwitchBreaker,
    DrawdownBreaker,
    ReconciliationBreaker,
    StaleDataBreaker,
    VIXBreaker,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Create a mock redis client for testing."""
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    return redis


def _make_portfolio(
    equity: float = 50000.0,
    max_drawdown_pct: float = 5.0,
    daily_pnl_pct: float = 0.0,
) -> PortfolioSnapshot:
    """Helper to create a portfolio snapshot."""
    return PortfolioSnapshot(
        total_equity=equity,
        cash=equity * 0.3,
        positions_value=equity * 0.7,
        positions=[],
        max_drawdown_pct=max_drawdown_pct,
        daily_pnl_pct=daily_pnl_pct,
    )


# ---------------------------------------------------------------------------
# TestVIXBreaker
# ---------------------------------------------------------------------------

class TestVIXBreaker:
    """Test VIX circuit breaker."""

    @pytest.mark.asyncio
    async def test_vix_above_threshold_trips(self):
        """VIX above threshold -> tripped."""
        breaker = VIXBreaker(threshold=35.0)
        context = {"vix_level": 40.0}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "40.0" in reason
        assert "35.0" in reason

    @pytest.mark.asyncio
    async def test_vix_below_threshold_not_tripped(self):
        """VIX below threshold -> not tripped."""
        breaker = VIXBreaker(threshold=35.0)
        context = {"vix_level": 20.0}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "20.0" in reason

    @pytest.mark.asyncio
    async def test_missing_vix_not_tripped(self):
        """Missing VIX data -> not tripped (conservative=False for VIX)."""
        breaker = VIXBreaker(threshold=35.0)
        context = {}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "unavailable" in reason.lower()


# ---------------------------------------------------------------------------
# TestStaleDataBreaker
# ---------------------------------------------------------------------------

class TestStaleDataBreaker:
    """Test stale data circuit breaker."""

    @pytest.mark.asyncio
    async def test_old_timestamp_trips(self):
        """Old timestamp -> tripped."""
        breaker = StaleDataBreaker(max_age_seconds=300)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        context = {"last_data_timestamp": old_time}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "600" in reason
        assert "300" in reason

    @pytest.mark.asyncio
    async def test_recent_timestamp_not_tripped(self):
        """Recent timestamp -> not tripped."""
        breaker = StaleDataBreaker(max_age_seconds=300)
        recent_time = datetime.now(timezone.utc)
        context = {"last_data_timestamp": recent_time}

        tripped, reason = await breaker.check(context)

        assert tripped is False

    @pytest.mark.asyncio
    async def test_missing_timestamp_trips(self):
        """Missing timestamp -> tripped (conservative)."""
        breaker = StaleDataBreaker(max_age_seconds=300)
        context = {}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "stale" in reason.lower()


# ---------------------------------------------------------------------------
# TestDrawdownBreaker
# ---------------------------------------------------------------------------

class TestDrawdownBreaker:
    """Test drawdown circuit breaker."""

    @pytest.mark.asyncio
    async def test_drawdown_exceeds_threshold_trips(self):
        """Drawdown exceeds threshold -> tripped."""
        breaker = DrawdownBreaker(threshold_pct=10.0)
        context = {"max_drawdown_pct": 12.0}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "12.0" in reason
        assert "10.0" in reason

    @pytest.mark.asyncio
    async def test_drawdown_within_threshold_not_tripped(self):
        """Drawdown within threshold -> not tripped."""
        breaker = DrawdownBreaker(threshold_pct=10.0)
        context = {"max_drawdown_pct": 5.0}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "5.0" in reason


# ---------------------------------------------------------------------------
# TestDailyLossBreaker
# ---------------------------------------------------------------------------

class TestDailyLossBreaker:
    """Test daily loss circuit breaker."""

    @pytest.mark.asyncio
    async def test_daily_loss_exceeds_threshold_trips(self):
        """Daily loss exceeds threshold -> tripped."""
        breaker = DailyLossBreaker(threshold_pct=3.0)
        context = {"daily_pnl_pct": -5.0}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "-5.0" in reason
        assert "3.0" in reason

    @pytest.mark.asyncio
    async def test_daily_loss_within_threshold_not_tripped(self):
        """Daily loss within threshold -> not tripped."""
        breaker = DailyLossBreaker(threshold_pct=3.0)
        context = {"daily_pnl_pct": -1.0}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "-1.0" in reason


# ---------------------------------------------------------------------------
# TestReconciliationBreaker
# ---------------------------------------------------------------------------

class TestReconciliationBreaker:
    """Test reconciliation circuit breaker."""

    @pytest.mark.asyncio
    async def test_drift_exceeds_threshold_trips(self):
        """Drift exceeds threshold -> tripped."""
        breaker = ReconciliationBreaker(max_drift_pct=1.0)
        context = {"reconciliation_drift_pct": 2.5}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "2.5" in reason
        assert "1.0" in reason

    @pytest.mark.asyncio
    async def test_drift_within_threshold_not_tripped(self):
        """Drift within threshold -> not tripped."""
        breaker = ReconciliationBreaker(max_drift_pct=1.0)
        context = {"reconciliation_drift_pct": 0.5}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "0.5" in reason

    @pytest.mark.asyncio
    async def test_missing_drift_not_tripped(self):
        """Missing drift data -> not tripped."""
        breaker = ReconciliationBreaker(max_drift_pct=1.0)
        context = {}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "No reconciliation" in reason


# ---------------------------------------------------------------------------
# TestDeadManSwitchBreaker
# ---------------------------------------------------------------------------

class TestDeadManSwitchBreaker:
    """Test dead man's switch circuit breaker."""

    @pytest.mark.asyncio
    async def test_no_heartbeat_trips(self):
        """No heartbeat -> tripped."""
        breaker = DeadManSwitchBreaker(max_hours=48)
        context = {}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "No operator heartbeat" in reason

    @pytest.mark.asyncio
    async def test_old_heartbeat_trips(self):
        """Old heartbeat (72h ago, max=48h) -> tripped."""
        breaker = DeadManSwitchBreaker(max_hours=48)
        old_heartbeat = datetime.now(timezone.utc) - timedelta(hours=72)
        context = {"last_operator_heartbeat": old_heartbeat}

        tripped, reason = await breaker.check(context)

        assert tripped is True
        assert "72" in reason
        assert "48" in reason

    @pytest.mark.asyncio
    async def test_recent_heartbeat_not_tripped(self):
        """Recent heartbeat (1h ago) -> not tripped."""
        breaker = DeadManSwitchBreaker(max_hours=48)
        recent_heartbeat = datetime.now(timezone.utc) - timedelta(hours=1)
        context = {"last_operator_heartbeat": recent_heartbeat}

        tripped, reason = await breaker.check(context)

        assert tripped is False
        assert "1" in reason


# ---------------------------------------------------------------------------
# TestCircuitBreakerManager
# ---------------------------------------------------------------------------

class TestCircuitBreakerManager:
    """Test circuit breaker manager."""

    @pytest.mark.asyncio
    @patch("src.risk.circuit_breaker.get_settings")
    async def test_check_all_runs_all_breakers(self, mock_settings, mock_redis):
        """check_all runs all breakers and persists results in Redis."""
        # Mock settings
        mock_settings.return_value.risk.circuit_breakers.vix_threshold = 35.0
        mock_settings.return_value.risk.circuit_breakers.stale_data_seconds = 300
        mock_settings.return_value.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
        mock_settings.return_value.risk.circuit_breakers.dead_man_switch_hours = 48
        mock_settings.return_value.risk.portfolio_limits.max_drawdown_pct = 10.0
        mock_settings.return_value.risk.portfolio_limits.max_daily_loss_pct = 3.0

        manager = CircuitBreakerManager(redis_client=mock_redis)

        # Build context that trips VIX breaker
        context = {
            "vix_level": 40.0,
            "last_data_timestamp": datetime.now(timezone.utc),
            "max_drawdown_pct": 5.0,
            "daily_pnl_pct": -1.0,
            "reconciliation_drift_pct": 0.5,
            "last_operator_heartbeat": datetime.now(timezone.utc),
        }

        results = await manager.check_all(context)

        # Should have results for all 6 breakers
        assert len(results) == 6

        # Verify Redis state was persisted for each breaker
        assert mock_redis.set.call_count == 6

        # Check that VIX breaker tripped
        vix_result = [r for r in results if r[0] == "vix"][0]
        assert vix_result[1] is True  # tripped

    @pytest.mark.asyncio
    @patch("src.risk.circuit_breaker.get_settings")
    async def test_is_any_tripped_returns_true_when_one_trips(self, mock_settings, mock_redis):
        """is_any_tripped returns True when at least one breaker trips."""
        mock_settings.return_value.risk.circuit_breakers.vix_threshold = 35.0
        mock_settings.return_value.risk.circuit_breakers.stale_data_seconds = 300
        mock_settings.return_value.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
        mock_settings.return_value.risk.circuit_breakers.dead_man_switch_hours = 48
        mock_settings.return_value.risk.portfolio_limits.max_drawdown_pct = 10.0
        mock_settings.return_value.risk.portfolio_limits.max_daily_loss_pct = 3.0

        manager = CircuitBreakerManager(redis_client=mock_redis)

        # Context with VIX above threshold
        context = {
            "vix_level": 40.0,
            "last_data_timestamp": datetime.now(timezone.utc),
            "max_drawdown_pct": 5.0,
            "daily_pnl_pct": -1.0,
            "last_operator_heartbeat": datetime.now(timezone.utc),
        }

        result = await manager.is_any_tripped(context)

        assert result is True

    @pytest.mark.asyncio
    @patch("src.risk.circuit_breaker.get_settings")
    async def test_is_any_tripped_returns_false_when_none_trip(self, mock_settings, mock_redis):
        """is_any_tripped returns False when none trip."""
        mock_settings.return_value.risk.circuit_breakers.vix_threshold = 35.0
        mock_settings.return_value.risk.circuit_breakers.stale_data_seconds = 300
        mock_settings.return_value.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
        mock_settings.return_value.risk.circuit_breakers.dead_man_switch_hours = 48
        mock_settings.return_value.risk.portfolio_limits.max_drawdown_pct = 10.0
        mock_settings.return_value.risk.portfolio_limits.max_daily_loss_pct = 3.0

        manager = CircuitBreakerManager(redis_client=mock_redis)

        # Context with all breakers happy
        context = {
            "vix_level": 20.0,
            "last_data_timestamp": datetime.now(timezone.utc),
            "max_drawdown_pct": 5.0,
            "daily_pnl_pct": 1.0,
            "reconciliation_drift_pct": 0.5,
            "last_operator_heartbeat": datetime.now(timezone.utc),
        }

        result = await manager.is_any_tripped(context)

        assert result is False

    @pytest.mark.asyncio
    @patch("src.risk.circuit_breaker.get_settings")
    async def test_get_states_returns_redis_state(self, mock_settings, mock_redis):
        """get_states returns state from Redis for each breaker."""
        mock_settings.return_value.risk.circuit_breakers.vix_threshold = 35.0
        mock_settings.return_value.risk.circuit_breakers.stale_data_seconds = 300
        mock_settings.return_value.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
        mock_settings.return_value.risk.circuit_breakers.dead_man_switch_hours = 48
        mock_settings.return_value.risk.portfolio_limits.max_drawdown_pct = 10.0
        mock_settings.return_value.risk.portfolio_limits.max_daily_loss_pct = 3.0

        # Mock Redis to return state for VIX breaker
        def mock_get(key):
            if key == f"{REDIS_CB_PREFIX}vix":
                return json.dumps({
                    "tripped": True,
                    "reason": "VIX at 40.0",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                })
            return None

        mock_redis.get = AsyncMock(side_effect=mock_get)

        manager = CircuitBreakerManager(redis_client=mock_redis)
        states = await manager.get_states()

        # Should have states for all 6 breakers
        assert len(states) == 6
        assert "vix" in states
        assert states["vix"]["tripped"] is True
        assert "VIX at 40.0" in states["vix"]["reason"]

    @pytest.mark.asyncio
    @patch("src.risk.circuit_breaker.get_settings")
    async def test_build_context_maps_portfolio_fields(self, mock_settings):
        """build_context maps portfolio fields correctly."""
        mock_settings.return_value.risk.circuit_breakers.vix_threshold = 35.0
        mock_settings.return_value.risk.circuit_breakers.stale_data_seconds = 300
        mock_settings.return_value.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
        mock_settings.return_value.risk.circuit_breakers.dead_man_switch_hours = 48
        mock_settings.return_value.risk.portfolio_limits.max_drawdown_pct = 10.0
        mock_settings.return_value.risk.portfolio_limits.max_daily_loss_pct = 3.0

        manager = CircuitBreakerManager(redis_client=AsyncMock())

        portfolio = _make_portfolio(
            equity=50000.0,
            max_drawdown_pct=7.5,
            daily_pnl_pct=-2.0,
        )
        vix_level = 25.0
        last_data_ts = datetime.now(timezone.utc)
        last_heartbeat = datetime.now(timezone.utc) - timedelta(hours=10)
        drift = 0.8

        context = manager.build_context(
            portfolio=portfolio,
            vix_level=vix_level,
            last_data_timestamp=last_data_ts,
            last_operator_heartbeat=last_heartbeat,
            reconciliation_drift_pct=drift,
        )

        assert context["max_drawdown_pct"] == 7.5
        assert context["daily_pnl_pct"] == -2.0
        assert context["vix_level"] == 25.0
        assert context["last_data_timestamp"] == last_data_ts
        assert context["last_operator_heartbeat"] == last_heartbeat
        assert context["reconciliation_drift_pct"] == 0.8

    @pytest.mark.asyncio
    @patch("src.risk.circuit_breaker.get_settings")
    async def test_record_heartbeat_writes_timestamp(self, mock_settings, mock_redis):
        """record_heartbeat writes timestamp to Redis."""
        mock_settings.return_value.risk.circuit_breakers.vix_threshold = 35.0
        mock_settings.return_value.risk.circuit_breakers.stale_data_seconds = 300
        mock_settings.return_value.risk.circuit_breakers.max_reconciliation_drift_pct = 1.0
        mock_settings.return_value.risk.circuit_breakers.dead_man_switch_hours = 48
        mock_settings.return_value.risk.portfolio_limits.max_drawdown_pct = 10.0
        mock_settings.return_value.risk.portfolio_limits.max_daily_loss_pct = 3.0

        manager = CircuitBreakerManager(redis_client=mock_redis)
        await manager.record_heartbeat()

        # Verify Redis set was called
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == f"{REDIS_CB_PREFIX}heartbeat"

        # Verify timestamp is ISO format
        timestamp = call_args[0][1]
        datetime.fromisoformat(timestamp)  # Should not raise
