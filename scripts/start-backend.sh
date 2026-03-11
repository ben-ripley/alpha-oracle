#!/usr/bin/env bash
# start-backend.sh — Start Docker infra (TimescaleDB, Redis, Prometheus, Grafana)
#                    then start the FastAPI dev server (uvicorn, port 8000)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_ROOT/.pids"
PID_FILE="$PID_DIR/backend.pid"
LOG_FILE="$PROJECT_ROOT/logs/backend.log"

mkdir -p "$PID_DIR" "$(dirname "$LOG_FILE")"

# --- Docker infra ---
echo "Starting Docker infra (timescaledb, redis, prometheus, grafana)..."
cd "$PROJECT_ROOT"
docker compose up -d timescaledb redis prometheus grafana

echo "Waiting for TimescaleDB and Redis to be healthy..."
docker compose wait timescaledb redis 2>/dev/null || sleep 5

# --- uvicorn API ---
if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Backend API is already running (PID $OLD_PID)"
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

echo "Starting FastAPI (uvicorn)..."
cd "$PROJECT_ROOT"
nohup python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000 > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Backend API started (PID $(cat "$PID_FILE")) — http://localhost:8000"
echo "Logs: $LOG_FILE"
