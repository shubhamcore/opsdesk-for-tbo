# Pushing OpsDesk for TBO to GitHub

Target account: **shubhamcore** · commit email: **sk2330465@gmail.com** · branch: **main** · repo name: **opsdesk-for-tbo**

Two ways to do this. **Option A** is one command. **Option B** is the explicit sequence if you prefer to see every step.

---

## 0. Get the code onto your machine

Download `OpsDesk_for_TBO_v2.1.zip` from this workspace, then:

```bash
unzip OpsDesk_for_TBO_v2.1.zip     # creates ./OpsDesk
cd OpsDesk
git --version                      # any git ≥ 2.23 is fine
```

The project already ships a `.gitignore` that keeps `node_modules/`, `.env`, SQLite WAL sidecars,
runtime export CSVs and video scratch files out of the repository.

---

## 1. Create the empty repository on GitHub

<https://github.com/new>

* **Repository name:** `opsdesk-for-tbo`
* **Visibility:** your choice (Private is safer while it is demo data)
* **Initialise with README / .gitignore / licence: NO** — leave all three unchecked, otherwise the
  first push is rejected as non-fast-forward.

Then create a **Personal Access Token**: GitHub → *Settings → Developer settings → Personal access
tokens → Tokens (classic) → Generate new token*, scope **`repo`**. Copy it once; GitHub will never
show it again.

> Why a token: GitHub removed password authentication for git in 2021. The token is used **as the
> password** when git prompts. Do not save it in any file inside this repository.

---

## Option A — one command

```bash
./scripts/push_to_github.sh shubhamcore opsdesk-for-tbo
```

When prompted:

```
Username for 'https://github.com': shubhamcore
Password for 'https://shubhamcore@github.com': <paste the token>
```

The script sets your identity, initialises git, stages everything, refuses to proceed if an
excluded file (`.env`, `node_modules/`, `*.db-wal`, export CSVs) slipped in, commits, adds
`origin`, and pushes `main`.

---

## Option B — explicit commands

```bash
# 1. identity (repo-local, so it cannot clash with other projects)
git config --global user.name  "shubhamcore"
git config --global user.email "sk2330465@gmail.com"

# 2. repository
git init
git checkout -B main

# 3. stage everything except .gitignore'd paths
git add -A
git status --short            # review: no node_modules/, no .env, no *.db-wal

# 4. first commit
git commit -m "OpsDesk for TBO v2.1.0 — booking-centric travel ops platform

- FastAPI + SQLAlchemy + SQLite (WAL) backend, 56 API paths
- React + Vite + TypeScript console with six workspaces
- Eight-agent case review mesh with read-only tool allow-lists and persisted traces
- Travel-aware SLA engine, explainable 100-point routing, escalation war room
- Streaming 50k-row exports, product intelligence, live simulation lab
- 121 pytest tests, five seeded journeys, Docker/CI packaging

All operational data is synthetic."

# 5. remote + push
git remote add origin https://github.com/shubhamcore/opsdesk-for-tbo.git
git push -u origin main
```

Push over SSH instead of HTTPS (no token prompts after setup):

```bash
ssh-keygen -t ed25519 -C "sk2330465@gmail.com"          # then add ~/.ssh/id_ed25519.pub to GitHub → SSH keys
git remote add origin git@github.com:shubhamcore/opsdesk-for-tbo.git
git push -u origin main
```

With the GitHub CLI:

```bash
gh auth login
gh repo create opsdesk-for-tbo --private --source=. --remote=origin --push
```

---

## 2. What actually gets committed

Verified on the packaged archive before shipping this guide:

| Category | Size | Pushed? |
| --- | --- | --- |
| Source (`backend/`, `frontend/src`, `tests/`, `simulation/`, `scripts/`) | ~2 MB | ✅ |
| Built SPA (`backend/static/`) | 0.8 MB | ✅ (so the image and a bare `uvicorn` both work) |
| Model artefact (`ai_models/saved_models/intent_pipeline.joblib`) | 0.4 MB | ✅ (403 KB, well under GitHub's 100 MB limit) |
| Database (`database/opsdesk.db`, synthetic) | 0.4 MB | ✅ |
| Docs, decks, videos, screenshots | ~12 MB | ✅ |
| `node_modules/`, `.env`, `exports/*.csv`, `*.db-wal`, `videos/raw/` | — | ❌ ignored |

If you would rather keep the media out of git, add `videos/` and `presentations/` to `.gitignore`
before the first commit — but then say so in the README, because they are referenced there.

---

## 3. Verify the push

```bash
git remote -v                       # origin  https://github.com/shubhamcore/opsdesk-for-tbo.git
git log --oneline -1                # your commit
git ls-files | wc -l                # file count in the repo
git ls-files | grep -E "node_modules|\.env$" || echo "clean: no node_modules or secrets tracked"
```

Then open <https://github.com/shubhamcore/opsdesk-for-tbo> and confirm:

* the README renders with the architecture table and measured results,
* `documentation/` and `screenshots/` are browsable,
* `backend/static/assets/index-*.js` is present (the SPA build),
* **Settings → Actions** shows the `ci` workflow; the first run executes 121 tests plus the five
  seeded journeys.

---

## 4. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `! [rejected] main -> main (fetch first)` | repo was created with a README/licence | `git pull --rebase origin main` then `git push -u origin main` |
| `remote: Support for password authentication was removed` | typed the account password | use the Personal Access Token as the password |
| `remote: Permission to … denied` | token missing `repo` scope, or wrong account cached | regenerate the token with `repo`; `git credential-manager reject https://github.com` (or clear Windows Credential Manager) |
| `error: File … is 123.00 MB; this exceeds GitHub's file size limit` | a stray export CSV or a new video | `git rm --cached <file>` + add the path to `.gitignore` |
| Commits show your real name/email | identity not set | `git commit --amend --reset-author` after `git config user.email …` |
| Want commits to hide the Gmail address | privacy preference | GitHub → *Settings → Emails* → enable *Keep my email private*, then use `sk2330465@users.noreply.github.com` as `user.email` |

---

## 5. Optional: keep pushing updates

```bash
git add -A
git commit -m "describe the change"
git push
```

Before each push, the repository's own release gate is:

```bash
python -m pytest tests backend/tests -q    # expect 121 passed
python -m simulation.run_all               # expect 5/5 journeys
```
