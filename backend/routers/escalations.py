"""Escalation Manager APIs — queue, escalation, history, trend."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.deps import get_ticket_or_404
from backend.api.schemas import EscalateRequest
from backend.database import get_db
from backend.models import User
from backend.security import OPS_ROLES, require_roles
from backend.services import escalation as escalation_service

router = APIRouter(prefix="/api/escalations", tags=["escalations"])


@router.get("/queue")
def queue(
    user: User = Depends(require_roles("ESCALATION_MANAGER", "OPS_LEAD", "OPS_AGENT")),
    db: Session = Depends(get_db),
) -> dict:
    return escalation_service.queue(db, user)


@router.get("/managers")
def managers(
    user: User = Depends(require_roles("ESCALATION_MANAGER", "OPS_LEAD", "OPS_AGENT")),
    db: Session = Depends(get_db),
) -> dict:
    rows = escalation_service.eligible_managers(db)
    return {
        "managers": [
            {
                "id": m.id,
                "full_name": m.full_name,
                "region": m.region,
                "timezone": m.timezone,
                "active_escalations": escalation_service.manager_load(db, m.id),
                "is_online": m.is_online,
            }
            for m in rows
        ]
    }


@router.get("/trend")
def trend(
    weeks: int = 8,
    user: User = Depends(require_roles("ESCALATION_MANAGER", "OPS_LEAD", "OPS_AGENT")),
    db: Session = Depends(get_db),
) -> dict:
    return escalation_service.trend(db, weeks=weeks)


@router.get("/deadlines")
def deadlines(
    hours: int = 48,
    user: User = Depends(require_roles("ESCALATION_MANAGER", "OPS_LEAD", "OPS_AGENT")),
    db: Session = Depends(get_db),
) -> dict:
    return {"deadlines": escalation_service.upcoming_deadlines(db, hours=hours)}


@router.post("/tickets/{ticket_id}/escalate")
def escalate(
    ticket_id: str,
    payload: EscalateRequest,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    return escalation_service.escalate(db, ticket, actor=user, reason=payload.reason)


@router.get("/tickets/{ticket_id}")
def history(
    ticket_id: str,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "escalations": escalation_service.history(db, ticket),
    }
