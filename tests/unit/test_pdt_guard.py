"""Tests for the PDT (Pattern Day Trader) Guard — the most critical safety component.

The PDT guard MUST:
- Block day trade #4 when under $25K equity
- Allow trades when at/above $25K
- Correctly identify what constitutes a day trade
- Track day trades in a rolling 5 business day window
- Be conservative: reject when in doubt
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.core.config import PDTGuard as PDTGuardConfig
from src.core.models import (
    Order,
    OrderSide,
    OrderType,
    PortfolioSnapshot,
    Position,
    RiskAction,
)
from src.risk.pdt_guard import PDTGuardImpl, _business_days_ago

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_portfolio(equity: float, positions: list[Position] | None = None) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        total_equity=equity,
        cash=equity - sum(p.market_value for p in (positions or [])),
        positions_value=sum(p.market_value for p in (positions or [])),
        positions=positions or [],
    )


def _make_sell_order(symbol: str) -> Order:
    return Order(
        id="test-sell",
        symbol=symbol,
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=10,
        limit_price=180.0,
    )


def _make_buy_order(symbol: str) -> Order:
    return Order(
        id="test-buy",
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10,
        limit_price=180.0,
    )


def _make_position_opened_today(symbol: str) -> Position:
    return Position(
        symbol=symbol,
        quantity=10,
        avg_entry_price=178.0,
        current_price=180.0,
        market_value=1800.0,
        unrealized_pnl=20.0,
        unrealized_pnl_pct=1.12,
        entry_date=datetime.combine(date.today(), datetime.min.time()),
    )


def _make_position_opened_days_ago(symbol: str, days: int) -> Position:
    return Position(
        symbol=symbol,
        quantity=10,
        avg_entry_price=178.0,
        current_price=180.0,
        market_value=1800.0,
        unrealized_pnl=20.0,
        unrealized_pnl_pct=1.12,
        entry_date=datetime.now() - timedelta(days=days),
    )


# ---------------------------------------------------------------------------
# Tests for _business_days_ago helper
# ---------------------------------------------------------------------------

class TestBusinessDaysAgo:
    def test_zero_days(self):
        result = _business_days_ago(0, date(2024, 3, 13))  # Wednesday
        assert result == date(2024, 3, 13)

    def test_one_business_day(self):
        # Wednesday -> Tuesday
        result = _business_days_ago(1, date(2024, 3, 13))
        assert result == date(2024, 3, 12)

    def test_skips_weekend(self):
        # Monday -> previous Friday (skips Sat+Sun)
        result = _business_days_ago(1, date(2024, 3, 11))
        assert result == date(2024, 3, 8)

    def test_five_business_days(self):
        # Wednesday Mar 13 -> 5 biz days back = Wednesday Mar 6
        result = _business_days_ago(5, date(2024, 3, 13))
        assert result == date(2024, 3, 6)

    def test_five_business_days_from_monday(self):
        # Monday Mar 11 -> 5 biz days back = Monday Mar 4
        result = _business_days_ago(5, date(2024, 3, 11))
        assert result == date(2024, 3, 4)


# ---------------------------------------------------------------------------
# Tests for PDT Guard
# ---------------------------------------------------------------------------

@pytest.fixture
def pdt_config():
    return PDTGuardConfig(
        enabled=True,
        max_day_trades=3,
        rolling_window_days=5,
        account_threshold=25000.0,
    )


@pytest.fixture
def mock_redis():
    """Create a mock redis client for testing."""
    redis = AsyncMock()
    redis.zadd = AsyncMock()
    redis.zremrangebyscore = AsyncMock()
    redis.zrangebyscore = AsyncMock(return_value=[])
    return redis


@pytest.fixture
def guard(pdt_config, mock_redis):
    return PDTGuardImpl(config=pdt_config, redis_client=mock_redis)


class TestPDTGuardExemption:
    """Accounts at or above $25K are exempt from PDT rules."""

    @pytest.mark.asyncio
    async def test_exempt_at_threshold(self, guard):
        portfolio = _make_portfolio(25000.0)
        order = _make_sell_order("AAPL")
        result = await guard.check(order, portfolio)
        assert result.action == RiskAction.APPROVE
        assert result.metadata.get("pdt_exempt") is True

    @pytest.mark.asyncio
    async def test_exempt_above_threshold(self, guard):
        portfolio = _make_portfolio(100000.0)
        order = _make_sell_order("AAPL")
        result = await guard.check(order, portfolio)
        assert result.action == RiskAction.APPROVE
        assert result.metadata.get("pdt_exempt") is True

    @pytest.mark.asyncio
    async def test_not_exempt_below_threshold(self, guard, mock_redis):
        """Below $25K, PDT rules apply."""
        mock_redis.zrangebyscore = AsyncMock(return_value=[])
        portfolio = _make_portfolio(24999.99)
        order = _make_buy_order("AAPL")  # buy order, not a day trade
        result = await guard.check(order, portfolio)
        assert result.action == RiskAction.APPROVE
        assert result.metadata.get("pdt_exempt") is False


class TestPDTGuardDisabled:
    @pytest.mark.asyncio
    async def test_disabled_always_approves(self, mock_redis):
        config = PDTGuardConfig(enabled=False)
        guard = PDTGuardImpl(config=config, redis_client=mock_redis)
        portfolio = _make_portfolio(10000.0)
        order = _make_sell_order("AAPL")
        result = await guard.check(order, portfolio)
        assert result.action == RiskAction.APPROVE


class TestPDTDayTradeDetection:
    """Correctly identify what constitutes a day trade."""

    @pytest.mark.asyncio
    async def test_sell_position_opened_today_is_day_trade(self, guard):
        pos = _make_position_opened_today("AAPL")
        order = _make_sell_order("AAPL")
        is_dt = await guard.would_be_day_trade(order, [pos])
        assert is_dt is True

    @pytest.mark.asyncio
    async def test_sell_position_opened_yesterday_not_day_trade(self, guard):
        pos = _make_position_opened_days_ago("AAPL", 1)
        order = _make_sell_order("AAPL")
        is_dt = await guard.would_be_day_trade(order, [pos])
        assert is_dt is False

    @pytest.mark.asyncio
    async def test_sell_different_symbol_not_day_trade(self, guard):
        pos = _make_position_opened_today("AAPL")
        order = _make_sell_order("MSFT")  # different symbol
        is_dt = await guard.would_be_day_trade(order, [pos])
        assert is_dt is False

    @pytest.mark.asyncio
    async def test_buy_order_not_day_trade(self, guard):
        pos = _make_position_opened_today("AAPL")
        order = _make_buy_order("AAPL")
        is_dt = await guard.would_be_day_trade(order, [pos])
        assert is_dt is False

    @pytest.mark.asyncio
    async def test_sell_with_no_positions(self, guard):
        order = _make_sell_order("AAPL")
        is_dt = await guard.would_be_day_trade(order, [])
        assert is_dt is False


class TestPDTGuardBlocking:
    """PDT guard must block the 4th day trade."""

    @pytest.mark.asyncio
    async def test_blocks_when_at_limit(self, guard, mock_redis):
        """3 day trades already used -> reject any potential day trade."""
        mock_redis.zrangebyscore = AsyncMock(return_value=["t1", "t2", "t3"])
        portfolio = _make_portfolio(20000.0)
        order = _make_buy_order("GOOG")  # not a day trade itself
        result = await guard.check(order, portfolio)
        # At limit, even non-day trades are rejected because count >= max
        assert result.action == RiskAction.REJECT
        assert "PDT LIMIT REACHED" in result.reasons[0]

    @pytest.mark.asyncio
    async def test_blocks_day_trade_that_would_exceed(self, guard, mock_redis):
        """2 day trades used + this would be a 3rd that would make total > max=3 at next check."""
        mock_redis.zrangebyscore = AsyncMock(return_value=["t1", "t2"])
        pos = _make_position_opened_today("AAPL")
        portfolio = _make_portfolio(20000.0, [pos])
        order = _make_sell_order("AAPL")  # would be day trade #3
        result = await guard.check(order, portfolio)
        # 3rd day trade is allowed (limit is 3), so this should approve with warning
        assert result.action == RiskAction.APPROVE
        assert result.metadata["pdt_trades_after"] == 3

    @pytest.mark.asyncio
    async def test_allows_non_day_trade_below_limit(self, guard, mock_redis):
        """1 day trade used, buying new stock (not a day trade) -> approve."""
        mock_redis.zrangebyscore = AsyncMock(return_value=["t1"])
        portfolio = _make_portfolio(20000.0)
        order = _make_buy_order("GOOG")
        result = await guard.check(order, portfolio)
        assert result.action == RiskAction.APPROVE
        assert result.metadata["pdt_trades_used"] == 1

    @pytest.mark.asyncio
    async def test_allows_with_zero_day_trades(self, guard, mock_redis):
        """No day trades used -> approve."""
        mock_redis.zrangebyscore = AsyncMock(return_value=[])
        portfolio = _make_portfolio(20000.0)
        order = _make_buy_order("AAPL")
        result = await guard.check(order, portfolio)
        assert result.action == RiskAction.APPROVE
        assert result.metadata["pdt_trades_used"] == 0


class TestPDTGuardRecording:
    @pytest.mark.asyncio
    async def test_record_day_trade(self, guard, mock_redis):
        await guard.record_day_trade("AAPL", date(2024, 3, 11))
        mock_redis.zadd.assert_called_once()
        mock_redis.zremrangebyscore.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_day_trades(self, guard, mock_redis):
        mock_redis.zrangebyscore = AsyncMock(return_value=["a", "b"])
        count = await guard.count_day_trades()
        assert count == 2
