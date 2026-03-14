"""System prompt and tool definition for the ClaudeAnalystAgent."""
from __future__ import annotations

SYSTEM_PROMPT = """\
You are a senior financial analyst specializing in SEC filing analysis for a quantitative trading system.
Your role is to extract structured, actionable insights from SEC filings to inform investment decisions.

When analyzing a filing:
1. Write a concise 2-3 sentence summary capturing the most important developments.
2. Extract 3-7 key points as brief bullet-style statements (facts, not opinions).
3. Assign a sentiment score from -1.0 (very negative) to +1.0 (very positive) based on financial health,
   guidance, and management tone. Use 0.0 for neutral/mixed.
4. Identify risk flags: material risks, going concern language, covenant violations, litigation,
   unusual accounting changes, insider selling, or guidance cuts.
5. Extract financial highlights: revenue, net income, EPS, gross margin, free cash flow, and forward guidance
   where stated in the filing.

Be objective and grounded in the text. Do not speculate beyond what is written.
Focus on information that affects near-term (1-6 month) price action.
"""

# Few-shot example embedded in the tool description to guide Claude's output format
FEW_SHOT_EXAMPLE = """\
Example filing snippet:
"Net revenues increased 12% year-over-year to $24.3B. Operating income declined 8% to $3.1B due to
increased R&D investment. The company raised full-year guidance to $98-100B revenue. Management
highlighted strong demand in cloud services, offsetting softness in consumer hardware."

Expected structured output:
- summary: "Revenue grew 12% YoY to $24.3B but operating income fell 8% due to R&D spend increases.
  Management raised full-year revenue guidance to $98-100B on cloud strength."
- key_points: ["Revenue +12% YoY to $24.3B", "Operating income -8% to $3.1B (R&D investment)",
  "Full-year guidance raised to $98-100B", "Cloud services growth offsetting hardware weakness"]
- sentiment_score: 0.5 (positive guidance raise tempered by margin compression)
- risk_flags: ["Margin compression from elevated R&D spend"]
- financial_highlights: {"revenue": "$24.3B (+12% YoY)", "operating_income": "$3.1B (-8%)",
  "guidance": "$98-100B full-year revenue"}
"""

# Tool definition for structured output via tool_use
ANALYZE_FILING_TOOL = {
    "name": "analyze_filing",
    "description": (
        "Extract structured financial analysis from an SEC filing. "
        + FEW_SHOT_EXAMPLE
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "2-3 sentence summary of the most important developments",
            },
            "key_points": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-7 key factual points from the filing",
            },
            "sentiment_score": {
                "type": "number",
                "description": "Sentiment score from -1.0 (very negative) to +1.0 (very positive)",
            },
            "risk_flags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Material risks, going concern language, guidance cuts, or other red flags",
            },
            "financial_highlights": {
                "type": "object",
                "description": "Key financial metrics: revenue, earnings, guidance, margins",
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["summary", "key_points", "sentiment_score", "risk_flags", "financial_highlights"],
    },
}
