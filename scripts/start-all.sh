#!/usr/bin/env bash
# start-all.sh — Start backend (Docker infra + FastAPI) and frontend (Vite)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/start-backend.sh"
"$SCRIPT_DIR/start-frontend.sh"
