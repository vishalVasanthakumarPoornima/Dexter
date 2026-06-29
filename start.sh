#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

BACKEND_HOST="${DEXTER_BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${DEXTER_BACKEND_PORT:-8000}"
FRONTEND_HOST="${DEXTER_FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${DEXTER_FRONTEND_PORT:-5173}"
BACKEND_URL="http://${BACKEND_HOST}:${BACKEND_PORT}/status"
FRONTEND_URL="http://${FRONTEND_HOST}:${FRONTEND_PORT}"
LOG_DIR="${ROOT_DIR}/logs/dev"
BUNDLED_NODE="/Users/vasanth/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
NODE_BIN="${DEXTER_NODE_BIN:-}"

PIDS=()

is_up() {
  curl -fsS --max-time 2 "$1" >/dev/null 2>&1
}

cleanup() {
  if [ "${#PIDS[@]}" -gt 0 ]; then
    echo
    echo "Stopping Dexter dev services..."
    kill "${PIDS[@]}" >/dev/null 2>&1 || true
    wait "${PIDS[@]}" >/dev/null 2>&1 || true
  fi
}

trap cleanup INT TERM EXIT

mkdir -p "$LOG_DIR"

if [ -z "$NODE_BIN" ] && [ -x "$BUNDLED_NODE" ]; then
  NODE_BIN="$BUNDLED_NODE"
elif [ -z "$NODE_BIN" ] && command -v node >/dev/null 2>&1; then
  NODE_BIN="$(command -v node)"
fi

echo "Starting Dexter..."

if is_up "$BACKEND_URL"; then
  echo "Backend already running: ${BACKEND_URL}"
else
  if [ ! -x "${ROOT_DIR}/.venv/bin/python" ]; then
    echo "Missing Python virtualenv at .venv. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
  fi

  echo "Starting backend on http://${BACKEND_HOST}:${BACKEND_PORT}"
  (
    cd "$ROOT_DIR"
    exec .venv/bin/python -m uvicorn backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ) >"${LOG_DIR}/backend.log" 2>&1 &
  PIDS+=("$!")
fi

if is_up "$FRONTEND_URL"; then
  echo "Frontend already running: ${FRONTEND_URL}"
else
  if [ ! -d "${ROOT_DIR}/frontend/dashboard/node_modules" ]; then
    echo "Missing frontend dependencies. Run: cd frontend/dashboard && npm install"
    exit 1
  fi
  if [ -z "$NODE_BIN" ] || [ ! -x "$NODE_BIN" ]; then
    echo "Could not find a usable Node.js binary. Set DEXTER_NODE_BIN=/path/to/node."
    exit 1
  fi

  echo "Starting frontend on ${FRONTEND_URL}"
  (
    cd "${ROOT_DIR}/frontend/dashboard"
    exec "$NODE_BIN" node_modules/vite/bin/vite.js --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) >"${LOG_DIR}/frontend.log" 2>&1 &
  PIDS+=("$!")
fi

for _ in {1..30}; do
  if is_up "$BACKEND_URL" && is_up "$FRONTEND_URL"; then
    break
  fi
  sleep 1
done

if ! is_up "$BACKEND_URL"; then
  echo "Backend did not become ready. See ${LOG_DIR}/backend.log"
  exit 1
fi

if ! is_up "$FRONTEND_URL"; then
  echo "Frontend did not become ready. See ${LOG_DIR}/frontend.log"
  exit 1
fi

echo
echo "Dexter is ready:"
echo "  Frontend: ${FRONTEND_URL}"
echo "  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "  Logs:     ${LOG_DIR}"

if [ "${#PIDS[@]}" -eq 0 ]; then
  exit 0
fi

echo
echo "Press Ctrl-C to stop services started by this script."
wait "${PIDS[@]}"
