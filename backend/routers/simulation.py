"""Workspace 6 — Live Simulation Lab APIs.

Journeys are executed by driving the public HTTP API of this same service, so a
green lab run proves the API path (not a private shortcut).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Ticket
from backend.security import require_roles
from backend.services.classifier import get_classifier

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

RESULTS_PATH = Path(__file__).resolve().parents[2] / "benchmark_results" / "journey_results.json"
JOURNEY_META = {
    "A": {
        "title": "Booking context & automatic case linking",
        "agency": "Wanderlust Travels (MEA)",
        "expected": "New refund ticket on TBOH-778899 is auto-extracted, classified "
                    "REFUND_DELAY, linked to TCK-101/104/109 and summarised in a 3-point brief.",
        "workspace": "W1 / W2",
    },
    "B": {
        "title": "Intelligent routing & capacity",
        "agency": "Apex Global Holidays (APAC)",
        "expected": "High-priority voucher ticket on TBOH-554411 routes to Ananya Sharma "
                    "(APAC, skill 5, 1/8 load) with a full score breakdown and audit row.",
        "workspace": "W3",
    },
    "C": {
        "title": "Transfer-safe supplier communication",
        "agency": "EuroWings B2B (EU)",
        "expected": "Hilton Paris conversation keeps groups@hilton-paris.com and the full "
                    "message history after the ticket moves EU-TRIAGE → EU-SENIOR-OPS.",
        "workspace": "W2",
    },
    "D": {
        "title": "Travel-aware SLA & escalation",
        "agency": "EuroWings B2B / Apex Global (EU / APAC)",
        "expected": "TCK-401 shows LCD-governed countdown, escalate creates real ownership by "
                    "an Escalation Manager, audit timeline records the handover.",
        "workspace": "W1 / W4",
    },
    "E": {
        "title": "Product intelligence & 50,000-row export",
        "agency": "All agencies",
        "expected": "Inventory-sync theme yields a PROD-BUG proposal and a 50,000-row CSV "
                    "streams with validated row count and measured throughput.",
        "workspace": "W5",
    },
}


def _internal_base_url() -> str:
    return os.getenv("OPSDESK_INTERNAL_URL", "http://127.0.0.1:8000").rstrip("/")


@router.get("/status")
def sim_status(db: Session = Depends(get_db),
               user=Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER"))) -> dict:
    classifier = get_classifier()
    return {
        "database": {
            "tickets": int(db.scalar(select(func.count(Ticket.id))) or 0),
            "active": int(db.scalar(select(func.count(Ticket.id)).where(Ticket.status.in_(
                ("OPEN", "IN_PROGRESS", "PENDING_SUPPLIER", "ESCALATED")))) or 0),
        },
        "classifier_mode": classifier.mode,
        "classifier_error": classifier.load_error,
        "internal_base_url": _internal_base_url(),
        "datasets_are_synthetic": True,
        "journeys": [{"key": key, **meta} for key, meta in JOURNEY_META.items()],
        "last_results_available": RESULTS_PATH.exists(),
    }


@router.post("/seed")
def seed(user=Depends(require_roles("OPS_LEAD"))) -> dict:
    """One-click seed (resets first so runs are reproducible)."""
    from database.seed_data.seed import seed_database

    try:
        summary = seed_database(reset=True)
    except Exception as exc:  # surfaced to the UI
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Seeding failed: {exc}") from exc
    return {"seeded": True, **summary}


@router.post("/reset")
def reset(user=Depends(require_roles("OPS_LEAD"))) -> dict:
    from database.seed_data.seed import reset_database

    counts = reset_database()
    return {"reset": True, "rows_deleted": counts}


@router.post("/journeys/{key}/run")
def run_journey(
    key: str,
    export_rows: int = 50000,
    reseed: bool = True,
    user=Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
) -> dict:
    """Run one seeded journey.

    ``reseed`` restores the deterministic baseline first (default true) so a
    journey can be replayed after earlier runs have changed ticket state — e.g.
    journey C needs the supplier ticket to still be sitting in EU-TRIAGE.
    """
    key = key.upper()
    if key not in JOURNEY_META:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown journey {key}")

    if reseed:
        from database.seed_data.seed import seed_database

        seed_database(reset=True)

    from simulation.engine import pretty
    from simulation.journeys import JOURNEYS

    base_url = _internal_base_url()
    try:
        result = (
            JOURNEYS[key](base_url) if key != "E" else JOURNEYS[key](base_url, export_rows)
        )
    except Exception as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Journey {key} could not reach the service at {base_url}: {exc}",
        ) from exc

    _merge_into_results_file(result)
    return {**result, "meta": JOURNEY_META[key], "console": pretty(result), "reseeded": reseed}


@router.get("/journeys/results")
def journey_results(user=Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER"))) -> dict:
    if not RESULTS_PATH.exists():
        return {"available": False, "journeys": []}
    data = json.loads(RESULTS_PATH.read_text())
    return {"available": True, **data}


def _merge_into_results_file(result: dict) -> None:
    """Keep a rolling record of lab runs next to the CLI report."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": _internal_base_url(),
        "journeys": [],
        "source": "Workspace 6 simulation lab",
    }
    if RESULTS_PATH.exists():
        try:
            existing = json.loads(RESULTS_PATH.read_text())
            payload["journeys"] = [
                j for j in existing.get("journeys", []) if j.get("journey") != result["journey"]
            ]
        except json.JSONDecodeError:
            payload["journeys"] = []
    payload["journeys"].append(result)
    payload["journeys"].sort(key=lambda j: j["journey"])
    payload["summary"] = {
        "total": len(payload["journeys"]),
        "passed": sum(1 for j in payload["journeys"] if j.get("passed")),
        "steps_total": sum(j.get("steps_total", 0) for j in payload["journeys"]),
        "steps_passed": sum(j.get("steps_passed", 0) for j in payload["journeys"]),
    }
    RESULTS_PATH.write_text(json.dumps(payload, indent=2, default=str))
