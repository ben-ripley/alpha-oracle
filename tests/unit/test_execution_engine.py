"""Tests for ExecutionEngine — order processing, risk handling, and approval workflows."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.core.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PortfolioSnapshot,
    RiskAction,
    RiskCheckResult,
    Signal,
    SignalDirection,
)
from src.execution.engine import ExecutionEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager with check_pre_trade and is_kill_switch_active."""
    risk = AsyncMock()
    risk.is_kill_switch_active = AsyncMock(return_value=False)
    risk.check_pre_trade = AsyncMock(return_value=RiskCheckResult(
        action=RiskAction.APPROVE,
        reasons=[],
    ))
    return risk


@pytest.fixture
def mock_order_generator():
    """Mock OrderGenerator that returns a test order."""
    gen = AsyncMock()
    gen.generate_order = lambda signal, portfolio: Order(
        id="test-order-123",
        symbol=signal.symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        limit_price=150.0,
        strategy_name=signal.strategy_name,
    )
    return gen


@pytest.fixture
def mock_tracker():
    """Mock ExecutionTracker."""
    return AsyncMock()


@pytest.fixture
def engine(mock_broker, mock_risk_manager, mock_order_generator, mock_tracker):
    """ExecutionEngine with all mocked dependencies."""
    return ExecutionEngine(
        broker=mock_broker,
        risk_manager=mock_risk_manager,
        order_generator=mock_order_generator,
        tracker=mock_tracker,
    )


@pytest.fixture
def long_signal() -> Signal:
    """Sample LONG signal for testing."""
    from datetime import datetime
    return Signal(
        symbol="AAPL",
        timestamp=datetime.utcnow(),
        direction=SignalDirection.LONG,
        strength=0.75,
        strategy_name="TestStrategy",
    )


@pytest.fixture
def flat_signal() -> Signal:
    """Sample FLAT signal for testing."""
    from datetime import datetime
    return Signal(
        symbol="AAPL",
        timestamp=datetime.utcnow(),
        direction=SignalDirection.FLAT,
        strength=0.0,
        strategy_name="TestStrategy",
    )


# ---------------------------------------------------------------------------
# TestProcessSignal
# ---------------------------------------------------------------------------

class TestProcessSignal:
    """Test signal processing through risk checks and submission."""

    @pytest.mark.asyncio
    async def test_flat_signal_is_skipped(self, engine, flat_signal):
        """FLAT signal returns None without processing."""
        result = await engine.process_signal(flat_signal)
        assert result is None

    @pytest.mark.asyncio
    async def test_kill_switch_active_blocks_signal(
        self, engine, long_signal, mock_risk_manager
    ):
        """Kill switch active blocks all signals."""
        mock_risk_manager.is_kill_switch_active = AsyncMock(return_value=True)
        result = await engine.process_signal(long_signal)
        assert result is None

    @pytest.mark.asyncio
    async def test_broker_failure_in_get_portfolio(
        self, engine, long_signal, mock_broker
    ):
        """Broker get_portfolio failure raises exception."""
        mock_broker.get_portfolio = AsyncMock(side_effect=Exception("Broker down"))
        with pytest.raises(Exception, match="Broker down"):
            await engine.process_signal(long_signal)

    @pytest.mark.asyncio
    async def test_order_generation_failure_returns_none(
        self, engine, long_signal, mock_order_generator
    ):
        """Order generation ValueError returns None."""
        mock_order_generator.generate_order = lambda s, p: (_ for _ in ()).throw(
            ValueError("Invalid signal")
        )
        result = await engine.process_signal(long_signal)
        assert result is None

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_successful_signal_approve_flow(
        self, mock_get_redis, engine, long_signal, mock_broker, mock_risk_manager
    ):
        """Successful signal -> order -> APPROVE -> submit."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_risk_manager.check_pre_trade = AsyncMock(return_value=RiskCheckResult(
            action=RiskAction.APPROVE,
            reasons=[],
        ))

        submitted_order = Order(
            id="test-order-123",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
            status=OrderStatus.SUBMITTED,
            broker_order_id="broker-123",
        )
        mock_broker.submit_order = AsyncMock(return_value=submitted_order)

        result = await engine.process_signal(long_signal)
        assert result is not None
        assert result.status == OrderStatus.SUBMITTED
        assert result.broker_order_id == "broker-123"
        mock_broker.submit_order.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_signal_with_reject_returns_none(
        self, mock_get_redis, engine, long_signal, mock_risk_manager
    ):
        """Signal with REJECT risk result returns None."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        mock_risk_manager.check_pre_trade = AsyncMock(return_value=RiskCheckResult(
            action=RiskAction.REJECT,
            reasons=["Position limit exceeded"],
        ))

        result = await engine.process_signal(long_signal)
        assert result is None


# ---------------------------------------------------------------------------
# TestHandleRiskAction
# ---------------------------------------------------------------------------

class TestHandleRiskAction:
    """Test risk action handling logic."""

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_approve_action_submits_order(self, mock_get_redis, engine, sample_portfolio):
        """APPROVE action submits order via broker."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
        )
        risk_result = RiskCheckResult(action=RiskAction.APPROVE, reasons=[])

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock()
        )
        assert result is not None
        engine._broker.submit_order.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_reject_action_logs_and_returns_none(
        self, mock_get_redis, engine, sample_portfolio
    ):
        """REJECT action logs rejection and returns None."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
        )
        risk_result = RiskCheckResult(
            action=RiskAction.REJECT,
            reasons=["Position limit exceeded"],
        )

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock()
        )
        assert result is None
        assert order.status == OrderStatus.REJECTED
        assert "rejection_reasons" in order.metadata

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_require_human_approval_queues_in_redis(
        self, mock_get_redis, engine, sample_portfolio
    ):
        """REQUIRE_HUMAN_APPROVAL queues order in Redis."""
        mock_redis = AsyncMock()
        mock_redis.hset = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
        )
        risk_result = RiskCheckResult(
            action=RiskAction.REQUIRE_HUMAN_APPROVAL,
            reasons=["Autonomy mode requires approval"],
        )

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock()
        )
        assert result is not None
        assert result.status == OrderStatus.PENDING
        mock_redis.hset.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_reduce_size_with_valid_adjusted_quantity_retries(
        self, mock_get_redis, engine, sample_portfolio, mock_risk_manager
    ):
        """REDUCE_SIZE with valid adjusted_quantity retries risk check."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=150.0,
        )
        risk_result = RiskCheckResult(
            action=RiskAction.REDUCE_SIZE,
            reasons=["Position limit requires size reduction"],
            adjusted_quantity=50,
        )

        # Second check approves
        mock_risk_manager.check_pre_trade = AsyncMock(return_value=RiskCheckResult(
            action=RiskAction.APPROVE,
            reasons=[],
        ))

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock()
        )
        assert result is not None
        assert result.quantity == 50
        mock_risk_manager.check_pre_trade.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_reduce_size_with_max_retries_rejects(
        self, mock_get_redis, engine, sample_portfolio
    ):
        """REDUCE_SIZE with max retries (3) rejects."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=150.0,
        )
        risk_result = RiskCheckResult(
            action=RiskAction.REDUCE_SIZE,
            reasons=["Position limit requires size reduction"],
            adjusted_quantity=50,
        )

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock(), reduce_attempts=3
        )
        assert result is None

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_reduce_size_with_no_valid_adjusted_quantity_rejects(
        self, mock_get_redis, engine, sample_portfolio
    ):
        """REDUCE_SIZE with no valid adjusted_quantity rejects."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=150.0,
        )
        risk_result = RiskCheckResult(
            action=RiskAction.REDUCE_SIZE,
            reasons=["Position limit requires size reduction"],
            adjusted_quantity=None,
        )

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock()
        )
        assert result is None
        assert order.status == OrderStatus.REJECTED

    @pytest.mark.asyncio
    async def test_unknown_action_returns_none(self, engine, sample_portfolio):
        """Unknown/unhandled action returns None."""
        order = Order(
            id="test-order",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
        )
        # Create a risk result with an invalid action (simulated)
        risk_result = RiskCheckResult(action=RiskAction.APPROVE, reasons=[])
        risk_result.action = "UNKNOWN_ACTION"  # Force invalid action

        result = await engine._handle_risk_action(
            order, sample_portfolio, risk_result, AsyncMock()
        )
        assert result is None


# ---------------------------------------------------------------------------
# TestPendingApprovals
# ---------------------------------------------------------------------------

class TestPendingApprovals:
    """Test pending order approval/rejection workflows."""

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_approve_pending_order_retrieves_and_submits(
        self, mock_get_redis, engine
    ):
        """approve_pending_order retrieves from Redis and submits."""
        order = Order(
            id="pending-order-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
            status=OrderStatus.PENDING,
        )

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=order.model_dump_json())
        mock_redis.hdel = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        result = await engine.approve_pending_order("pending-order-1")
        assert result is not None
        mock_redis.hdel.assert_called_once()
        engine._broker.submit_order.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_reject_pending_order_marks_rejected(
        self, mock_get_redis, engine
    ):
        """reject_pending_order marks REJECTED."""
        order = Order(
            id="pending-order-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
            status=OrderStatus.PENDING,
        )

        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=order.model_dump_json())
        mock_redis.hdel = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        await engine.reject_pending_order("pending-order-1", "User declined")
        mock_redis.hdel.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_missing_order_raises_value_error(self, mock_get_redis, engine):
        """Missing order raises ValueError."""
        mock_redis = AsyncMock()
        mock_redis.hget = AsyncMock(return_value=None)
        mock_get_redis.return_value = mock_redis

        with pytest.raises(ValueError, match="No pending order found"):
            await engine.approve_pending_order("nonexistent-order")


# ---------------------------------------------------------------------------
# TestCancelAll
# ---------------------------------------------------------------------------

class TestCancelAll:
    """Test cancel_all_orders functionality."""

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_clears_redis_pending_orders(self, mock_get_redis, engine):
        """Clears Redis pending orders, publishes cancel events, returns count."""
        order1 = Order(
            id="pending-1",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
            limit_price=150.0,
        )
        order2 = Order(
            id="pending-2",
            symbol="MSFT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=5,
            limit_price=420.0,
        )

        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={
            "pending-1": order1.model_dump_json(),
            "pending-2": order2.model_dump_json(),
        })
        mock_redis.delete = AsyncMock()
        mock_redis.publish = AsyncMock()
        mock_get_redis.return_value = mock_redis

        count = await engine.cancel_all_orders()
        assert count == 2
        mock_redis.delete.assert_called_once()
        assert mock_redis.publish.call_count == 2

    @pytest.mark.asyncio
    @patch("src.execution.engine.get_redis")
    async def test_empty_queue_returns_zero(self, mock_get_redis, engine):
        """Empty queue returns 0."""
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.delete = AsyncMock()
        mock_get_redis.return_value = mock_redis

        count = await engine.cancel_all_orders()
        assert count == 0
