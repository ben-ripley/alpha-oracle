#!/usr/bin/env bash
# stop-all.sh — Stop frontend (Vite) and backend (FastAPI + optionally Docker infra)
#               Pass --all to also stop Docker infra services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/stop-frontend.sh"
"$SCRIPT_DIR/stop-backend.sh" "${1:-}"
