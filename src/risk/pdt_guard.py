"""PDT (Pattern Day Trader) Guard - CRITICAL SAFETY COMPONENT.

Tracks day trades and enforces FINRA PDT rules. A bug here could trigger
regulatory restrictions on the account, so every check is conservative
and every decision is logged for audit.

Rules:
- A day trade = buying AND selling the same security on the same calendar day.
- Accounts under $25K equity are limited to 3 day trades per 5 rolling business days.
- If an account crosses below $25K, the PDT rule applies immediately.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

import redis.asyncio as aioredis
import structlog

from src.core.config import PDTGuard as PDTGuardConfig, get_settings
from src.core.models import (
    Order,
    OrderSide,
    PortfolioSnapshot,
    Position,
    RiskAction,
    RiskCheckResult,
)
from src.core.redis import get_redis

logger = structlog.get_logger(__name__)

REDIS_PDT_PREFIX = "risk:pdt:"
DAY_TRADE_TTL_SECONDS = 7 * 86400  # 7 days, generous buffer over 5 business days


def _business_days_ago(n: int, from_date: date | None = None) -> date:
    """Return the date that is *n* business days before *from_date*."""
    d = from_date or date.today()
    counted = 0
    while counted < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            counted += 1
    return d


class PDTGuardImpl:
    """Bulletproof PDT guard backed by Redis."""

    def __init__(
        self,
        config: PDTGuardConfig | None = None,
        redis_client: aioredis.Redis | None = None,
    ) -> None:
        self._config = config or get_settings().risk.pdt_guard
        self._redis_override = redis_client

    async def _redis(self) -> aioredis.Redis:
        return self._redis_override or await get_redis()

    # ------------------------------------------------------------------
    # Day-trade recording
    # ------------------------------------------------------------------

    async def record_day_trade(
        self,
        symbol: str,
        trade_date: date | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a completed day trade in Redis. Called by execution engine
        after confirming a round-trip was completed in the same day."""
        r = await self._redis()
        trade_date = trade_date or date.today()
        key = f"{REDIS_PDT_PREFIX}trades"
        entry = json.dumps({
            "symbol": symbol,
            "date": trade_date.isoformat(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        })
        await r.zadd(key, {entry: trade_date.toordinal()})
        # Trim entries older than 7 days to keep the set small
        cutoff = (date.today() - timedelta(days=8)).toordinal()
        await r.zremrangebyscore(key, "-inf", cutoff)
        logger.warning(
            "pdt_day_trade_recorded",
            symbol=symbol,
            trade_date=trade_date.isoformat(),
        )

    # ------------------------------------------------------------------
    # Counting
    # ------------------------------------------------------------------

    async def count_day_trades(self, rolling_window: int | None = None) -> int:
        """Count day trades within the rolling business-day window."""
        window = rolling_window or self._config.rolling_window_days
        r = await self._redis()
        start_date = _business_days_ago(window)
        key = f"{REDIS_PDT_PREFIX}trades"
        entries = await r.zrangebyscore(
            key, start_date.toordinal(), "+inf"
        )
        return len(entries)

    # ------------------------------------------------------------------
    # Predictive check
    # ------------------------------------------------------------------

    async def would_be_day_trade(
        self, order: Order, positions: list[Position]
    ) -> bool:
        """Return True if executing *order* would constitute a day trade.

        A day trade occurs when:
        1. SELL order for a position that was opened today.
        2. BUY order for a symbol that has an open sell order today (short covering
           same day is also a day trade, but we only go long in this system).
        """
        today = date.today()

        if order.side == OrderSide.SELL:
            for pos in positions:
                if pos.symbol != order.symbol:
                    continue
                if pos.entry_date is not None and pos.entry_date.date() == today:
                    logger.info(
                        "pdt_would_be_day_trade",
                        reason="selling_position_opened_today",
                        symbol=order.symbol,
                    )
                    return True

        # Conservative: if buying a symbol we already hold and might sell today,
        # we don't flag it here — the sell side is what triggers the day trade.
        return False

    # ------------------------------------------------------------------
    # Main check
    # ------------------------------------------------------------------

    async def check(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Run PDT check. Returns APPROVE or REJECT with detailed reasons.

        This method is intentionally conservative: when in doubt, REJECT.
        A false rejection is far less costly than a FINRA restriction.
        """
        if not self._config.enabled:
            logger.info("pdt_check_skipped", reason="pdt_guard_disabled")
            return RiskCheckResult(
                action=RiskAction.APPROVE,
                reasons=["PDT guard disabled"],
            )

        equity = portfolio.total_equity
        threshold = self._config.account_threshold
        max_trades = self._config.max_day_trades

        # Accounts at or above $25K are exempt from PDT
        # Use strict >= to be safe at the boundary
        if equity >= threshold:
            logger.info(
                "pdt_check_exempt",
                equity=equity,
                threshold=threshold,
            )
            return RiskCheckResult(
                action=RiskAction.APPROVE,
                reasons=[f"Account equity ${equity:,.2f} >= ${threshold:,.2f} PDT threshold"],
                metadata={"pdt_exempt": True},
            )

        # Below $25K — PDT rules apply
        current_count = await self.count_day_trades()

        # Check if we're already at the limit
        if current_count >= max_trades:
            reason = (
                f"PDT LIMIT REACHED: {current_count}/{max_trades} day trades used "
                f"in last {self._config.rolling_window_days} business days. "
                f"Account equity ${equity:,.2f} is below ${threshold:,.2f} threshold."
            )
            logger.critical(
                "pdt_check_rejected_at_limit",
                current_count=current_count,
                max_trades=max_trades,
                equity=equity,
            )
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[reason],
                metadata={
                    "pdt_trades_used": current_count,
                    "pdt_trades_max": max_trades,
                    "pdt_exempt": False,
                },
            )

        # Check if this specific order would create a day trade
        is_day_trade = await self.would_be_day_trade(order, portfolio.positions)

        if is_day_trade:
            new_count = current_count + 1
            if new_count > max_trades:
                reason = (
                    f"PDT BLOCKED: This order would be day trade #{new_count}, "
                    f"exceeding limit of {max_trades} per {self._config.rolling_window_days} "
                    f"business days. Account equity ${equity:,.2f} < ${threshold:,.2f}."
                )
                logger.critical(
                    "pdt_check_rejected_would_exceed",
                    would_be_count=new_count,
                    max_trades=max_trades,
                    symbol=order.symbol,
                )
                return RiskCheckResult(
                    action=RiskAction.REJECT,
                    reasons=[reason],
                    metadata={
                        "pdt_trades_used": current_count,
                        "pdt_trades_max": max_trades,
                        "pdt_would_be_day_trade": True,
                        "pdt_exempt": False,
                    },
                )

            # Would be a day trade but within limits — warn but approve
            logger.warning(
                "pdt_check_approved_day_trade",
                current_count=current_count,
                new_count=new_count,
                max_trades=max_trades,
                symbol=order.symbol,
            )
            return RiskCheckResult(
                action=RiskAction.APPROVE,
                reasons=[
                    f"Day trade #{new_count}/{max_trades} allowed. "
                    f"CAUTION: {max_trades - new_count} day trades remaining."
                ],
                metadata={
                    "pdt_trades_used": current_count,
                    "pdt_trades_after": new_count,
                    "pdt_trades_max": max_trades,
                    "pdt_would_be_day_trade": True,
                    "pdt_exempt": False,
                },
            )

        # Not a day trade — approve
        logger.info(
            "pdt_check_approved",
            current_count=current_count,
            max_trades=max_trades,
            symbol=order.symbol,
        )
        return RiskCheckResult(
            action=RiskAction.APPROVE,
            reasons=[f"Not a day trade. {max_trades - current_count}/{max_trades} day trades remaining."],
            metadata={
                "pdt_trades_used": current_count,
                "pdt_trades_max": max_trades,
                "pdt_would_be_day_trade": False,
                "pdt_exempt": False,
            },
        )
