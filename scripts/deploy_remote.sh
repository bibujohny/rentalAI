#!/bin/bash
set -euo pipefail

APP_BASE="/opt/rentalai"
APP_DIR="$APP_BASE/app"
PROJECT_DIR="$APP_DIR/rentalai"
SERVICE_NAME="rentalai"

# Ensure app exists (first-time bootstrap)
if [[ ! -d "$APP_DIR" ]]; then
  echo "[deploy] First-time setup at $APP_DIR"
  sudo mkdir -p "$APP_BASE"
  sudo chown -R "$USER":www-data "$APP_BASE"
  git clone https://github.com/bibujohny/rentalAI.git "$APP_DIR"
fi

cd "$APP_DIR"

echo "[deploy] Fetch latest code"
 git fetch --all --prune
 git reset --hard origin/main

cd "$PROJECT_DIR"

# Python env
if [[ ! -d .venv ]]; then
  echo "[deploy] Creating venv"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# DB migrations without relying on flask CLI
python3 - <<'PY'
from app import create_app
from app.models import db
from flask_migrate import upgrade
app = create_app()
with app.app_context():
    upgrade()
print('Applied migrations (if any).')
PY

# Restart service (expects systemd unit installed on server)
if command -v systemctl >/dev/null 2>&1; then
  echo "[deploy] Restarting systemd service: $SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
else
  echo "[deploy] systemctl not found. Please restart the app process manually."
fi

echo "[deploy] Done."
