"""Tests for the Kill Switch — emergency halt of all trading activity.

The kill switch MUST:
- Persist active/inactive state in Redis
- Cancel all open orders when activated (if broker available)
- Respect cooldown period before allowing deactivation
- Log all activation/deactivation events for audit trail
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.models import Order, OrderSide, OrderType
from src.risk.kill_switch import REDIS_KS_KEY, REDIS_KS_LOG_KEY, KillSwitch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """Create a mock redis client for testing."""
    redis = AsyncMock()
    redis.set = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.rpush = AsyncMock()
    redis.lrange = AsyncMock(return_value=[])
    return redis


@pytest.fixture
def mock_broker():
    """Create a mock broker adapter."""
    broker = AsyncMock()
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_open_orders = AsyncMock(return_value=[])
    broker.cancel_order = AsyncMock()
    return broker


def _make_order(symbol: str, broker_order_id: str) -> Order:
    """Helper to create an order with broker_order_id."""
    return Order(
        id=f"test-{symbol}",
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        limit_price=100.0,
        broker_order_id=broker_order_id,
    )


# ---------------------------------------------------------------------------
# TestActivation
# ---------------------------------------------------------------------------

class TestActivation:
    """Test kill switch activation."""

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_sets_redis_state(self, mock_settings, mock_redis):
        """Activation sets Redis state with active=True."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)

        await ks.activate("Test reason")

        # Verify Redis state was set
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == REDIS_KS_KEY

        # Parse the state
        state_json = call_args[0][1]
        state = json.loads(state_json)
        assert state["active"] is True
        assert state["reason"] == "Test reason"
        assert "activated_at" in state

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_appends_audit_log(self, mock_settings, mock_redis):
        """Activation appends an entry to the audit log."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)

        await ks.activate("Audit test")

        # Verify audit log was written
        mock_redis.rpush.assert_called_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == REDIS_KS_LOG_KEY

        # Parse log entry
        log_entry = json.loads(call_args[0][1])
        assert log_entry["action"] == "activate"
        assert log_entry["reason"] == "Audit test"
        assert "timestamp" in log_entry

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_cancels_open_orders(self, mock_settings, mock_redis, mock_broker):
        """Activation cancels all open orders via broker."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60

        # Mock open orders
        orders = [
            _make_order("AAPL", "broker-123"),
            _make_order("MSFT", "broker-456"),
        ]
        mock_broker.get_open_orders = AsyncMock(return_value=orders)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=mock_broker)
        await ks.activate("Cancel all orders")

        # Verify broker methods were called
        mock_broker.get_open_orders.assert_called_once()
        assert mock_broker.cancel_order.call_count == 2
        mock_broker.cancel_order.assert_any_call("broker-123")
        mock_broker.cancel_order.assert_any_call("broker-456")

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_cancel_failure_doesnt_raise(self, mock_settings, mock_redis, mock_broker):
        """Cancel order failure doesn't prevent activation from completing."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60

        orders = [_make_order("AAPL", "broker-123")]
        mock_broker.get_open_orders = AsyncMock(return_value=orders)
        mock_broker.cancel_order = AsyncMock(side_effect=Exception("Broker error"))

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=mock_broker)

        # Should not raise despite broker error
        await ks.activate("Test error handling")

        # Verify state was still set
        mock_redis.set.assert_called()

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_activate_without_broker(self, mock_settings, mock_redis):
        """Activation without broker_adapter still works (just Redis state)."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)

        await ks.activate("No broker test")

        # Verify Redis state was set despite no broker
        mock_redis.set.assert_called_once()
        state_json = mock_redis.set.call_args[0][1]
        state = json.loads(state_json)
        assert state["active"] is True


# ---------------------------------------------------------------------------
# TestDeactivation
# ---------------------------------------------------------------------------

class TestDeactivation:
    """Test kill switch deactivation."""

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_deactivate_when_not_active(self, mock_settings, mock_redis):
        """Deactivate when not active (no key in Redis) succeeds."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        mock_redis.get = AsyncMock(return_value=None)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        await ks.deactivate()

        # Should set state to inactive
        mock_redis.set.assert_called()
        state_json = mock_redis.set.call_args[0][1]
        state = json.loads(state_json)
        assert state["active"] is False

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_deactivate_within_cooldown_raises(self, mock_settings, mock_redis):
        """Deactivate within cooldown raises ValueError."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60

        # Activated 5 minutes ago (within 60 minute cooldown)
        activated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        state = json.dumps({
            "active": True,
            "reason": "Test",
            "activated_at": activated_at.isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=state)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)

        with pytest.raises(ValueError, match="cooldown active"):
            await ks.deactivate()

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_deactivate_after_cooldown_succeeds(self, mock_settings, mock_redis):
        """Deactivate after cooldown succeeds."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60

        # Activated 120 minutes ago (after 60 minute cooldown)
        activated_at = datetime.now(timezone.utc) - timedelta(minutes=120)
        state = json.dumps({
            "active": True,
            "reason": "Test",
            "activated_at": activated_at.isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=state)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        await ks.deactivate()

        # Should successfully deactivate
        mock_redis.set.assert_called()
        state_json = mock_redis.set.call_args[0][1]
        new_state = json.loads(state_json)
        assert new_state["active"] is False

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_audit_log_on_deactivate(self, mock_settings, mock_redis):
        """Audit log entry written on deactivate."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60

        # Set up prior activation (beyond cooldown)
        activated_at = datetime.now(timezone.utc) - timedelta(minutes=120)
        state = json.dumps({
            "active": True,
            "reason": "Test",
            "activated_at": activated_at.isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=state)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        await ks.deactivate()

        # Verify audit log entry
        mock_redis.rpush.assert_called_once()
        call_args = mock_redis.rpush.call_args
        assert call_args[0][0] == REDIS_KS_LOG_KEY

        log_entry = json.loads(call_args[0][1])
        assert log_entry["action"] == "deactivate"
        assert "timestamp" in log_entry


# ---------------------------------------------------------------------------
# TestIsActive
# ---------------------------------------------------------------------------

class TestIsActive:
    """Test checking if kill switch is active."""

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_no_key_returns_false(self, mock_settings, mock_redis):
        """No key in Redis returns False."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        mock_redis.get = AsyncMock(return_value=None)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        result = await ks.is_active()

        assert result is False

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_active_true_returns_true(self, mock_settings, mock_redis):
        """Key with active=True returns True."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        state = json.dumps({"active": True, "reason": "Test"})
        mock_redis.get = AsyncMock(return_value=state)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        result = await ks.is_active()

        assert result is True

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_active_false_returns_false(self, mock_settings, mock_redis):
        """Key with active=False returns False."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        state = json.dumps({"active": False})
        mock_redis.get = AsyncMock(return_value=state)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        result = await ks.is_active()

        assert result is False


# ---------------------------------------------------------------------------
# TestStatus
# ---------------------------------------------------------------------------

class TestStatus:
    """Test getting kill switch status."""

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_no_key_returns_default_dict(self, mock_settings, mock_redis):
        """No key returns default dict with active=False."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        mock_redis.get = AsyncMock(return_value=None)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        status = await ks.get_status()

        assert status == {"active": False, "reason": None, "activated_at": None}

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_with_key_returns_stored_dict(self, mock_settings, mock_redis):
        """With key returns the stored dict."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60
        stored_state = {
            "active": True,
            "reason": "Emergency shutdown",
            "activated_at": "2024-03-11T10:00:00Z",
        }
        mock_redis.get = AsyncMock(return_value=json.dumps(stored_state))

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        status = await ks.get_status()

        assert status == stored_state


# ---------------------------------------------------------------------------
# TestAuditLog
# ---------------------------------------------------------------------------

class TestAuditLog:
    """Test audit log retrieval."""

    @pytest.mark.asyncio
    @patch("src.risk.kill_switch.get_settings")
    async def test_get_audit_log_returns_parsed_entries(self, mock_settings, mock_redis):
        """get_audit_log returns parsed JSON entries, respects limit."""
        mock_settings.return_value.risk.kill_switch.cooldown_minutes = 60

        # Mock log entries
        entries = [
            json.dumps({"action": "activate", "reason": "Test 1", "timestamp": "2024-03-11T10:00:00Z"}),
            json.dumps({"action": "deactivate", "timestamp": "2024-03-11T11:00:00Z"}),
            json.dumps({"action": "activate", "reason": "Test 2", "timestamp": "2024-03-11T12:00:00Z"}),
        ]
        mock_redis.lrange = AsyncMock(return_value=entries)

        ks = KillSwitch(redis_client=mock_redis, broker_adapter=None)
        result = await ks.get_audit_log(limit=10)

        # Verify lrange called with correct params
        mock_redis.lrange.assert_called_once_with(REDIS_KS_LOG_KEY, -10, -1)

        # Verify entries were parsed
        assert len(result) == 3
        assert result[0]["action"] == "activate"
        assert result[0]["reason"] == "Test 1"
        assert result[1]["action"] == "deactivate"
        assert result[2]["action"] == "activate"
        assert result[2]["reason"] == "Test 2"
