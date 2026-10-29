#!/usr/bin/env bash
# Stop both Youtube Card Reader servers.
BACKEND_PORT="${YCR_BACKEND_PORT:-8420}"
FRONTEND_PORT="${YCR_FRONTEND_PORT:-15273}"
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  pids=$(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill 2>/dev/null && echo "✓ stopped :$port"
  else
    echo "· nothing listening on :$port"
  fi
done
