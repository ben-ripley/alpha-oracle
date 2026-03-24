---
title: Infrastructure
nav_order: 5
parent: Developer Guide
has_children: true
---

# Infrastructure

This section documents the infrastructure services that the alpha-oracle system depends on. The full stack is orchestrated via Docker Compose and requires no manual service configuration for local development.

## In This Section

- [Docker Compose](docker-compose.md) — Service definitions for TimescaleDB, Redis, Prometheus, Grafana, and the FastAPI backend; startup, teardown, and port reference
- [Database Schema](database-schema.md) — TimescaleDB hypertable definitions, SQLAlchemy models, and query patterns for time-series data
- [IBKR Gateway Setup](ibkr-gateway.md) — Configuring IB Gateway or TWS for order execution and market data, including client ID scheme and connection troubleshooting
- [Redis Keys Reference](redis-keys.md) — Complete reference for all Redis namespaces used by the system (PDT tracking, pub/sub events, job idempotency, agent cache, autonomy state)
