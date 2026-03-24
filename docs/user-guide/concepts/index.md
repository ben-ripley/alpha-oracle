---
title: Concepts
nav_order: 6
parent: User Guide
has_children: true
---

# Concepts

This section explains the core ideas behind how AlphaOracle works — from regulatory rules and risk controls to the trading strategies and AI models that drive decisions.

## In This Section

- [PDT Rule](pdt-rule.md) — The FINRA Pattern Day Trader regulation, why it matters for accounts under $25K, and how the system enforces it automatically
- [Risk Management](risk-management.md) — The four-layer risk control system (position limits, portfolio limits, circuit breakers, and LLM guardrails) that every order passes through
- [Autonomy Modes](autonomy-modes.md) — The four operating modes (PAPER_ONLY through FULL_AUTONOMOUS) and how to progress between them safely
- [Trading Strategies](strategies-explained.md) — The three built-in swing trading strategies and how they generate buy/sell signals
- [ML Signal Intelligence](ml-signals.md) — How the XGBoost model learns from 50+ features to predict 5-day price movements
- [LLM Agents](llm-agents.md) — The three Claude-powered advisory agents (Analyst, Advisor, Briefing) and their advisory-only role in the system
- [Full Autonomous Mode](full-autonomous.md) — Requirements, safeguards, and what to expect when enabling fully autonomous trading
