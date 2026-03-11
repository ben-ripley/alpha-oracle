#!/usr/bin/env bash
# stop-backend.sh — Stop the FastAPI dev server (leaves Docker infra running)
#                   Pass --all to also stop Docker infra services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_ROOT/.pids/backend.pid"

# --- uvicorn API ---
if [[ ! -f "$PID_FILE" ]]; then
  echo "Backend API is not running (no PID file found)"
else
  PID=$(cat "$PID_FILE")
  if kill -0 "$PID" 2>/dev/null; then
    echo "Stopping backend API (PID $PID)..."
    kill "$PID"
    rm -f "$PID_FILE"
    echo "Backend API stopped"
  else
    echo "Backend API process (PID $PID) not found — cleaning up stale PID file"
    rm -f "$PID_FILE"
  fi
fi

# --- Docker infra (optional) ---
if [[ "${1:-}" == "--all" ]]; then
  echo "Stopping Docker infra..."
  cd "$PROJECT_ROOT"
  docker compose stop timescaledb redis prometheus grafana
  echo "Docker infra stopped"
fi
