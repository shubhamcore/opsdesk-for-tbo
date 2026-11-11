"""Routing & agent capacity APIs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_ticket_or_404, routing_audit_payload
from backend.api.schemas import ReassignRequest, RouteRequest
from backend.database import get_db
from backend.models import RoutingAudit, User
from backend.security import OPS_ROLES, require_roles
from backend.services import assignment
from backend.services import routing as routing_math

router = APIRouter(prefix="/api/routing", tags=["routing"])


@router.get("/board")
def board(user: User = Depends(require_roles(*OPS_ROLES)), db: Session = Depends(get_db)) -> dict:
    agents = assignment.build_board(db)
    return {
        "agents": agents,
        "count": len(agents),
        "eligible_now": len([a for a in agents if a["eligible_generic"]]),
        "at_capacity": len([a for a in agents if a["active_load"] >= a["max_capacity"]]),
    }


@router.get("/formula")
def formula(user: User = Depends(require_roles(*OPS_ROLES))) -> dict:
    return {
        "formula": (
            "35*RegionMatch + 25*ShiftMatch + 25*(SkillRank/5)*UrgencyWeight "
            "+ 15*(1 - ActiveLoad/MaxCapacity)"
        ),
        "max_score": routing_math.MAX_SCORE,
        "weights": {
            "region": routing_math.W_REGION,
            "shift": routing_math.W_SHIFT,
            "skill": routing_math.W_SKILL,
            "capacity": routing_math.W_CAPACITY,
        },
        "variables": {
            "RegionMatch": "1 if agent.region == ticket.region else 0",
            "ShiftMatch": "1 if current agent-local time is inside shift_start..shift_end else 0",
            "SkillRank": "integer 1..5",
            "UrgencyWeight": "0..1 — priority factor; AT_RISK/BREACHED saturate to 1.0",
            "ActiveLoad": "count of active tickets currently owned by the agent",
            "MaxCapacity": "agent maximum concurrent ticket capacity",
        },
        "hard_filters": [
            "exclude offline agents",
            "exclude agents at capacity or with zero capacity",
            "exclude agents outside their shift window",
            "require SkillRank >= 4 for CRITICAL / AT_RISK / BREACHED tickets",
            "respect configured regional eligibility restrictions",
        ],
        "tie_break": "highest score → lowest active load → lowest agent id",
    }


@router.get("/audits")
def audits(
    ticket_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    query = select(RoutingAudit).order_by(RoutingAudit.created_at.desc())
    if ticket_id is not None:
        query = query.where(RoutingAudit.ticket_id == ticket_id)
    rows = db.scalars(query.limit(limit)).all()
    return {"audits": [routing_audit_payload(row) for row in rows], "count": len(rows)}


@router.get("/performance")
def performance(user: User = Depends(require_roles(*OPS_ROLES)), db: Session = Depends(get_db)) -> dict:
    rows = assignment.performance(db)
    return {"agents": rows, "count": len(rows)}


@router.get("/tickets/{ticket_id}/comparator")
def comparator(
    ticket_id: str,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    decision = assignment.build_decision(db, ticket)
    decision["explanation"] = assignment.explain(ticket, decision)
    decision["current_assignee_id"] = ticket.assigned_user_id
    return decision


@router.post("/tickets/{ticket_id}/route")
def route(
    ticket_id: str,
    payload: RouteRequest,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    return assignment.route_ticket(db, ticket, actor=user, triggered_by=payload.triggered_by)


@router.post("/tickets/{ticket_id}/reassign")
def reassign(
    ticket_id: str,
    payload: ReassignRequest,
    user: User = Depends(require_roles("OPS_LEAD", "ESCALATION_MANAGER")),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    return assignment.reassign(db, ticket, actor=user, agent_id=payload.agent_id, note=payload.note)
