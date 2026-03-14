"""Pre-trade risk engine: validates every order before submission."""
from __future__ import annotations

from src.core.config import get_settings
from src.core.models import (
    AutonomyMode,
    Order,
    OrderSide,
    PortfolioSnapshot,
    RiskAction,
    RiskCheckResult,
)

import structlog

from src.risk.pdt_guard import PDTGuardImpl

logger = structlog.get_logger(__name__)


class PreTradeRiskEngine:
    """Runs all pre-trade risk checks and returns a consolidated result."""

    def __init__(self, pdt_guard: PDTGuardImpl | None = None) -> None:
        self._settings = get_settings().risk
        self._pdt = pdt_guard or PDTGuardImpl()

    async def check_pre_trade(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Run all pre-trade checks. Returns the most restrictive action."""
        reasons: list[str] = []
        action = RiskAction.APPROVE
        adjusted_qty: float | None = None
        metadata: dict = {}

        checks = [
            self._check_min_price(order),
            self._check_position_size(order, portfolio),
            self._check_sector_exposure(order, portfolio),
            self._check_max_positions(order, portfolio),
            self._check_daily_trade_count(portfolio),
            self._check_cash_reserve(order, portfolio),
        ]

        for result in checks:
            if result.action == RiskAction.REJECT:
                action = RiskAction.REJECT
                reasons.extend(result.reasons)
            elif result.action == RiskAction.REDUCE_SIZE and action != RiskAction.REJECT:
                action = RiskAction.REDUCE_SIZE
                adjusted_qty = result.adjusted_quantity
                reasons.extend(result.reasons)
            elif result.action == RiskAction.REQUIRE_HUMAN_APPROVAL and action == RiskAction.APPROVE:
                action = RiskAction.REQUIRE_HUMAN_APPROVAL
                reasons.extend(result.reasons)
            elif result.action == RiskAction.APPROVE:
                # Only add informational reasons if all checks pass
                pass
            metadata.update(result.metadata)

        # PDT check (async)
        pdt_result = await self._pdt.check(order, portfolio)
        if pdt_result.action == RiskAction.REJECT:
            action = RiskAction.REJECT
        reasons.extend(pdt_result.reasons)
        metadata.update(pdt_result.metadata)

        # Autonomy mode check (can escalate to REQUIRE_HUMAN_APPROVAL)
        if action != RiskAction.REJECT:
            autonomy_result = self._check_autonomy_mode(order)
            if autonomy_result.action == RiskAction.REJECT:
                action = RiskAction.REJECT
            elif autonomy_result.action == RiskAction.REQUIRE_HUMAN_APPROVAL:
                if action == RiskAction.APPROVE:
                    action = RiskAction.REQUIRE_HUMAN_APPROVAL
            reasons.extend(autonomy_result.reasons)

        final = RiskCheckResult(
            action=action,
            reasons=reasons,
            adjusted_quantity=adjusted_qty,
            metadata=metadata,
        )
        logger.info(
            "pre_trade_check_complete",
            symbol=order.symbol,
            side=order.side.value,
            action=action.value,
            reason_count=len(reasons),
        )
        return final

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_min_price(self, order: Order) -> RiskCheckResult:
        min_price = self._settings.position_limits.min_price
        price = order.limit_price or order.stop_price or 0.0
        if price > 0 and price < min_price:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[f"Price ${price:.2f} below minimum ${min_price:.2f} (no penny stocks)"],
            )
        return RiskCheckResult(action=RiskAction.APPROVE)

    def _check_position_size(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        max_pct = self._settings.position_limits.max_position_pct / 100.0
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=["Portfolio equity is zero or negative"],
            )

        price = order.limit_price or order.stop_price or 0.0
        if price <= 0:
            # Market order — we can't check size without price, approve cautiously
            return RiskCheckResult(action=RiskAction.APPROVE)

        order_value = price * order.quantity
        max_value = equity * max_pct

        # Include existing position value for the same symbol
        existing_value = 0.0
        for pos in portfolio.positions:
            if pos.symbol == order.symbol:
                existing_value = abs(pos.market_value)
                break

        if order.side == OrderSide.BUY:
            total_exposure = existing_value + order_value
        else:
            total_exposure = max(existing_value - order_value, 0.0)

        if total_exposure > max_value:
            # Can we reduce size?
            allowed_additional = max(max_value - existing_value, 0.0)
            if allowed_additional > 0 and price > 0:
                reduced_qty = int(allowed_additional / price)
                if reduced_qty > 0:
                    return RiskCheckResult(
                        action=RiskAction.REDUCE_SIZE,
                        reasons=[
                            f"Position would be {total_exposure / equity * 100:.1f}% of portfolio "
                            f"(max {max_pct * 100:.1f}%). Reducing to {reduced_qty} shares."
                        ],
                        adjusted_quantity=float(reduced_qty),
                    )
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[
                    f"Position would be {total_exposure / equity * 100:.1f}% of portfolio "
                    f"(max {max_pct * 100:.1f}%)"
                ],
            )
        return RiskCheckResult(action=RiskAction.APPROVE)

    def _check_sector_exposure(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        if order.side != OrderSide.BUY:
            return RiskCheckResult(action=RiskAction.APPROVE)

        max_pct = self._settings.position_limits.max_sector_pct / 100.0
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskCheckResult(action=RiskAction.APPROVE)

        # Find the sector of the order's symbol from existing positions
        order_sector = ""
        for pos in portfolio.positions:
            if pos.symbol == order.symbol and pos.sector:
                order_sector = pos.sector
                break

        if not order_sector:
            # Unknown sector — can't check, approve
            return RiskCheckResult(action=RiskAction.APPROVE)

        sector_value = portfolio.sector_exposure.get(order_sector, 0.0)
        price = order.limit_price or order.stop_price or 0.0
        new_sector_value = sector_value + (price * order.quantity if price > 0 else 0)
        sector_pct = new_sector_value / equity

        if sector_pct > max_pct:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[
                    f"Sector '{order_sector}' exposure would be {sector_pct * 100:.1f}% "
                    f"(max {max_pct * 100:.1f}%)"
                ],
            )
        return RiskCheckResult(action=RiskAction.APPROVE)

    def _check_max_positions(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        if order.side != OrderSide.BUY:
            return RiskCheckResult(action=RiskAction.APPROVE)

        max_pos = self._settings.portfolio_limits.max_positions
        current = len(portfolio.positions)

        # Check if we're adding a new position vs adding to existing
        is_new = not any(p.symbol == order.symbol for p in portfolio.positions)
        if is_new and current >= max_pos:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[f"Max positions reached ({current}/{max_pos})"],
            )
        return RiskCheckResult(action=RiskAction.APPROVE)

    def _check_daily_trade_count(
        self, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        # Daily trade count is tracked externally; we check via metadata
        max_trades = self._settings.portfolio_limits.max_daily_trades
        daily_trades = portfolio.metadata.get("daily_trade_count", 0)
        if daily_trades >= max_trades:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[f"Daily trade limit reached ({daily_trades}/{max_trades})"],
            )
        return RiskCheckResult(action=RiskAction.APPROVE)

    def _check_cash_reserve(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        if order.side != OrderSide.BUY:
            return RiskCheckResult(action=RiskAction.APPROVE)

        min_reserve_pct = self._settings.portfolio_limits.min_cash_reserve_pct / 100.0
        equity = portfolio.total_equity
        if equity <= 0:
            return RiskCheckResult(action=RiskAction.APPROVE)

        price = order.limit_price or order.stop_price or 0.0
        order_cost = price * order.quantity if price > 0 else 0
        cash_after = portfolio.cash - order_cost
        reserve_after = cash_after / equity if equity > 0 else 0

        if reserve_after < min_reserve_pct:
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=[
                    f"Cash reserve would drop to {reserve_after * 100:.1f}% "
                    f"(minimum {min_reserve_pct * 100:.1f}%)"
                ],
            )
        return RiskCheckResult(action=RiskAction.APPROVE)

    def _check_autonomy_mode(self, order: Order) -> RiskCheckResult:
        mode = AutonomyMode(self._settings.autonomy_mode)

        if mode == AutonomyMode.PAPER_ONLY:
            return RiskCheckResult(
                action=RiskAction.APPROVE,
                reasons=["Paper trading mode — order will be simulated"],
            )
        elif mode == AutonomyMode.MANUAL_APPROVAL:
            return RiskCheckResult(
                action=RiskAction.REQUIRE_HUMAN_APPROVAL,
                reasons=["Manual approval mode — human review required"],
            )
        elif mode == AutonomyMode.BOUNDED_AUTONOMOUS:
            # In bounded mode, large orders need approval
            price = order.limit_price or order.stop_price or 0.0
            if price * order.quantity > 10000:
                return RiskCheckResult(
                    action=RiskAction.REQUIRE_HUMAN_APPROVAL,
                    reasons=["Bounded autonomous: order > $10,000 requires approval"],
                )
            return RiskCheckResult(action=RiskAction.APPROVE)
        elif mode == AutonomyMode.FULL_AUTONOMOUS:
            # Layer 4 (LLM guardrails) is enforced by AutonomyValidator before
            # transitioning to FULL_AUTONOMOUS.  Once in this mode all four risk
            # layers (position limits, portfolio limits, circuit breakers, and LLM
            # guardrails) have been validated.  Auto-approve here.
            return RiskCheckResult(action=RiskAction.APPROVE)

        return RiskCheckResult(
            action=RiskAction.REJECT,
            reasons=[f"Unknown autonomy mode: {mode}"],
        )
