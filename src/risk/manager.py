"""Top-level risk manager facade implementing the RiskManager interface."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import structlog

from src.core.config import RiskSettings
from src.core.interfaces import RiskManager
from src.core.models import AutonomyMode, Order, PortfolioSnapshot, RiskAction, RiskCheckResult
from src.risk.autonomy_validator import AutonomyValidator
from src.risk.circuit_breaker import CircuitBreakerManager
from src.risk.kill_switch import KillSwitch
from src.risk.pdt_guard import PDTGuardImpl
from src.risk.portfolio_monitor import PortfolioMonitor
from src.risk.pre_trade import PreTradeRiskEngine
from src.risk.reconciliation import ReconciliationEngine

logger = structlog.get_logger(__name__)


class RiskManagerImpl(RiskManager):
    """Combines all risk subsystems into a single entry point."""

    def __init__(
        self,
        broker_adapter=None,
        pdt_guard: PDTGuardImpl | None = None,
    ) -> None:
        self._pdt = pdt_guard or PDTGuardImpl()
        self._pre_trade = PreTradeRiskEngine(pdt_guard=self._pdt)
        self._monitor = PortfolioMonitor(pdt_guard=self._pdt)
        self._circuit_breakers = CircuitBreakerManager()
        self._kill_switch = KillSwitch(broker_adapter=broker_adapter)
        self._reconciliation = ReconciliationEngine()
        self._autonomy_validator = AutonomyValidator()

    # ------------------------------------------------------------------
    # RiskManager interface
    # ------------------------------------------------------------------

    async def check_pre_trade(
        self, order: Order, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Full pre-trade check: kill switch + circuit breakers + pre-trade rules."""
        # Kill switch is the fastest check
        if await self._kill_switch.is_active():
            logger.critical("pre_trade_blocked_kill_switch", symbol=order.symbol)
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=["Kill switch is ACTIVE — all trading halted"],
            )

        # Circuit breakers (use cached state from last portfolio check)
        cb_states = await self._circuit_breakers.get_states()
        tripped = [
            name for name, state in cb_states.items() if state.get("tripped")
        ]
        if tripped:
            reasons = [
                f"Circuit breaker '{name}' is tripped: {cb_states[name].get('reason', 'unknown')}"
                for name in tripped
            ]
            logger.critical("pre_trade_blocked_circuit_breaker", breakers=tripped)
            return RiskCheckResult(
                action=RiskAction.REJECT,
                reasons=reasons,
            )

        # Run pre-trade risk checks
        return await self._pre_trade.check_pre_trade(order, portfolio)

    async def check_portfolio(
        self, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Full portfolio check: monitor + circuit breakers."""
        # Portfolio health
        monitor_result = await self._monitor.check_portfolio(portfolio)

        # Circuit breakers with current portfolio data
        context = self._circuit_breakers.build_context(portfolio=portfolio)
        cb_results = await self._circuit_breakers.check_all(context)
        tripped = [(name, reason) for name, t, reason in cb_results if t]

        if tripped:
            for name, reason in tripped:
                monitor_result.reasons.append(f"Circuit breaker '{name}': {reason}")
            if monitor_result.action == RiskAction.APPROVE:
                monitor_result.action = RiskAction.REJECT

            # Auto-activate kill switch on critical circuit breaker trips
            critical_breakers = {"drawdown", "daily_loss", "reconciliation"}
            critical_tripped = [n for n, _ in tripped if n in critical_breakers]
            if critical_tripped:
                reason = f"Auto kill switch: {', '.join(critical_tripped)} circuit breaker(s) tripped"
                await self._kill_switch.activate(reason)

        return monitor_result

    async def is_kill_switch_active(self) -> bool:
        return await self._kill_switch.is_active()

    async def activate_kill_switch(self, reason: str) -> None:
        await self._kill_switch.activate(reason)

    # ------------------------------------------------------------------
    # Dashboard & utilities
    # ------------------------------------------------------------------

    async def get_risk_dashboard(self, portfolio: PortfolioSnapshot) -> dict:
        """Return a comprehensive risk dashboard for the web UI."""
        metrics = await self._monitor.get_risk_metrics(portfolio)
        cb_states = await self._circuit_breakers.get_states()
        ks_status = await self._kill_switch.get_status()

        return {
            "portfolio_metrics": metrics,
            "circuit_breakers": cb_states,
            "kill_switch": ks_status,
            "autonomy_mode": self._pre_trade._settings.autonomy_mode,
        }

    @property
    def pdt_guard(self) -> PDTGuardImpl:
        return self._pdt

    @property
    def kill_switch(self) -> KillSwitch:
        return self._kill_switch

    @property
    def circuit_breakers(self) -> CircuitBreakerManager:
        return self._circuit_breakers

    @property
    def reconciliation(self) -> ReconciliationEngine:
        return self._reconciliation

    @property
    def portfolio_monitor(self) -> PortfolioMonitor:
        return self._monitor

    @property
    def settings(self) -> RiskSettings:
        return self._pre_trade._settings

    # ------------------------------------------------------------------
    # Autonomy mode transitions (Phase 3)
    # ------------------------------------------------------------------

    async def validate_mode_transition(
        self,
        target_mode: AutonomyMode,
        portfolio_metrics: dict,
        confirmation: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate whether transitioning to target_mode is permitted.

        For FULL_AUTONOMOUS, also checks that confirmation == "FULL_AUTONOMOUS".
        """
        current_mode = AutonomyMode(self._pre_trade._settings.autonomy_mode)

        if target_mode == AutonomyMode.FULL_AUTONOMOUS:
            if confirmation != "FULL_AUTONOMOUS":
                return False, [
                    "Transitioning to FULL_AUTONOMOUS requires typed confirmation 'FULL_AUTONOMOUS'"
                ]

        return self._autonomy_validator.validate_transition(
            current_mode, target_mode, portfolio_metrics
        )

    async def transition_autonomy_mode(
        self,
        target_mode: AutonomyMode,
        portfolio_metrics: dict,
        confirmation: str | None = None,
    ) -> bool:
        """Validate and apply an autonomy mode transition.

        On success, updates the in-memory settings and writes audit trail to Redis.
        Returns True if transition was applied, False if validation failed.
        """
        approved, reasons = await self.validate_mode_transition(
            target_mode, portfolio_metrics, confirmation
        )
        if not approved:
            logger.warning(
                "autonomy_transition_denied",
                target=target_mode.value,
                reasons=reasons,
            )
            return False

        old_mode = self._pre_trade._settings.autonomy_mode
        # Update in-memory setting
        self._pre_trade._settings.autonomy_mode = target_mode.value

        # Persist to Redis for audit trail (lazy import to avoid startup cost)
        try:
            from src.core.redis import get_redis

            redis = await get_redis()
            now = datetime.now(timezone.utc).isoformat()
            await redis.set("risk:autonomy:mode_since", now)
            log_entry = json.dumps({
                "from": old_mode,
                "to": target_mode.value,
                "at": now,
            })
            await redis.rpush("risk:autonomy:transition_log", log_entry)
        except Exception as exc:
            logger.warning("autonomy_redis_write_failed", error=str(exc))

        logger.info(
            "autonomy_transition_applied",
            from_mode=old_mode,
            to_mode=target_mode.value,
        )
        return True
