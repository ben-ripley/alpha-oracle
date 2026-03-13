# Developer Guide

Welcome to the **stock-analysis** Developer Guide. This documentation is for developers and contributors who want to understand the system architecture, set up a local development environment, extend functionality, or contribute to the project.

## What This Guide Covers

This guide provides technical documentation for:

- **Getting Started**: Prerequisites, local setup, and running tests
- **Architecture**: System design, data flows, and module organization
- **Module Reference**: Detailed documentation for each subsystem (data, strategy, execution, risk, ML)
- **Infrastructure**: Docker services, database schema, Redis pub/sub patterns
- **Frontend**: React dashboard architecture, WebSocket integration, component structure
- **Operations**: Deployment, monitoring, troubleshooting, and production configuration
- **Extending**: Writing custom strategies, data adapters, risk managers, and backtest engines
- **ADRs**: Architecture Decision Records documenting key design choices

## Project Overview

**stock-analysis** is an AI-driven automated stock trading system designed for retail investors with accounts under $25K. It focuses on swing and position trading (no day trading) to comply with FINRA Pattern Day Trader (PDT) rules.

### Key Features

- **Data Pipeline**: Multi-source ingestion from IBKR, Alpha Vantage, SEC EDGAR, and FINRA
- **Strategy Engine**: Pluggable strategy framework with 3 builtin strategies and ML-powered signal generation
- **Risk Management**: Multi-layer risk checks including PDT guard, position limits, and circuit breakers
- **Smart Execution**: Intelligent order routing (market/limit/TWAP) with execution quality tracking
- **ML Pipeline**: XGBoost-based prediction with 50+ point-in-time features and model monitoring
- **Dashboard**: Real-time React UI with portfolio, strategy, risk, and ML monitoring views

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy async, Pydantic |
| **Databases** | TimescaleDB (time-series), DuckDB (analytics), Redis (cache/pub-sub) |
| **Frontend** | React 18, TypeScript, TailwindCSS, Vite, Recharts |
| **ML** | XGBoost, scikit-learn, Optuna (hyperparameter tuning) |
| **Broker** | Interactive Brokers (IBKR) via ib-async |
| **Observability** | Prometheus (metrics), Grafana (dashboards), structlog (logging) |
| **Orchestration** | APScheduler (cron jobs), Redis pub/sub (events) |
| **Testing** | pytest, pytest-asyncio, hypothesis (property tests) |

## Navigation

### Getting Started

1. [Prerequisites](getting-started/prerequisites.md) — System requirements and tools
2. [Local Development Setup](getting-started/local-setup.md) — Clone, install, and run
3. [Running Tests](getting-started/running-tests.md) — Test suite organization and execution

### Architecture

1. [Overview](architecture/overview.md) — Modular monolith design and core interfaces
2. [Data Flows](architecture/data-flows.md) — Signal generation, order execution, and risk cascade
3. [Module Map](architecture/module-map.md) — Full directory structure with descriptions

### Module Reference

Detailed documentation for each subsystem (see [Module Reference](modules/index.md)):

- **Core**: Models, interfaces, config, database, Redis
- **Data**: Adapters, feeds, storage, universe management
- **Strategy**: Engine, backtesting, builtin strategies, ranking
- **Signals**: Feature store, ML pipeline, model monitoring
- **Scheduling**: Cron jobs for data ingestion and model retraining
- **Execution**: Smart router, broker adapters, order generation
- **Risk**: PDT guard, pre-trade checks, circuit breakers, kill switch
- **API**: FastAPI routes, WebSocket, dependencies
- **Monitoring**: Prometheus metrics, alert manager

### Infrastructure

- Database schema (TimescaleDB hypertables, DuckDB views)
- Redis pub/sub channels and cache keys
- Docker Compose services and networking
- Prometheus metrics and Grafana dashboards

### Frontend

- React component architecture
- WebSocket integration for real-time updates
- Dashboard page structure (Portfolio, Strategies, Risk, Trades, ML)
- Styling conventions (dark terminal aesthetic)

### Operations

- Configuration management (YAML + env vars)
- Deployment strategies (Docker, systemd)
- Monitoring and alerting
- Backup and recovery
- Troubleshooting common issues

### Extending

- Writing custom strategies (BaseStrategy interface)
- Adding data sources (DataSourceInterface)
- Implementing risk managers (RiskManager interface)
- Creating backtest engines (BacktestEngine interface)

### Architecture Decision Records

See [ADRs](adrs.md) for detailed context on key architectural choices:

- [ADR-001: Trading Platform Selection](../specs/adrs/001-trading-platform.md)
- [ADR-002: Market Data Strategy](../specs/adrs/002-market-data-strategy.md)
- [ADR-003: ML Model Architecture](../specs/adrs/003-ml-model-architecture.md)
- [ADR-004: Alternative Data Sources](../specs/adrs/004-alternative-data.md)
- [ADR-005: Backtesting Framework](../specs/adrs/005-backtesting.md)
- [ADR-006: Technology Stack](../specs/adrs/006-technology-stack.md)
- [ADR-007: System Architecture](../specs/adrs/007-architecture.md)
- [ADR-008: LLM Agent Integration](../specs/adrs/008-llm-agent-integration.md)
- [ADR-009: Risk Management](../specs/adrs/009-risk-management.md)
- [ADR-010: IBKR Broker Switch](../specs/adrs/010-ibkr-broker-switch.md)

## Quick Links

- [User Guide](../user-guide/index.md) — For traders and operators
- [Glossary](../glossary.md) — Technical terms and acronyms
- [API Reference](../api-reference.md) — REST and WebSocket endpoints
- [GitHub Repository](https://github.com/yourusername/stock-analysis)

## Contributing

Contributions are welcome! Please read the [Contributing Guide](../CONTRIBUTING.md) for:

- Code style and conventions (Ruff, mypy)
- Testing requirements (pytest, coverage)
- Pull request process
- Issue reporting guidelines

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/stock-analysis/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/stock-analysis/discussions)
- **Security**: See [SECURITY.md](../SECURITY.md) for reporting vulnerabilities
