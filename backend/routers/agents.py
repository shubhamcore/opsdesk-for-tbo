"""Multi-agent case review endpoints.

Read endpoints are open to the internal roles that already see the case; the
swarm run is limited to ops roles and is always persisted, so an agent-assisted
decision is as auditable as a human one.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents import orchestrator
from backend.api.deps import get_ticket_or_404
from backend.api.schemas import AgentRunRequest
from backend.database import get_db
from backend.models import AgentRun, Ticket, User
from backend.security import OPS_ROLES, require_roles

router = APIRouter(prefix="/api/agents", tags=["agents"])


@router.get("/registry")
def registry(user: User = Depends(require_roles(*OPS_ROLES))) -> dict:
    return orchestrator.registry_payload()


@router.post("/cases/{ticket_ref}/run")
def run_case(
    ticket_ref: str,
    payload: AgentRunRequest | None = None,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_ref, user)
    if ticket.status == "RESOLVED":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Case is resolved — reopen it before requesting an agent review",
        )
    objective = (payload.objective if payload else None) or "CASE_REVIEW"
    return orchestrator.run_case_swarm(db, ticket, actor=user, objective=objective)


@router.get("/runs")
def runs(
    ticket_id: int | None = Query(None, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if ticket_id is not None:
        stmt = stmt.where(AgentRun.ticket_id == ticket_id)
    records = db.scalars(stmt).all()
    tickets = {t.id: t for t in db.scalars(select(Ticket).where(Ticket.id.in_([r.ticket_id for r in records]))).all()}
    return {
        "runs": [orchestrator.record_payload(r, tickets.get(r.ticket_id)) for r in records],
        "count": len(records),
    }


@router.get("/runs/{run_uuid}")
def run_detail(
    run_uuid: str,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    record = db.scalar(select(AgentRun).where(AgentRun.run_uuid == run_uuid))
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent run not found")
    return orchestrator.record_payload(record, db.get(Ticket, record.ticket_id))


@router.get("/telemetry")
def telemetry(
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    return orchestrator.telemetry(db)
