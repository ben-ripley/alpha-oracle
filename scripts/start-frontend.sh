#!/usr/bin/env bash
# start-frontend.sh — Start the Vite dev server (React dashboard, port 3000)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_ROOT/.pids"
PID_FILE="$PID_DIR/frontend.pid"
LOG_FILE="$PROJECT_ROOT/logs/frontend.log"

mkdir -p "$PID_DIR" "$(dirname "$LOG_FILE")"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Frontend is already running (PID $OLD_PID)"
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

echo "Starting frontend (Vite dev server)..."
cd "$PROJECT_ROOT/web"
nohup npm run dev > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"
echo "Frontend started (PID $(cat "$PID_FILE")) — http://localhost:3000"
echo "Logs: $LOG_FILE"
