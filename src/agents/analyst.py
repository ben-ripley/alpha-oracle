"""ClaudeAnalystAgent: SEC filing analysis using Claude API with response caching."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog

from src.agents.base import AgentContext, AgentResult, BaseAgent
from src.agents.cost_tracker import CostTracker
from src.agents.guardrails import guardrail

logger = structlog.get_logger(__name__)


class ClaudeAnalystAgent(BaseAgent):
    """Analyzes SEC filings using Claude and returns structured AgentAnalysis."""

    @property
    def name(self) -> str:
        return "analyst"

    @property
    def description(self) -> str:
        return "Analyzes SEC filings using Claude to extract financial insights"

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
        """Analyze a filing and return an AgentResult containing AgentAnalysis.

        context.data must contain:
            filing_text: str — the filing content
            symbol: str — ticker symbol
            filing_type: str — one of FILING_10K, FILING_10Q, FILING_8K, EARNINGS_SUMMARY
        """
        from src.core.config import get_settings
        from src.core.models import AgentAnalysis, AgentAnalysisType

        settings = get_settings()
        agent_cfg = settings.agent

        if not agent_cfg.enabled:
            logger.info("analyst_agent.disabled")
            return AgentResult(output=None, metadata={"disabled": True})

        filing_text = context.data.get("filing_text", "")
        symbol = context.symbol or context.data.get("symbol", "")
        filing_type_str = context.data.get("filing_type", "FILING_10K")

        try:
            filing_type = AgentAnalysisType(filing_type_str)
        except ValueError:
            filing_type = AgentAnalysisType.FILING_10K

        model = agent_cfg.analyst_model

        # Budget check before expensive API call
        await self._cost_tracker.reject_if_over_budget()

        # Build prompt and check cache
        from src.agents.prompts.analyst import ANALYZE_FILING_TOOL, SYSTEM_PROMPT
        prompt_hash = CostTracker.compute_prompt_hash(filing_text[:10000], model, filing_type=filing_type_str)
        cached = await self._cost_tracker.get_cached_response(prompt_hash)

        tool_input = None
        input_tokens = 0
        output_tokens = 0
        if cached:
            try:
                tool_input = json.loads(cached)
            except json.JSONDecodeError:
                logger.warning("analyst.cache_decode_error")
        if tool_input is None:
            tool_input, input_tokens, output_tokens = await self._call_claude(
                filing_text, model, agent_cfg, SYSTEM_PROMPT, ANALYZE_FILING_TOOL
            )
            await self._cost_tracker.cache_response(prompt_hash, json.dumps(tool_input))

        # Record usage (only when API was actually called)
        if input_tokens > 0 or output_tokens > 0:
            usage_record = await self._cost_tracker.record_usage(
                agent_name=self.name,
                model_name=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                task_type=filing_type_str,
            )
            cost_usd = usage_record.cost_usd
        else:
            cost_usd = 0.0

        analysis = AgentAnalysis(
            symbol=symbol,
            analysis_type=filing_type,
            summary=tool_input.get("summary", ""),
            key_points=tool_input.get("key_points", []),
            sentiment_score=float(tool_input.get("sentiment_score", 0.0)),
            risk_flags=tool_input.get("risk_flags", []),
            financial_highlights=tool_input.get("financial_highlights", {}),
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost_usd,
            model_name=model,
        )

        await self._store_analysis(analysis)

        logger.info(
            "analyst_agent.complete",
            symbol=symbol,
            filing_type=filing_type_str,
            sentiment=analysis.sentiment_score,
            risk_flags=len(analysis.risk_flags),
            cached=input_tokens == 0,
        )

        return AgentResult(
            output=analysis,
            tokens_used=input_tokens + output_tokens,
            cost_usd=cost_usd,
            metadata={"symbol": symbol, "filing_type": filing_type_str, "cached": input_tokens == 0},
        )

    async def _call_claude(
        self,
        filing_text: str,
        model: str,
        agent_cfg,
        system_prompt: str,
        tool: dict,
    ) -> tuple[dict, int, int]:
        """Call Claude API with retry. Returns (tool_input, input_tokens, output_tokens)."""
        from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type((TimeoutError, ConnectionError)),
        )
        async def _attempt() -> tuple[dict, int, int]:
            from src.agents.client import get_anthropic_client
            client = get_anthropic_client()

            # Truncate filing text to fit within input token budget
            truncated = filing_text[:agent_cfg.max_input_tokens * 3]  # rough char limit

            response = client.messages.create(
                model=model,
                max_tokens=agent_cfg.max_output_tokens,
                temperature=agent_cfg.temperature,
                system=system_prompt,
                tools=[tool],
                tool_choice={"type": "tool", "name": "analyze_filing"},
                messages=[
                    {
                        "role": "user",
                        "content": f"Please analyze the following SEC filing for {filing_text[:100]}:\n\n{truncated}",
                    }
                ],
            )

            # Extract tool_use block
            tool_input = {}
            for block in response.content:
                if block.type == "tool_use" and block.name == "analyze_filing":
                    tool_input = block.input
                    break

            if not tool_input:
                raise ValueError("Claude response did not include analyze_filing tool output")

            usage = response.usage
            return tool_input, usage.input_tokens, usage.output_tokens

        return await _attempt()

    # Lua script: atomically SET the analysis, LPUSH+LTRIM the symbol index, EXPIRE.
    # Prevents concurrent requests from interleaving the four operations and
    # accidentally trimming a freshly stored entry.
    _STORE_LUA = """
local key        = KEYS[1]
local symbol_key = KEYS[2]
local id         = ARGV[1]
local json       = ARGV[2]
local ttl        = tonumber(ARGV[3])
local max_e      = tonumber(ARGV[4])
redis.call('SET',    key,        json, 'EX', ttl)
redis.call('LPUSH',  symbol_key, id)
redis.call('LTRIM',  symbol_key, 0, max_e - 1)
redis.call('EXPIRE', symbol_key, ttl)
return 1
"""

    async def _store_analysis(self, analysis) -> None:
        """Store analysis atomically in Redis using a Lua script."""
        from src.core.config import get_settings
        cfg = get_settings().agent
        redis = await self._get_redis()
        analysis_id = str(uuid.uuid4())
        key = f"agent:analyses:{analysis_id}"
        symbol_key = f"agent:analyses:by_symbol:{analysis.symbol}"

        await redis.eval(
            self._STORE_LUA,
            2,
            key, symbol_key,
            analysis_id, analysis.model_dump_json(),
            str(cfg.analyses_ttl_seconds), str(cfg.max_analyses_per_symbol),
        )

    async def get_analyses_for_symbol(self, symbol: str) -> list:
        """Retrieve recent analyses for a symbol from Redis."""
        from src.core.config import get_settings
        from src.core.models import AgentAnalysis

        cfg = get_settings().agent
        redis = await self._get_redis()
        symbol_key = f"agent:analyses:by_symbol:{symbol}"
        ids = await redis.lrange(symbol_key, 0, cfg.max_analyses_per_symbol - 1)

        analyses = []
        for analysis_id in ids:
            data = await redis.get(f"agent:analyses:{analysis_id}")
            if data:
                try:
                    a = AgentAnalysis.model_validate_json(data)
                    if a.schema_version == 1:
                        analyses.append(a)
                except Exception:
                    logger.warning("analyst_agent.stale_analysis_discarded", id=analysis_id)
        return analyses
