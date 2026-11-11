"""Product intelligence and governance APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.schemas import ProductBugCreate
from backend.database import get_db
from backend.models import ProductBug, User
from backend.security import require_roles
from backend.services import analytics as analytics_service

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/queue")
def queue(
    user: User = Depends(require_roles("OPS_AGENT", "ESCALATION_MANAGER", "OPS_LEAD")),
    db: Session = Depends(get_db),
) -> dict:
    return analytics_service.queue_snapshot(db)


@router.get("/product-intelligence")
def product_intelligence(
    window_days: int = Query(default=30, ge=1, le=365),
    user: User = Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
    db: Session = Depends(get_db),
) -> dict:
    return analytics_service.product_intelligence(db, window_days=window_days)


@router.post("/themes/refresh")
def refresh_themes(
    user: User = Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
    db: Session = Depends(get_db),
) -> dict:
    themes = analytics_service.refresh_themes(db)
    return {"themes": themes, "count": len(themes)}


@router.get("/bug-suggestions")
def bug_suggestions(
    window_days: int = Query(default=60, ge=1, le=365),
    min_tickets: int = Query(default=3, ge=2, le=50),
    user: User = Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
    db: Session = Depends(get_db),
) -> dict:
    return analytics_service.bug_suggestions(db, window_days=window_days, min_tickets=min_tickets)


@router.get("/product-bugs")
def list_bugs(
    user: User = Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(select(ProductBug).order_by(ProductBug.created_at.desc())).all()
    return {"bugs": [analytics_service.product_bug_payload(b) for b in rows], "count": len(rows)}


@router.post("/product-bugs", status_code=http_status.HTTP_201_CREATED)
def create_bug(
    payload: ProductBugCreate,
    user: User = Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
    db: Session = Depends(get_db),
) -> dict:
    bug = analytics_service.create_product_bug(
        db,
        supplier=payload.supplier,
        intent=payload.intent,
        title=payload.title,
        suggested_action=payload.suggested_action,
        related_ticket_ids=payload.related_ticket_ids,
        frequency=payload.frequency,
        created_by=user.full_name,
    )
    return analytics_service.product_bug_payload(bug)
