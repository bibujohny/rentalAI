#!/bin/zsh
set -euo pipefail

# Stop RentalAI server running on port 5000 or using saved PID

BASE_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$BASE_DIR"

if [[ -f .server.pid ]]; then
  PID=$(cat .server.pid)
  if kill -0 "$PID" 2>/dev/null; then
    echo "[stop] Stopping PID $PID"
    kill "$PID" || true
  fi
  rm -f .server.pid
fi

# Fallback: kill any python processes listening on :5000
PIDS=($(lsof -ti tcp:5000 || true))
if [[ ${#PIDS[@]} -gt 0 ]]; then
  echo "[stop] Killing processes on :5000 -> ${PIDS[*]}"
  kill ${PIDS[@]} || true
fi

echo "[stop] Done."
