# Docker Compose Infrastructure

The system uses Docker Compose to orchestrate five core services: [TimescaleDB](../glossary.md#timescaledb), [Redis](../glossary.md#redis), the FastAPI backend, Prometheus, and Grafana. All services are defined in `docker-compose.yml` at the project root.

## Services

### timescaledb

**Image:** `timescale/timescaledb:latest-pg16`
**Port:** `5432`
**Purpose:** Primary time-series database for OHLCV bars, fundamentals, trades, orders, portfolio snapshots, signals, risk events, and backtest results.

**Configuration:**
- Database: `stock_analysis`
- User: `trader`
- Password: `${POSTGRES_PASSWORD:-dev_password}` (defaults to `dev_password` if not set in environment)

**Volumes:**
- `timescale_data:/home/postgres/pgdata/data` — persistent storage
- `./scripts/init_db.sql:/docker-entrypoint-initdb.d/init.sql` — initialization script (creates tables and hypertables on first run)

**Health Check:**
- Command: `pg_isready -U trader -d stock_analysis`
- Interval: 10 seconds
- Timeout: 5 seconds
- Retries: 5

The database is initialized automatically on first startup using `init_db.sql`, which creates all tables as [hypertables](../glossary.md#hypertable) and sets up indexes.

---

### redis

**Image:** `redis:7-alpine`
**Port:** `6379`
**Purpose:** In-memory cache for rate limiting, PDT tracking, job idempotency, pub/sub event bus for real-time updates.

**Configuration:**
- Max memory: `256MB`
- Eviction policy: `allkeys-lru` (least recently used)

**Volumes:**
- `redis_data:/data` — persistent storage (AOF/RDB snapshots)

**Health Check:**
- Command: `redis-cli ping`
- Interval: 10 seconds
- Timeout: 5 seconds
- Retries: 5

Redis is configured with an LRU eviction policy to automatically drop old cache entries when memory is full. See [Redis Keys Reference](redis-keys.md) for the complete key schema.

---

### api

**Image:** Built from `Dockerfile` in project root
**Port:** `8000`
**Purpose:** FastAPI application serving REST API endpoints and WebSocket for real-time updates.

**Dependencies:**
- `timescaledb` (waits for healthy status)
- `redis` (waits for healthy status)

**Environment Variables:**
- `SA_DATABASE__URL`: PostgreSQL connection string (uses Docker network hostname `timescaledb`)
- `SA_REDIS__URL`: Redis connection string (uses Docker network hostname `redis`)
- `SA_ALPACA_API_KEY`: Alpaca API key (optional, deprecated)
- `SA_ALPACA_SECRET_KEY`: Alpaca secret key (optional, deprecated)
- `SA_BROKER__PAPER_TRADING`: Paper trading mode flag (default `"true"`)
- `SA_ALPHA_VANTAGE_API_KEY`: Alpha Vantage API key for historical data backfill

All `SA_*` environment variables can be overridden via `.env` file or shell exports.

**Volumes (Hot Reload):**
- `./src:/app/src` — source code (changes trigger uvicorn auto-reload in development)
- `./config:/app/config` — YAML configuration files
- `./scripts:/app/scripts` — utility scripts
- `parquet_data:/app/data` — persistent Parquet feature store

The API service mounts source directories as volumes to enable hot-reload during development. Changes to Python files are automatically detected by uvicorn.

---

### prometheus

**Image:** `prom/prometheus:v2.48.1`
**Port:** `9090`
**Purpose:** Metrics collection and time-series storage for monitoring.

**Volumes:**
- `./config/prometheus.yml:/etc/prometheus/prometheus.yml` — Prometheus configuration
- `prometheus_data:/prometheus` — persistent metrics storage

Prometheus scrapes the FastAPI `/metrics` endpoint (exposed by the `prometheus-fastapi-instrumentator` library) every 15 seconds. Metrics include request latency, order submission counts, risk check results, and custom business metrics.

---

### grafana

**Image:** `grafana/grafana:10.2.3`
**Port:** `3001` (mapped from container port 3000)
**Purpose:** Visualization and alerting dashboard for system metrics.

**Configuration:**
- Admin password: `${GRAFANA_PASSWORD:-admin}` (defaults to `admin`)
- Installed plugins: `grafana-clock-panel`

**Volumes:**
- `grafana_data:/var/lib/grafana` — persistent dashboards and settings
- `./config/grafana/provisioning:/etc/grafana/provisioning` — pre-configured data sources and dashboards

**Dependencies:**
- `prometheus` (Grafana reads from Prometheus as its data source)

Grafana is pre-configured with Prometheus as a data source via the provisioning directory. Access the Grafana UI at `http://localhost:3001` (default credentials: `admin` / `admin`).

---

## Named Volumes

All volumes are managed by Docker and persist data across container restarts:

| Volume | Purpose |
|--------|---------|
| `timescale_data` | TimescaleDB database files |
| `redis_data` | Redis AOF/RDB snapshots |
| `prometheus_data` | Prometheus time-series metrics |
| `grafana_data` | Grafana dashboards and settings |
| `parquet_data` | Feature store Parquet files |

To reset all data:
```bash
docker compose down -v  # WARNING: destroys all volumes
```

---

## Starting the Stack

```bash
# Start all services in background
docker compose up -d

# View logs
docker compose logs -f

# Check service status
docker compose ps

# Stop services (keeps data)
docker compose down

# Stop and remove all data
docker compose down -v
```

For routine development, use the helper scripts:
- `./scripts/start-backend.sh` — starts Docker services + FastAPI
- `./scripts/stop-backend.sh --all` — stops FastAPI + Docker services

See [Deployment](../operations/deployment.md) for production setup.

---

<!-- DIAGRAM: Docker Compose architecture showing service dependencies and volume mounts -->
