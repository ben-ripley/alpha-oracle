#!/usr/bin/env bash
# restart-frontend.sh — Restart the Vite dev server
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Restarting frontend..."
"$SCRIPT_DIR/stop-frontend.sh"
sleep 1
"$SCRIPT_DIR/start-frontend.sh"
