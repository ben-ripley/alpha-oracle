# ADR-006: Technology Stack

**Status:** Accepted

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Finance/ML ecosystem dominance |
| Web UI | TypeScript + React + TailwindCSS | Dashboard for portfolio, strategies, risk. Phase 1-2. |
| API layer | FastAPI (Python) | REST API serving the React frontend + WebSocket for real-time updates |
| Data processing | Pandas + Polars (large datasets) | Compatibility + performance |
| Analytics DB | DuckDB (embedded) | Zero-ops queries on Parquet files |
| Time-series DB | TimescaleDB (PostgreSQL ext) | SQL-compatible, hypertables |
| Cache/Queue | Redis | Rate limiting, signal cache, event pub/sub |
| ML - tabular | XGBoost + scikit-learn | Best for financial tabular data |
| ML - deep learning | PyTorch (Phase 3 only) | LSTM/Transformer if XGBoost insufficient |
| ML - NLP | HuggingFace FinBERT | Pre-trained financial sentiment |
| LLM | Claude API (Anthropic) | Document analysis, decision support |
| Agent framework | LangGraph | Stateful workflows, human-in-the-loop |
| Orchestration | Prefect | Python-native, easier than Airflow for solo dev |
| Monitoring | Prometheus + Grafana | Industry standard |
| Alerting | Grafana Alerts + Slack/Telegram | Real-time notifications |
| Containers | Docker Compose | Single-node, sufficient for retail |
| Config | Pydantic Settings + YAML | Type-safe with env overrides |
| Testing | pytest + hypothesis | Property-based testing for financial logic |
