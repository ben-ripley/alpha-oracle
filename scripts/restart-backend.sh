#!/usr/bin/env bash
# restart-backend.sh — Restart the FastAPI dev server (and optionally Docker infra)
#                      Pass --all to also restart Docker infra services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting backend..."
if [[ "${1:-}" == "--all" ]]; then
  "$SCRIPT_DIR/stop-backend.sh" --all
  sleep 2
else
  "$SCRIPT_DIR/stop-backend.sh"
  sleep 1
fi
"$SCRIPT_DIR/start-backend.sh"
