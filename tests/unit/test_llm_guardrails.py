"""Tests for LLMGuardrailsEngine — guardrail verification."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(redis_value: str | None = None):
    """Create LLMGuardrailsEngine with a mocked Redis client."""
    with patch("src.risk.llm_guardrails.redis") as mock_redis_module:
        mock_client = MagicMock()
        mock_client.get.return_value = redis_value
        mock_redis_module.from_url.return_value = mock_client
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
    return engine


# ---------------------------------------------------------------------------
# verify_guardrails
# ---------------------------------------------------------------------------

class TestVerifyGuardrails:
    def test_verify_returns_true(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        with patch.object(engine, "_store_verification_timestamp"):
            result = engine.verify_guardrails()
        assert result is True

    def test_verify_stores_timestamp(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        stored = []
        with patch.object(engine, "_store_verification_timestamp", side_effect=lambda: stored.append(True)):
            engine.verify_guardrails()
        assert len(stored) == 1

    def test_verify_checks_no_broker_import(self):
        """Guardrail check should verify agents module doesn't import broker at top level."""
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        with patch.object(engine, "_store_verification_timestamp"):
            result = engine.verify_guardrails()
        # If the check passes (no direct broker import at module level), returns True
        assert result is True


# ---------------------------------------------------------------------------
# is_recently_verified
# ---------------------------------------------------------------------------

class TestIsRecentlyVerified:
    def test_not_verified_if_no_redis_key(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        with patch.object(engine, "_get_last_verified_timestamp", return_value=None):
            assert engine.is_recently_verified() is False

    def test_recently_verified_within_24h(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        recent = datetime.now(timezone.utc) - timedelta(hours=2)
        with patch.object(engine, "_get_last_verified_timestamp", return_value=recent):
            assert engine.is_recently_verified(max_age_hours=24) is True

    def test_not_recently_verified_older_than_24h(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        with patch.object(engine, "_get_last_verified_timestamp", return_value=old):
            assert engine.is_recently_verified(max_age_hours=24) is False

    def test_exactly_at_boundary_is_not_recent(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        boundary = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        with patch.object(engine, "_get_last_verified_timestamp", return_value=boundary):
            assert engine.is_recently_verified(max_age_hours=24) is False

    def test_custom_max_age_hours(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        with patch.object(engine, "_get_last_verified_timestamp", return_value=two_hours_ago):
            assert engine.is_recently_verified(max_age_hours=1) is False
            assert engine.is_recently_verified(max_age_hours=3) is True


# ---------------------------------------------------------------------------
# Store and retrieve timestamp (Redis integration tests via mocks)
# ---------------------------------------------------------------------------

class TestRedisIntegration:
    def test_store_verification_timestamp_sets_redis_key(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        mock_client = MagicMock()
        with patch.object(engine, "_get_redis_client", return_value=mock_client):
            engine._store_verification_timestamp()
        mock_client.set.assert_called_once()
        call_args = mock_client.set.call_args
        assert call_args[0][0] == "risk:guardrails:last_verified"

    def test_get_last_verified_timestamp_reads_redis(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        now_str = datetime.now(timezone.utc).isoformat()
        mock_client = MagicMock()
        mock_client.get.return_value = now_str
        with patch.object(engine, "_get_redis_client", return_value=mock_client):
            ts = engine._get_last_verified_timestamp()
        assert ts is not None
        mock_client.get.assert_called_once_with("risk:guardrails:last_verified")

    def test_get_last_verified_returns_none_when_key_missing(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        mock_client = MagicMock()
        mock_client.get.return_value = None
        with patch.object(engine, "_get_redis_client", return_value=mock_client):
            ts = engine._get_last_verified_timestamp()
        assert ts is None


# ---------------------------------------------------------------------------
# Broker access check
# ---------------------------------------------------------------------------

class TestBrokerAccessCheck:
    def test_agents_do_not_import_broker_at_module_level(self):
        """Agents module should NOT have a top-level import of BrokerAdapter."""
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        # This just verifies the check runs without error
        result = engine._check_no_broker_module_import()
        assert isinstance(result, bool)

    def test_guardrail_check_passes_for_clean_agents(self):
        """If agents don't expose broker, check should pass."""
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        result = engine._check_no_broker_module_import()
        assert result is True


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_get_status_returns_dict(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        with patch.object(engine, "is_recently_verified", return_value=True):
            status = engine.get_status()
        assert isinstance(status, dict)

    def test_get_status_has_required_keys(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        with patch.object(engine, "is_recently_verified", return_value=False):
            status = engine.get_status()
        assert "recently_verified" in status
        assert "last_verified" in status

    def test_get_status_reflects_verified_state(self):
        from src.risk.llm_guardrails import LLMGuardrailsEngine
        engine = LLMGuardrailsEngine()
        with patch.object(engine, "is_recently_verified", return_value=True):
            status = engine.get_status()
        assert status["recently_verified"] is True
