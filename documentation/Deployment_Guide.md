# OpsDesk — Deployment Guide

## 1. Requirements

| Component | Version used | Notes |
| --- | --- | --- |
| Python | 3.13 | 3.11+ should work; `zoneinfo` needs tzdata on slim images |
| Node.js | 20 | only to build the SPA |
| SQLite | 3.40+ | bundled with Python |
| FFmpeg / LibreOffice | 7.1 / 25.2 | only to regenerate videos and PDF decks |

System packages for the optional tooling: `ffmpeg`, `libreoffice-impress`, `poppler-utils`
(PDF preview), plus `playwright install chromium` for browser verification.

## 2. Install

```bash
git clone <repo> && cd OpsDesk
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd frontend
npm ci
npm run build          # emits ../backend/static
cd ..
```

`npm run build` runs `tsc -b` first, so a type error fails the build instead of shipping.

## 3. Configure

Copy `.env.example` to `.env` (or export the variables) — nothing is read from source:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPSDESK_APP_NAME` | `OpsDesk for TBO` | shown in health/docs |
| `OPSDESK_SECRET_KEY` | `dev-insecure-change-me` | JWT signing key — **must** be set in any shared environment |
| `OPSDESK_DATABASE_URL` | `sqlite:///database/opsdesk.db` | swap to `postgresql+psycopg://…` for Postgres |
| `OPSDESK_TOKEN_TTL_MINUTES` | `720` | bearer token lifetime |
| `OPSDESK_EXPORT_DIR` | `exports/` | where streamed files are written |
| `OPSDESK_EXPORT_BATCH_SIZE` | `5000` | rows per yielded batch |
| `OPSDESK_MODEL_PATH` | `ai_models/saved_models/intent_pipeline.joblib` | classifier artefact |
| `OPSDESK_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | dev-server origins |
| `OPSDESK_ENABLE_ROLE_SWITCH` | `true` | demo one-click sign-in; set `false` for shared deployments |
| `OPSDESK_DEMO_PASSWORD` | documented demo password | password for the seeded synthetic identities |

Generate a real secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 4. Seed the database

```bash
python -m database.seed_data.seed                 # create if empty
python -c "from database.seed_data.seed import seed_database; seed_database(reset=True)"   # rebuild
```

Expected output: 4 agencies · 16 users · 12 bookings · **49 tickets** (24 named + 25 background).
The seed is relative to `now`, so SLA countdowns are always meaningful. All rows are synthetic.

## 5. Run

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
# optional: --reload for development, --workers 4 behind a load balancer
```

- App: `http://<host>:8000/`
- OpenAPI: `/docs`, `/openapi.json`
- Health: `/api/health`

If `GET /` returns a JSON 503 with a `fix` hint, the SPA was never built — run `npm run build` in
`frontend/`.

### Development mode

```bash
uvicorn backend.main:app --reload --port 8000      # terminal 1
cd frontend && npm run dev                          # terminal 2 → http://localhost:5173, /api proxied
```

## 6. Verify a deployment

```bash
curl -s localhost:8000/api/health | python -m json.tool      # status ok, counts, classifier mode
python -m pytest tests backend/tests -q                      # 106 passed
python -m simulation.run_all                                 # 5/5 journeys, 34/34 steps
python scripts/ui_crawl.py                                   # 6 workspaces, 0 console errors
```

## 7. Operations

| Task | How |
| --- | --- |
| Reseed demo data | `POST /api/simulation/seed` (lead) or `POST /api/simulation/reset` to also clear runtime rows |
| Prune export artefacts | `python -c "from backend.services.exports import sweep_old_exports; print(sweep_old_exports(keep=3))"` |
| Rotate the model | retrain via `ai_models/training/`, drop the new `joblib` at `OPSDESK_MODEL_PATH`, restart |
| Backup | copy `database/opsdesk.db` (and `-wal`/`-shm`) while stopped, or `sqlite3 opsdesk.db ".backup out.db"` |
| Logs | uvicorn access/error logs on stdout; ship to your collector |

Observe these health signals: `/api/health` (`database`, `classifier.mode`), export job statuses
(`/api/exports/jobs`: any `FAILED` row), and the SLA queue counts in `/api/analytics/queue`.

## 8. Docker sketch (not shipped as a file in this repo)

```dockerfile
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt . && RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN cd frontend && npm ci && npm run build
ENV OPSDESK_SECRET_KEY=change-me
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 9. Scaling notes (reference, not implemented)

- Move `OPSDESK_DATABASE_URL` to PostgreSQL and set `--workers` behind a proxy; SQLite serialises writes.
- Export generation is CPU-bound in the app process today — the documented target is a worker queue
  writing to Parquet/object storage (see `Storage_Architecture.md`).
- The classifier artefact is loaded per process; with many workers pin it to a shared volume or a model
  server.

## 10. Security checklist before sharing a URL

- [ ] `OPSDESK_SECRET_KEY` set to a random 48-byte value
- [ ] `OPSDESK_ENABLE_ROLE_SWITCH=false` (disables demo one-click sign-in)
- [ ] `OPSDESK_DEMO_PASSWORD` changed or the seeded accounts replaced
- [ ] TLS terminated in front of uvicorn
- [ ] `OPSDESK_CORS_ORIGINS` restricted to the real front-end origin
- [ ] Export artefacts pruned on a schedule; `exports/` not publicly served
- [ ] `.env` excluded from version control (`.gitignore`)

No credentials are committed in this repository; the demo password is a synthetic seed value and is
overridable by environment variable.


## Container, CI and operations (v2.1)

```bash
docker build -t opsdesk-tbo:2.1.0 .          # multi-stage: Vite build → python:3.13-slim
docker compose up -d                         # SQLite on a named volume, port 8000
docker compose --profile postgres up -d      # configuration path only, see §Not executed
```

The image runs as uid 10001, exposes `HEALTHCHECK` on `/api/ready`, and starts a single
uvicorn worker: SQLite is the store, so scale out only after moving `OPSDESK_DATABASE_URL` to
Postgres.

| Operator task | Command |
| --- | --- |
| Install deps | `make install` |
| Reseed the synthetic dataset | `make seed` |
| Run the API + SPA | `make serve` |
| Release gate | `make verify` (tests + five journeys) |
| Benchmark | `make bench` |
| Screenshot every workspace | `make crawl` |
| Consistent backup | `python -m scripts.backup_db --out backups/opsdesk-$(date +%F).db` |

Observability contract: `GET /api/health` (liveness), `GET /api/ready` (readiness, 503 when the
classifier or DB is degraded), `GET /api/metrics` (Prometheus text). Every response carries
`X-Request-ID` and `X-Response-Time-Ms`; the access log is one JSON line per request with the
same id. Sign-in attempts are limited per client (`OPSDESK_RATE_LIMIT_PER_MINUTE`, default 60,
`0` disables) and return `Retry-After` when limited.

CI (`.github/workflows/ci.yml`) runs the 121-test suite plus the five seeded journeys on every
push, and type-checks plus builds the SPA in a second job.
