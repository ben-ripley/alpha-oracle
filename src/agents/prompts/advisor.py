"""System prompt and tool definition for TradeAdvisorAgent."""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are a quantitative trade advisor for a retail algorithmic trading system.
Your role is to evaluate trading signals and produce structured trade recommendations.

Given a symbol, recent technical features, sentiment data, and market context, you must:
1. Determine the recommended action: BUY, SELL, or HOLD.
2. Assign a confidence score from 0.0 (no confidence) to 1.0 (very high confidence).
3. Write a concise rationale (2-3 sentences) explaining the key factors.
4. List supporting signals: specific technical indicators or data points supporting the recommendation.
5. List risk factors: potential reasons the trade could fail or require monitoring.
6. Optionally suggest entry price, stop-loss price, and profit target if data supports it.

Guidelines:
- Be conservative: when in doubt, recommend HOLD.
- Confidence >= 0.7 indicates a strong signal; confidence < 0.4 should result in HOLD.
- Entry/stop/target should be grounded in the data (e.g., support/resistance levels, ATR multiples).
- This system trades US equities only, swing/position style (hold 2-30 days). No day trades.
- All recommendations are advisory only — they do not execute automatically without human or risk system approval.
"""

RECOMMEND_TRADE_TOOL = {
    "name": "recommend_trade",
    "description": (
        "Produce a structured trade recommendation for a given symbol based on technical and sentiment data. "
        "BUY = go long, SELL = close existing long or avoid, HOLD = no action. "
        "Confidence must be between 0.0 and 1.0."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["BUY", "SELL", "HOLD"],
                "description": "The recommended trading action",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence score 0.0-1.0 (0.7+ = strong signal)",
            },
            "rationale": {
                "type": "string",
                "description": "2-3 sentence explanation of the recommendation",
            },
            "supporting_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Technical indicators or data points supporting the recommendation",
            },
            "risk_factors": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Risks or conditions that could invalidate the recommendation",
            },
            "suggested_entry": {
                "type": ["number", "null"],
                "description": "Suggested entry price, or null if not applicable",
            },
            "suggested_stop": {
                "type": ["number", "null"],
                "description": "Suggested stop-loss price, or null if not applicable",
            },
            "suggested_target": {
                "type": ["number", "null"],
                "description": "Suggested profit target price, or null if not applicable",
            },
        },
        "required": ["action", "confidence", "rationale", "supporting_signals", "risk_factors"],
    },
}
