"""TradeAdvisorAgent: produces TradeRecommendations using Claude API."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog

from src.agents.base import AgentContext, AgentResult, BaseAgent
from src.agents.cost_tracker import CostTracker
from src.agents.guardrails import guardrail

logger = structlog.get_logger(__name__)

_RECS_TTL = 86400 * 7  # 7 days
_BOUNDED_AUTO_CONFIDENCE_THRESHOLD = 0.7


class TradeAdvisorAgent(BaseAgent):
    """Produces trade recommendations via a plain async workflow (no LangGraph)."""

    @property
    def name(self) -> str:
        return "advisor"

    @property
    def description(self) -> str:
        return "Produces trade recommendations for symbols using Claude"

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
        """Run the trade advisor workflow.

        context.symbol: ticker symbol
        context.data: optional pre-gathered context dict (skips gather_symbol_context if provided)
        """
        from src.core.config import get_settings
        from src.core.models import RecommendationAction, TradeRecommendation

        settings = get_settings()
        agent_cfg = settings.agent

        if not agent_cfg.enabled:
            logger.info("advisor_agent.disabled")
            return AgentResult(output=None, metadata={"disabled": True})

        symbol = context.symbol or ""
        model = agent_cfg.advisor_model

        # Step 1: Gather symbol context (use pre-gathered if provided)
        if context.data.get("_context_gathered"):
            sym_ctx = context.data
        else:
            from src.agents.context import gather_symbol_context
            sym_ctx = await gather_symbol_context(symbol)

        # Step 2: Budget check
        await self._cost_tracker.reject_if_over_budget()

        # Step 3: Build prompt and check cache
        from src.agents.context import format_context_for_prompt
        from src.agents.prompts.advisor import RECOMMEND_TRADE_TOOL, SYSTEM_PROMPT

        context_text = format_context_for_prompt(sym_ctx)
        prompt_hash = CostTracker.compute_prompt_hash(context_text, model, symbol=symbol)
        cached = await self._cost_tracker.get_cached_response(prompt_hash)

        if cached:
            tool_input = json.loads(cached)
            input_tokens = 0
            output_tokens = 0
        else:
            tool_input, input_tokens, output_tokens = await self._call_claude(
                context_text, symbol, model, agent_cfg, SYSTEM_PROMPT, RECOMMEND_TRADE_TOOL
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
                task_type="recommendation",
            )
            cost_usd = usage.cost_usd

        # Step 5: Parse recommendation
        try:
            action = RecommendationAction(tool_input.get("action", "HOLD"))
        except ValueError:
            action = RecommendationAction.HOLD

        confidence = float(tool_input.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        rec = TradeRecommendation(
            symbol=symbol,
            action=action,
            confidence=confidence,
            rationale=tool_input.get("rationale", ""),
            supporting_signals=tool_input.get("supporting_signals", []),
            risk_factors=tool_input.get("risk_factors", []),
            suggested_entry=tool_input.get("suggested_entry"),
            suggested_stop=tool_input.get("suggested_stop"),
            suggested_target=tool_input.get("suggested_target"),
            human_approved=None,  # will be set by risk gate below
        )

        # Step 6: Risk gate — apply autonomy mode
        autonomy_mode = settings.risk.autonomy_mode
        rec = self._apply_risk_gate(rec, autonomy_mode)

        # Step 7: Store recommendation
        await self._store_recommendation(rec)

        logger.info(
            "advisor_agent.complete",
            symbol=symbol,
            action=action.value,
            confidence=confidence,
            autonomy_mode=autonomy_mode,
            approved=rec.human_approved,
            cached=input_tokens == 0,
        )

        return AgentResult(
            output=rec,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost_usd,
            metadata={
                "symbol": symbol,
                "action": action.value,
                "confidence": confidence,
                "autonomy_mode": autonomy_mode,
                "cached": input_tokens == 0,
            },
        )

    def _apply_risk_gate(self, rec, autonomy_mode: str):
        """Apply autonomy mode logic to set human_approved on the recommendation."""
        from src.core.models import AutonomyMode

        if autonomy_mode in (AutonomyMode.PAPER_ONLY.value, AutonomyMode.MANUAL_APPROVAL.value):
            # Queue for human review
            rec = rec.model_copy(update={"human_approved": None})
        elif autonomy_mode == AutonomyMode.BOUNDED_AUTONOMOUS.value:
            # Auto-approve only if confidence meets threshold
            if rec.confidence >= _BOUNDED_AUTO_CONFIDENCE_THRESHOLD:
                rec = rec.model_copy(update={"human_approved": True})
            else:
                rec = rec.model_copy(update={"human_approved": None})
        elif autonomy_mode == AutonomyMode.FULL_AUTONOMOUS.value:
            rec = rec.model_copy(update={"human_approved": True})

        return rec

    async def _call_claude(
        self,
        context_text: str,
        symbol: str,
        model: str,
        agent_cfg,
        system_prompt: str,
        tool: dict,
    ) -> tuple[dict, int, int]:
        from tenacity import retry, stop_after_attempt, wait_exponential

        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
        async def _attempt() -> tuple[dict, int, int]:
            from src.agents.client import get_anthropic_client
            client = get_anthropic_client()

            response = client.messages.create(
                model=model,
                max_tokens=agent_cfg.max_output_tokens,
                temperature=agent_cfg.temperature,
                system=system_prompt,
                tools=[tool],
                tool_choice={"type": "tool", "name": "recommend_trade"},
                messages=[
                    {
                        "role": "user",
                        "content": f"Please provide a trade recommendation for {symbol}:\n\n{context_text}",
                    }
                ],
            )

            tool_input = {}
            for block in response.content:
                if block.type == "tool_use" and block.name == "recommend_trade":
                    tool_input = block.input
                    break

            if not tool_input:
                raise ValueError("Claude response did not include recommend_trade tool output")

            return tool_input, response.usage.input_tokens, response.usage.output_tokens

        return await _attempt()

    _MAX_RECS_PER_SYMBOL = 50

    async def _store_recommendation(self, rec) -> None:
        redis = await self._get_redis()
        rec_id = str(uuid.uuid4())
        key = f"agent:recommendations:{rec_id}"

        await redis.set(key, rec.model_dump_json(), ex=_RECS_TTL)

        # Maintain recent index (all recommendations, newest first)
        await redis.lpush("agent:recommendations:recent", rec_id)
        await redis.ltrim("agent:recommendations:recent", 0, 199)
        await redis.expire("agent:recommendations:recent", _RECS_TTL)

        # Maintain per-symbol index
        symbol = rec.symbol or ""
        if symbol:
            symbol_key = f"agent:recommendations:by_symbol:{symbol}"
            await redis.lpush(symbol_key, rec_id)
            await redis.ltrim(symbol_key, 0, self._MAX_RECS_PER_SYMBOL - 1)
            await redis.expire(symbol_key, _RECS_TTL)

        # Queue pending recommendations for human review
        if rec.human_approved is None:
            await redis.lpush("agent:recommendations:pending", rec_id)
