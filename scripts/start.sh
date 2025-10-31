#!/bin/zsh
set -euo pipefail

# Start RentalAI server (foreground by default). Use 'bg' or '-b' for background.
# Loads .env if present, creates venv, installs deps.

BASE_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$BASE_DIR"

# Python venv
if [[ ! -d .venv ]]; then
  echo "[start] Creating virtual environment .venv"
  python3 -m venv .venv
fi
source .venv/bin/activate

# Dependencies
pip install -q -r requirements.txt

# Load env
if [[ -f .env ]]; then
  echo "[start] Loading .env"
  set -a; source .env; set +a
fi

MODE="${1:-fg}"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

if [[ "$MODE" == "bg" || "$MODE" == "-b" ]]; then
  echo "[start] Starting server in background..."
  nohup python3 run.py > "$LOG_DIR/server.log" 2>&1 &
  echo $! > .server.pid
  echo "[start] PID $(cat .server.pid). Logs: $LOG_DIR/server.log"
else
  echo "[start] Starting server in foreground... (Ctrl+C to exit)"
  python3 run.py
fi
