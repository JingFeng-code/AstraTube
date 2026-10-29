#!/usr/bin/env bash
# Youtube Card Reader — one-shot start script (macOS / Linux).
# First run installs everything; later runs just start the two servers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_PORT="${YCR_BACKEND_PORT:-8420}"
FRONTEND_PORT="${YCR_FRONTEND_PORT:-15273}"
PY="${PYTHON:-python3}"

info()  { printf '\033[36m→\033[0m %s\n' "$1"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$1"; }
die()   { printf '\033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }

command -v "$PY" >/dev/null 2>&1 || die "Python 3.10+ not found. Install it from https://www.python.org/downloads/"
command -v npm  >/dev/null 2>&1 || die "Node.js (npm) not found. Install it from https://nodejs.org/"

# 1) Backend environment (first run only)
if [ ! -x "backend/.venv/bin/python" ]; then
  info "First run: creating the Python environment (3-8 minutes, it downloads the local speech-to-text model)…"
  ( cd backend && "$PY" -m venv .venv \
      && ./.venv/bin/python -m pip install --upgrade pip -q \
      && ./.venv/bin/python -m pip install -r requirements.txt -q ) \
    || die "Backend install failed. Check your network and run this script again."
  ok "Backend environment ready"
fi

# 2) Frontend packages (first run only)
if [ ! -d "frontend/node_modules" ]; then
  info "First run: installing frontend packages (1-2 minutes)…"
  ( cd frontend && npm install --silent ) || die "Frontend install failed."
  ok "Frontend packages ready"
fi

is_up() { curl -fsS --max-time 1 "http://127.0.0.1:$1/" >/dev/null 2>&1; }

# 3) Backend
if curl -fsS --max-time 1 "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
  ok "Backend already running on :$BACKEND_PORT"
else
  info "Starting backend on :$BACKEND_PORT…"
  ( cd backend && nohup ./.venv/bin/python -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" > /tmp/ycr-backend.log 2>&1 & )
fi

# 4) Frontend
if is_up "$FRONTEND_PORT"; then
  ok "Frontend already running on :$FRONTEND_PORT"
else
  info "Starting frontend on :$FRONTEND_PORT…"
  ( cd frontend && PORT="$FRONTEND_PORT" nohup npm run dev > /tmp/ycr-frontend.log 2>&1 & )
fi

# 5) Wait for the frontend, then open a browser
for _ in $(seq 1 60); do is_up "$FRONTEND_PORT" && break; sleep 0.5; done
is_up "$FRONTEND_PORT" || die "Frontend did not come up. See /tmp/ycr-frontend.log"

URL="http://127.0.0.1:$FRONTEND_PORT"
ok "Youtube Card Reader is running at $URL"
if command -v open >/dev/null 2>&1; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
fi

echo
echo "  Logs:  /tmp/ycr-backend.log  /tmp/ycr-frontend.log"
echo "  Stop:  ./scripts/stop.sh"
