#!/usr/bin/env bash
# One-shot: initialise git in this project and push it to a new GitHub repo.
#
#   ./scripts/push_to_github.sh shubhamcore opsdesk-for-tbo
#
# Authentication: GitHub no longer accepts account passwords on the command line.
# Use a Personal Access Token (classic, scope "repo") as the password when git asks,
# or pre-configure SSH. Never paste a token into a file inside this repository.
set -euo pipefail

USER_NAME="${1:-shubhamcore}"
REPO_NAME="${2:-opsdesk-for-tbo}"
BRANCH="${3:-main}"
EMAIL="${GIT_EMAIL:-sk2330465@gmail.com}"

cd "$(dirname "$0")/.."

echo "==> git identity"
git config user.name "$USER_NAME"
git config user.email "$EMAIL"

if [ ! -d .git ]; then
  echo "==> git init"
  git init
fi
git checkout -B "$BRANCH"

echo "==> staging (respects .gitignore)"
git add -A
git status --short | head -20
echo "..."
echo "    staged files: $(git diff --cached --name-only | wc -l)"
echo "    staged size : $(git diff --cached --name-only | xargs -r du -ch 2>/dev/null | tail -1 || echo 'n/a')"

echo "==> guarding against mistakes"
if git diff --cached --name-only | grep -qE '(^|/)\.env$|node_modules/|\.db-wal$|exports/.+\.csv$'; then
  echo "ERROR: refusing to commit excluded files. Check .gitignore." >&2
  git diff --cached --name-only | grep -E '(^|/)\.env$|node_modules/|\.db-wal$|exports/.+\.csv$' >&2
  exit 1
fi

echo "==> commit"
git commit -m "OpsDesk for TBO v2.1.0 — booking-centric travel ops platform

- FastAPI + SQLAlchemy + SQLite (WAL) backend, 56 API paths
- React + Vite + TypeScript console with six workspaces
- Eight-agent case review mesh with read-only tool allow-lists and persisted traces
- Travel-aware SLA engine, explainable 100-point routing, escalation war room
- Streaming 50k-row exports, product intelligence, live simulation lab
- 121 pytest tests, five seeded journeys, Docker/CI packaging

All operational data is synthetic." || echo "    (nothing new to commit)"

echo "==> remote"
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "https://github.com/${USER_NAME}/${REPO_NAME}.git"
else
  git remote add origin "https://github.com/${USER_NAME}/${REPO_NAME}.git"
fi
echo "    origin -> $(git remote get-url origin)"

echo "==> push"
git push -u origin "$BRANCH"

echo
echo "Done. If the push failed, create the empty repo first:"
echo "  https://github.com/new  (name: ${REPO_NAME}, no README/licence/gitignore)"
echo "Then re-run: git push -u origin ${BRANCH}"
