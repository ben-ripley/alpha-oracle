---
title: Modules
nav_order: 4
parent: Developer Guide
has_children: true
---

# Modules

This section provides deep-dive documentation for each backend module in `src/`. Each module has a well-defined responsibility and communicates with other modules via Redis pub/sub or direct function calls within the modular monolith.

## In This Section

- [Core](core.md) — Pydantic domain models, abstract interfaces, config loading, async database client, and Redis connection management
- [Data Ingestion](data-ingestion.md) — Multi-source data pipeline: IBKR/AlphaVantage market feeds, OHLCV bars, SEC filings, fundamental data, and alternative data (insider trades, short interest)
- [Strategy Engine](strategy-engine.md) — Strategy registration, backtesting, walk-forward validation, composite ranking, regime detection, and Monte Carlo simulation
- [ML Pipeline](ml-pipeline.md) — Feature store (50+ point-in-time features), XGBoost training, walk-forward validation, confidence calibration, drift monitoring, and model registry
- [Execution Engine](execution-engine.md) — Half-Kelly position sizing, smart order routing (market/limit/TWAP), broker adapter integration, and execution quality tracking
- [Risk Management](risk-management.md) — PDT guard, pre-trade checks, circuit breakers, kill switch, autonomy validator, and LLM guardrails
- [Scheduling](scheduling.md) — APScheduler cron jobs for daily bars, weekly fundamentals, biweekly alt data, weekly retraining, sentiment, and daily briefing; idempotent via Redis
- [API Layer](api.md) — FastAPI REST routes, WebSocket broadcasting via Redis pub/sub, and dependency injection patterns
- [Agents](agents.md) — Claude-powered advisory agents (Analyst, Advisor, Briefing), cost tracking, rate limiting, and response caching
- [Monitoring](monitoring.md) — Prometheus metrics, Grafana dashboards, Slack/Telegram alerts, and structured logging via structlog
