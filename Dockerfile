# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# OpsDesk for TBO — single-image build (API + prebuilt SPA)
# ---------------------------------------------------------------------------
FROM node:20-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build          # emits into ../backend/static (see vite.config.ts)

FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPSDESK_ENV=production \
    OPSDESK_DATABASE_URL=sqlite:////data/opsdesk.db \
    OPSDESK_EXPORT_DIR=/data/exports

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY database ./database
COPY ai_models ./ai_models
COPY simulation ./simulation
COPY --from=frontend /app/backend/static ./backend/static

RUN useradd --create-home --uid 10001 opsdesk \
    && mkdir -p /data/exports && chown -R opsdesk:opsdesk /data /app
USER opsdesk

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/ready || exit 1

# One worker per container: SQLite is the store. Scale horizontally only after
# moving to Postgres (OPSDESK_DATABASE_URL) — see documentation/Deployment_Guide.md.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
