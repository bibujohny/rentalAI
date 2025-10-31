#!/bin/bash
set -euo pipefail

APP_BASE="/opt/rentalai"
APP_DIR="$APP_BASE/app"
SERVICE_NAME="rentalai"
SYSTEMCTL="$(command -v systemctl || echo /usr/bin/systemctl)"
LOG_DIR="$APP_DIR/logs"
GUNICORN_CMD="$APP_DIR/.venv/bin/gunicorn -w 3 -k gthread --threads 4 -b 127.0.0.1:8000 wsgi:app"
FALLBACK_PID_FILE="$APP_DIR/.gunicorn.pid"

mkdir -p "$LOG_DIR"

echo "[deploy] Fetch latest code"
if [[ ! -d "$APP_DIR/.git" ]]; then
  echo "[deploy] First-time clone into $APP_DIR"
  sudo mkdir -p "$APP_BASE" || true
  sudo chown -R "$USER":www-data "$APP_BASE" || true
  git clone "https://github.com/bibujohny/rentalAI.git" "$APP_DIR"
fi

cd "$APP_DIR"
git fetch --all --prune
git reset --hard origin/main
echo "[deploy] Now at commit: $(git rev-parse --short HEAD)"

# Python env
if [[ ! -d .venv ]]; then
  echo "[deploy] Creating venv"
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

# DB migrations (safe)
echo "[deploy] Applying migrations (if any)"
python3 - <<'PY'
from app import create_app
try:
    from flask_migrate import upgrade
except Exception:
    print("Flask-Migrate not installed; skipping upgrade")
    raise SystemExit(0)
app = create_app()
with app.app_context():
    try:
        upgrade()
        print("Applied migrations (if any).")
    except Exception as e:
        print("Migrate skipped or failed:", e)
PY

# Try systemd restart (non-interactive)
echo "[deploy] Restarting systemd service: ${SERVICE_NAME}"
set +e
sudo -n "$SYSTEMCTL" restart "$SERVICE_NAME" 2> "$LOG_DIR/systemctl.err"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "[deploy] systemctl restart failed (non-interactive). Falling back to user-level restart."
  echo "[deploy] systemctl stderr:"
  cat "$LOG_DIR/systemctl.err" || true

  # Kill any existing user-level gunicorn for this app
  pkill -f "gunicorn .* wsgi:app" 2>/dev/null || true
  sleep 1

  echo "[deploy] Starting gunicorn (user-level fallback)"
  nohup $GUNICORN_CMD > "$LOG_DIR/gunicorn.log" 2>&1 &
  echo $! > "$FALLBACK_PID_FILE"
fi

# Verify with retries
echo "[deploy] Verifying service at http://127.0.0.1:8000/"
ATTEMPTS=12
SLEEP=2
for i in $(seq 1 $ATTEMPTS); do
  if curl -fsS -I http://127.0.0.1:8000/ >/dev/null; then
    echo "[deploy] OK"
    exit 0
  fi
  echo "[deploy] Attempt $i/$ATTEMPTS failed; retrying in ${SLEEP}s..."
  sleep $SLEEP
done

echo "[deploy] ERROR: App did not respond on 127.0.0.1:8000 after $((ATTEMPTS*SLEEP))s"
echo "[deploy] Last 100 lines of gunicorn.log (if any):"
tail -n 100 "$LOG_DIR/gunicorn.log" || true
exit 1
