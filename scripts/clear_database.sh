#!/usr/bin/env bash
# clear_database.sh — Remove all seed/demo data from Redis to prepare for real data.
#
# Targets the exact key patterns written by scripts/seed_demo_data.py:
#   execution:trade_history, execution:trade_history:*, execution:pending_approvals
#   risk:pdt:trades
#   strategy:results:*, strategy:rankings
#   portfolio:history
#   circuit_breaker:heartbeat
#
# Usage:
#   ./scripts/clear_database.sh            # auto-detect Redis (Docker or localhost)
#   REDIS_HOST=localhost ./scripts/clear_database.sh
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-}"
REDIS_PORT="${REDIS_PORT:-6379}"

# Resolve redis-cli connection flags
redis_cmd() {
  if [[ -n "$REDIS_HOST" ]]; then
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" "$@"
  elif docker compose ps redis 2>/dev/null | grep -q "running\|Up"; then
    docker compose exec -T redis redis-cli "$@"
  else
    redis-cli -h localhost -p "$REDIS_PORT" "$@"
  fi
}

echo "Checking Redis connection..."
redis_cmd PING > /dev/null

echo ""
echo "Clearing seed/demo data from Redis..."

# Explicit keys
KEYS=(
  "execution:trade_history"
  "execution:pending_approvals"
  "risk:pdt:trades"
  "strategy:rankings"
  "portfolio:history"
  "circuit_breaker:heartbeat"
)

for key in "${KEYS[@]}"; do
  redis_cmd DEL "$key" > /dev/null
  echo "  deleted: $key"
done

# Pattern-matched keys (trade history per symbol, strategy results)
for pattern in "execution:trade_history:*" "strategy:results:*"; do
  mapfile -t matched < <(redis_cmd --scan --pattern "$pattern" 2>/dev/null || true)
  for key in "${matched[@]}"; do
    [[ -z "$key" ]] && continue
    redis_cmd DEL "$key" > /dev/null
    echo "  deleted: $key"
  done
done

echo ""
echo "Done. Redis is clean and ready for real data."
echo "Run 'docker compose restart api' (or restart-backend.sh) to pick up the empty state."
