"""OpsDesk for TBO — FastAPI application entry point.

Run:  uvicorn backend.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text

from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.models import Booking, Ticket, User
from backend.observability import ObservabilityMiddleware, prometheus_text
from backend.routers import (
    agents,
    analytics,
    auth,
    escalations,
    exports,
    routing,
    side_conversations,
    simulation,
    tickets,
)
from backend.services.classifier import get_classifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("opsdesk")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    classifier = get_classifier()
    logger.info("OpsDesk starting — classifier mode=%s", classifier.mode)
    if classifier.mode != "ML":
        logger.warning(
            "Classifier running in FALLBACK mode (%s). Train it with: "
            "python -m ai_models.training.train_classifier",
            classifier.load_error,
        )
    yield
    logger.info("OpsDesk shutting down")


app = FastAPI(
    title="OpsDesk for TBO",
    version="2.1.0",
    description=(
        "Booking-centric B2B travel operations platform. A booking is the operational "
        "context; a ticket is one interaction associated with it. All demo data is synthetic."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins if o.strip()] + ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Export-Job-Uuid", "X-Export-Rows"],
)

app.add_middleware(ObservabilityMiddleware)

for module in (auth, agents, tickets, routing, side_conversations, escalations, analytics, exports, simulation):
    app.include_router(module.router)


@app.get("/api/ready", tags=["health"])
def ready():
    """Readiness probe: database write path, classifier artefact and export volume."""
    problems: list[str] = []
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db.scalar(select(func.count()).select_from(Ticket))
    except Exception as exc:  # pragma: no cover - only on a broken deployment
        problems.append(f"database: {exc}")
    finally:
        db.close()

    classifier = get_classifier()
    if classifier.mode != "ML":
        problems.append(f"classifier in {classifier.mode} mode: {classifier.load_error}")

    if not settings.export_dir.exists():
        problems.append(f"export directory missing: {settings.export_dir}")

    body = {
        "status": "ready" if not problems else "degraded",
        "checks": {
            "database": "ok" if not any(p.startswith("database") for p in problems) else "fail",
            "classifier": classifier.mode,
            "export_dir": str(settings.export_dir),
        },
        "problems": problems,
        "environment": settings.environment,
        "version": app.version,
    }
    return JSONResponse(status_code=200 if not problems else 503, content=body)


@app.get("/api/metrics", tags=["health"])
def metrics():
    """Prometheus exposition format, built from measured request counters."""
    def gauges() -> dict[str, float]:
        db = SessionLocal()
        try:
            return {
                "opsdesk_tickets_total": float(db.scalar(select(func.count()).select_from(Ticket)) or 0),
                "opsdesk_bookings_total": float(db.scalar(select(func.count()).select_from(Booking)) or 0),
                "opsdesk_users_total": float(db.scalar(select(func.count()).select_from(User)) or 0),
            }
        finally:
            db.close()

    return PlainTextResponse(prometheus_text(gauges), media_type="text/plain; version=0.0.4")


@app.get("/api/health", tags=["health"])
def health() -> dict:
    classifier = get_classifier()
    db_status = "ok"
    counts: dict[str, int] = {}
    try:
        db = SessionLocal()
        counts = {
            "tickets": int(db.scalar(select(func.count(Ticket.id))) or 0),
            "bookings": int(db.scalar(select(func.count(Booking.id))) or 0),
            "users": int(db.scalar(select(func.count(User.id))) or 0),
        }
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as exc:  # pragma: no cover
        db_status = f"error: {exc}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "version": app.version,
        "database": db_status,
        "counts": counts,
        "classifier": {
            "mode": classifier.mode,
            "trained_at": classifier.version,
            "error": classifier.load_error,
        },
        "data_notice": "All operational data is SYNTHETIC demo data.",
        "features": [
            "intent-classification", "booking-case-graph", "explainable-routing",
            "side-conversations", "travel-aware-sla", "escalation", "product-intelligence",
            "streaming-exports", "simulation-lab",
        ],
    }


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):  # noqa: ARG001
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ------------------------------------------------------------------ static SPA
# Routes are registered unconditionally so the API and SPA can be built in any
# order; missing build output produces a clear message instead of a silent 404.
STATIC_DIR = Path(settings.frontend_dist)


@app.get("/", include_in_schema=False)
def index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Frontend build not found.",
                "fix": "cd frontend && npm install && npm run build  (outputs to backend/static)",
                "api_docs": "/docs",
            },
        )
    return FileResponse(index_file)


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """Serve the SPA for client-side routes; never shadow /api."""
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    candidate = (STATIC_DIR / full_path).resolve()
    if STATIC_DIR.resolve() in candidate.parents and candidate.is_file():
        return FileResponse(candidate)
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse(status_code=404, content={"detail": "Not found"})
