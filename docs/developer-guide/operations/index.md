---
title: Operations
nav_order: 6
parent: Developer Guide
has_children: true
---

# Operations

This section covers operational tasks for running and maintaining alpha-oracle in development and production environments — from initial data loading to deployment configurations and incident response.

## In This Section

- [Deployment](deployment.md) — Development, paper trading, and live trading deployment modes; environment variables, Docker Compose configuration, and production checklist
- [Data Backfill](backfill-data.md) — One-time historical OHLCV backfill via `backfill_history.py` (Alpha Vantage), resume support, and rate limiting considerations
- [Runbook: LLM Agents](runbook-agents.md) — Operational procedures for monitoring agent costs, managing rate limits, disabling agents, and clearing the response cache
- [Troubleshooting](troubleshooting.md) — Common issues and solutions for backend connectivity, database errors, broker connections, and frontend problems
