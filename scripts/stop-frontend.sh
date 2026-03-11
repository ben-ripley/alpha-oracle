#!/usr/bin/env bash
# stop-frontend.sh — Stop the Vite dev server
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_ROOT/.pids/frontend.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Frontend is not running (no PID file found)"
  exit 0
fi

PID=$(cat "$PID_FILE")
if kill -0 "$PID" 2>/dev/null; then
  echo "Stopping frontend (PID $PID)..."
  kill "$PID"
  rm -f "$PID_FILE"
  echo "Frontend stopped"
else
  echo "Frontend process (PID $PID) not found — cleaning up stale PID file"
  rm -f "$PID_FILE"
fi
