"""Real-time portfolio health monitoring."""
from __future__ import annotations

import structlog

from src.core.config import get_settings
from src.core.models import PortfolioSnapshot, RiskAction, RiskCheckResult
from src.risk.pdt_guard import PDTGuardImpl

logger = structlog.get_logger(__name__)


class PortfolioMonitor:
    """Monitors portfolio health and flags dangerous conditions."""

    def __init__(self, pdt_guard: PDTGuardImpl | None = None) -> None:
        self._settings = get_settings().risk
        self._pdt = pdt_guard or PDTGuardImpl()

    async def check_portfolio(
        self, portfolio: PortfolioSnapshot
    ) -> RiskCheckResult:
        """Check overall portfolio health. Returns REJECT if trading should halt."""
        reasons: list[str] = []
        action = RiskAction.APPROVE

        # Drawdown check
        max_dd = self._settings.portfolio_limits.max_drawdown_pct
        if portfolio.max_drawdown_pct > max_dd:
            action = RiskAction.REJECT
            reasons.append(
                f"HALT: Drawdown {portfolio.max_drawdown_pct:.1f}% exceeds max {max_dd:.1f}%"
            )

        # Daily P&L check
        max_daily_loss = self._settings.portfolio_limits.max_daily_loss_pct
        if portfolio.daily_pnl_pct < -max_daily_loss:
            action = RiskAction.REJECT
            reasons.append(
                f"HALT: Daily loss {portfolio.daily_pnl_pct:.1f}% exceeds max -{max_daily_loss:.1f}%"
            )

        # Stop-loss proximity
        stop_loss_pct = self._settings.position_limits.stop_loss_pct / 100.0
        for pos in portfolio.positions:
            if pos.avg_entry_price > 0 and pos.current_price > 0:
                loss_pct = (pos.avg_entry_price - pos.current_price) / pos.avg_entry_price
                if loss_pct >= stop_loss_pct:
                    reasons.append(
                        f"STOP-LOSS: {pos.symbol} down {loss_pct * 100:.1f}% "
                        f"(stop at {stop_loss_pct * 100:.1f}%)"
                    )

        # Sector concentration warning
        max_sector_pct = self._settings.position_limits.max_sector_pct / 100.0
        equity = portfolio.total_equity
        if equity > 0:
            for sector, value in portfolio.sector_exposure.items():
                pct = value / equity
                if pct > max_sector_pct:
                    reasons.append(
                        f"CONCENTRATION: Sector '{sector}' at {pct * 100:.1f}% "
                        f"(max {max_sector_pct * 100:.1f}%)"
                    )

        if action == RiskAction.REJECT:
            logger.critical("portfolio_health_halt", reasons=reasons)
        elif reasons:
            logger.warning("portfolio_health_warnings", reasons=reasons)

        return RiskCheckResult(action=action, reasons=reasons)

    async def get_risk_metrics(
        self, portfolio: PortfolioSnapshot
    ) -> dict:
        """Return a dict of current risk metrics for the dashboard."""
        equity = portfolio.total_equity
        stop_loss_pct = self._settings.position_limits.stop_loss_pct / 100.0

        positions_at_risk = []
        for pos in portfolio.positions:
            if pos.avg_entry_price > 0 and pos.current_price > 0:
                loss_pct = (pos.avg_entry_price - pos.current_price) / pos.avg_entry_price
                if loss_pct >= stop_loss_pct * 0.5:  # flag when 50%+ towards stop
                    positions_at_risk.append({
                        "symbol": pos.symbol,
                        "loss_pct": round(loss_pct * 100, 2),
                        "stop_loss_pct": round(stop_loss_pct * 100, 2),
                    })

        sector_exposure = {}
        if equity > 0:
            for sector, value in portfolio.sector_exposure.items():
                sector_exposure[sector] = round(value / equity * 100, 2)

        pdt_trades_used = await self._pdt.count_day_trades()
        pdt_max = self._settings.pdt_guard.max_day_trades

        cash_reserve_pct = (portfolio.cash / equity * 100) if equity > 0 else 0.0

        return {
            "current_drawdown_pct": round(portfolio.max_drawdown_pct, 2),
            "daily_pnl_pct": round(portfolio.daily_pnl_pct, 2),
            "sector_exposure": sector_exposure,
            "positions_at_risk": positions_at_risk,
            "pdt_trades_used": f"{pdt_trades_used} of {pdt_max}",
            "cash_reserve_pct": round(cash_reserve_pct, 2),
            "total_positions": len(portfolio.positions),
            "max_positions": self._settings.portfolio_limits.max_positions,
        }
