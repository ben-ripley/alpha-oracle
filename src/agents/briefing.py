"""PortfolioReviewAgent: generates daily portfolio briefings using Claude."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog

from src.agents.base import AgentContext, AgentResult, BaseAgent
from src.agents.cost_tracker import CostTracker
from src.agents.guardrails import guardrail

logger = structlog.get_logger(__name__)

_BRIEFING_TTL = 86400 * 30  # 30 days


class PortfolioReviewAgent(BaseAgent):
    """Generates daily portfolio briefings using Claude."""

    @property
    def name(self) -> str:
        return "briefing"

    @property
    def description(self) -> str:
        return "Generates daily portfolio briefings with P&L summary and actionable insights"

    def __init__(self, redis_client=None) -> None:
        self._cost_tracker = CostTracker(redis_client)
        self._redis = redis_client

    async def _get_redis(self):
        if self._redis is None:
            from src.core.redis import get_redis
            self._redis = await get_redis()
        return self._redis

    @guardrail
    async def run(self, context: AgentContext) -> AgentResult:
        """Generate a daily portfolio briefing.

        context.data must contain:
            portfolio: PortfolioSnapshot
            positions: list[Position]
            recent_trades: list[TradeRecord] (optional)
            market_data: dict (optional — VIX, SPY stats, etc.)
        """
        from src.core.config import get_settings
        from src.core.models import DailyBriefing

        settings = get_settings()
        agent_cfg = settings.agent

        if not agent_cfg.enabled:
            logger.info("briefing_agent.disabled")
            return AgentResult(output=None, metadata={"disabled": True})

        model = agent_cfg.briefing_model

        # Build the portfolio context string
        portfolio_text = self._format_portfolio_context(context.data)

        # Budget check
        await self._cost_tracker.reject_if_over_budget()

        # Cache check (briefings are cached for the day, not 4h)
        from src.agents.prompts.briefing import GENERATE_BRIEFING_TOOL, SYSTEM_PROMPT

        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        prompt_hash = CostTracker.compute_prompt_hash(portfolio_text, model, date=today_str)
        cached = await self._cost_tracker.get_cached_response(prompt_hash)

        tool_input = None
        input_tokens = 0
        output_tokens = 0
        if cached:
            try:
                tool_input = json.loads(cached)
            except json.JSONDecodeError:
                logger.warning("briefing.cache_decode_error")
        if tool_input is None:
            tool_input, input_tokens, output_tokens = await self._call_claude(
                portfolio_text, model, agent_cfg, SYSTEM_PROMPT, GENERATE_BRIEFING_TOOL
            )
            await self._cost_tracker.cache_response(prompt_hash, json.dumps(tool_input))

        # Record usage
        cost_usd = 0.0
        if input_tokens > 0 or output_tokens > 0:
            usage = await self._cost_tracker.record_usage(
                agent_name=self.name,
                model_name=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                task_type="briefing",
            )
            cost_usd = usage.cost_usd

        # Extract portfolio metrics from context
        portfolio = context.data.get("portfolio")
        if portfolio is None:
            logger.warning("briefing_agent.portfolio_unavailable")
        daily_pnl = portfolio.daily_pnl if portfolio else 0.0
        max_drawdown = settings.risk.portfolio_limits.max_drawdown_pct
        current_drawdown = portfolio.max_drawdown_pct if portfolio else 0.0
        risk_utilization = (current_drawdown / max_drawdown) if max_drawdown > 0 else 0.0

        briefing = DailyBriefing(
            date=datetime.now(UTC),
            portfolio_summary=tool_input.get("portfolio_summary", ""),
            daily_pnl=daily_pnl,
            risk_utilization=min(risk_utilization, 1.0),
            upcoming_catalysts=tool_input.get("upcoming_catalysts", []),
            suggested_exits=tool_input.get("suggested_exits", []),
            market_regime=tool_input.get("market_regime", "SIDEWAYS"),
            key_observations=tool_input.get("key_observations", []),
        )

        await self._store_briefing(briefing, today_str)

        logger.info(
            "briefing_agent.complete",
            date=today_str,
            market_regime=briefing.market_regime,
            observations=len(briefing.key_observations),
            suggested_exits=len(briefing.suggested_exits),
            cached=input_tokens == 0,
        )

        return AgentResult(
            output=briefing,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost_usd,
            metadata={"date": today_str, "cached": input_tokens == 0},
        )

    def _format_portfolio_context(self, data: dict) -> str:
        """Build a text summary of portfolio state for the LLM prompt."""
        lines = []

        portfolio = data.get("portfolio")
        if portfolio:
            lines.append(f"Portfolio equity: ${portfolio.total_equity:,.2f}")
            lines.append(f"Cash: ${portfolio.cash:,.2f}")
            lines.append(f"Daily P&L: ${portfolio.daily_pnl:,.2f} ({portfolio.daily_pnl_pct:.2f}%)")
            lines.append(f"Total P&L: ${portfolio.total_pnl:,.2f} ({portfolio.total_pnl_pct:.2f}%)")
            lines.append(f"Max drawdown: {portfolio.max_drawdown_pct:.2f}%")

        positions = data.get("positions", [])
        if positions:
            lines.append(f"\nPositions ({len(positions)}):")
            for pos in positions[:10]:  # limit to avoid token overflow
                lines.append(
                    f"  {pos.symbol}: {pos.quantity:.0f} shares @ ${pos.avg_entry_price:.2f}, "
                    f"current ${pos.current_price:.2f}, P&L ${pos.unrealized_pnl:.2f}"
                )

        recent_trades = data.get("recent_trades", [])
        if recent_trades:
            lines.append(f"\nRecent trades ({len(recent_trades)}):")
            for trade in recent_trades[:5]:
                lines.append(f"  {trade.symbol}: {trade.side.value} {trade.quantity:.0f} shares")

        market_data = data.get("market_data", {})
        if market_data:
            lines.append(f"\nMarket data: {market_data}")

        return "\n".join(lines) if lines else "No portfolio data available."

    async def _call_claude(
        self,
        portfolio_text: str,
        model: str,
        agent_cfg,
        system_prompt: str,
        tool: dict,
    ) -> tuple[dict, int, int]:
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        )
        async def _attempt() -> tuple[dict, int, int]:
            from src.agents.client import get_anthropic_client
            client = get_anthropic_client()

            response = client.messages.create(
                model=model,
                max_tokens=agent_cfg.max_output_tokens,
                temperature=agent_cfg.temperature,
                system=system_prompt,
                tools=[tool],
                tool_choice={"type": "tool", "name": "generate_briefing"},
                messages=[
                    {
                        "role": "user",
                        "content": f"Please generate today's portfolio briefing:\n\n{portfolio_text}",
                    }
                ],
            )

            tool_input = {}
            for block in response.content:
                if block.type == "tool_use" and block.name == "generate_briefing":
                    tool_input = block.input
                    break

            if not tool_input:
                raise ValueError("Claude response did not include generate_briefing tool output")

            return tool_input, response.usage.input_tokens, response.usage.output_tokens

        return await _attempt()

    async def _store_briefing(self, briefing, date_str: str) -> None:
        redis = await self._get_redis()
        key = f"agent:briefings:{date_str}"
        await redis.set(key, briefing.model_dump_json(), ex=_BRIEFING_TTL)
