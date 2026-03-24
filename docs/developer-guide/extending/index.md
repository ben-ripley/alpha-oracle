---
title: Extending
nav_order: 7
parent: Developer Guide
has_children: true
---

# Extending

This section covers how to add new functionality to the alpha-oracle system. All extension points follow the abstract interface pattern defined in `src/core/interfaces.py` — implement the interface, register the implementation, and the rest of the system picks it up automatically.

## In This Section

- [Writing a Custom Strategy](custom-strategy.md) — Implement the `BaseStrategy` interface to add a new buy/sell signal generator, with backtesting and PDT-compliant hold periods
- [Writing a Custom Data Adapter](custom-data-adapter.md) — Implement `DataSourceInterface` to connect a new market data source (API, file, or database)
- [Adding API Routes](adding-api-routes.md) — Add new FastAPI endpoints following the project's router and dependency injection patterns
