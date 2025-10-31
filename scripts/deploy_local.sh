#!/bin/zsh
set -euo pipefail

# CI/CD helper to push local changes and trigger remote deploy over SSH.
# Usage: ./scripts/deploy_local.sh user@server-ip [/opt/rentalai]

REMOTE="${1:-}"
REMOTE_BASE="${2:-/opt/rentalai}"

if [[ -z "$REMOTE" ]]; then
  echo "Usage: $0 user@server-ip [/opt/rentalai]"
  exit 1
fi

# 1) Run tests locally
if [[ -d .venv ]]; then
  source .venv/bin/activate || true
fi
pip install --upgrade pip >/dev/null 2>&1 || true
pip install -r requirements.txt >/dev/null 2>&1
pytest -q

# 2) Push to git (assumes origin main is set)
branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "main" ]]; then
  echo "[deploy] You are on branch '$branch'. Switch to 'main' or adjust CI.")
fi

echo "[deploy] Pushing to origin/$branch"
git add -A
if ! git diff --quiet --cached; then
  git commit -m "chore(deploy): auto-commit from deploy_local.sh"
fi
git push -u origin "$branch"

# 3) SSH to server, pull and restart via deploy_remote.sh
ssh -o StrictHostKeyChecking=no "$REMOTE" "bash -lc 'cd $REMOTE_BASE/app/rentalai && ./scripts/deploy_remote.sh'"

echo "[deploy] Complete"
