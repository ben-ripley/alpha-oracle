# ADR-007: Architecture - Modular Monolith

**Status:** Accepted

**Decision:** Modular monolith with event-driven communication, deployed as Docker Compose.

```
┌─────────────────────────────────────────────────────┐
│                 Docker Compose Stack                  │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────┐│
│  │   Data   │  │ Strategy │  │Execution │  │ Risk ││
│  │ Ingestion│──│  Engine  │──│  Engine  │──│ Mgr  ││
│  │  Module  │  │  Module  │  │  Module  │  │Module││
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──┬───┘│
│       └──────────────┴──────────────┴──────────┘    │
│                      Redis (Event Bus + Cache)       │
│                          │                           │
│  ┌────────────┐  ┌──────┴──────┐  ┌──────────────┐ │
│  │TimescaleDB │  │   DuckDB    │  │ Prometheus + │ │
│  │(time-series)│ │ (analytics) │  │   Grafana    │ │
│  └────────────┘  └─────────────┘  └──────────────┘ │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │     AI Agent Layer (LangGraph + Claude)       │   │
│  │  Analyst Agent | Risk Assessor | HITL Gateway │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Why not microservices:** Massive operational overhead for a solo developer. Modules communicate via Redis pub/sub for real-time events and direct calls for synchronous ops (risk checks). Clean interfaces enforced by abstract base classes.
