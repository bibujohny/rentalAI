#!/bin/zsh
set -euo pipefail

# Clear simple caches and compiled files

BASE_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
cd "$BASE_DIR"

# Remove sqlite db cache-journal if exists (not the DB itself)
find rentalai -name "*.pyc" -delete || true
find rentalai -name "__pycache__" -type d -exec rm -rf {} + || true

# Clear news in-memory cache requires restart; stop/start for full effect
if [[ -f .server.pid ]]; then
  echo "[clear_cache] Restarting server to reset in-memory caches"
  scripts/stop.sh
  scripts/start.sh bg
else
  echo "[clear_cache] Caches cleared (pyc). Restart server to reset in-memory caches."
fi
