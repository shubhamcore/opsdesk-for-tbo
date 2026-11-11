"""Routing orchestration — agent board, comparator, assignment and audit."""
from __future__ import annotations

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import sla_payload
from backend.models import ActivityTimeline, RoutingAudit, Ticket, User
from backend.models.base import utcnow
from backend.services import routing as routing_math
from backend.services import sla as sla_service

AGENT_ROLES = ("OPS_AGENT",)  # EMs and leads own escalations/oversight, not new work
REGIONAL_ELIGIBILITY: dict[str, set[str]] = {
    "APAC": {"APAC", "MEA"},
    "MEA": {"MEA", "APAC"},
    "EU": {"EU", "AMER"},
    "AMER": {"AMER", "EU"},
}


def _agent_state(agent: User, active_load: int, now) -> routing_math.AgentState:
    shift_match = routing_math.is_within_shift(
        now, agent.timezone, agent.shift_start, agent.shift_end
    )
    return routing_math.AgentState(
        agent_id=agent.id,
        full_name=agent.full_name,
        email=agent.email,
        region=agent.region,
        skill_rank=agent.skill_rank,
        max_capacity=agent.max_capacity,
        active_load=active_load,
        is_online=agent.is_online,
        timezone=agent.timezone,
        shift_start=agent.shift_start,
        shift_end=agent.shift_end,
        shift_match=shift_match,
    )


def active_loads(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Ticket.assigned_user_id).where(
            Ticket.assigned_user_id.is_not(None),
            Ticket.is_deleted.is_(False),
            Ticket.status.in_(("OPEN", "IN_PROGRESS", "PENDING_SUPPLIER", "ESCALATED")),
        )
    ).all()
    counts: dict[int, int] = {}
    for (agent_id,) in rows:
        counts[agent_id] = counts.get(agent_id, 0) + 1
    return counts


def eligible_agents(db: Session, *, ticket_region: str, priority: str, sla_state: str, now=None):
    now = now or utcnow()
    loads = active_loads(db)
    agents = db.scalars(
        select(User).where(
            User.role.in_(AGENT_ROLES),
            User.is_deleted.is_(False),
        ).order_by(User.id)
    ).all()
    allowed = REGIONAL_ELIGIBILITY.get(ticket_region)
    states, excluded = [], []
    for agent in agents:
        state = _agent_state(agent, loads.get(agent.id, 0), now)
        verdict = routing_math.check_eligibility(
            state,
            ticket_region=ticket_region,
            priority=priority,
            sla_state=sla_state,
            allowed_regions=allowed,
        )
        if verdict.eligible:
            states.append(state)
        else:
            excluded.append({"agent_id": agent.id, "full_name": agent.full_name,
                             "region": agent.region, "reasons": verdict.reasons})
    return states, excluded, now


def build_board(db: Session) -> list[dict]:
    now = utcnow()
    loads = active_loads(db)
    agents = db.scalars(
        select(User).where(User.role.in_(AGENT_ROLES), User.is_deleted.is_(False)).order_by(User.id)
    ).all()
    board = []
    for agent in agents:
        state = _agent_state(agent, loads.get(agent.id, 0), now)
        verdict = routing_math.check_eligibility(
            state, ticket_region=agent.region or "MEA", priority="MEDIUM", sla_state="HEALTHY",
            allowed_regions=REGIONAL_ELIGIBILITY.get(agent.region or "MEA"),
        )
        reference = routing_math.compute_route_score(
            state, ticket_region=agent.region or "MEA", urgency_weight=1.0
        )
        board.append({
            "agent_id": agent.id,
            "name": agent.full_name,
            "email": agent.email,
            "region": agent.region,
            "timezone": agent.timezone,
            "skill_rank": agent.skill_rank,
            "max_capacity": agent.max_capacity,
            "active_load": state.active_load,
            "is_online": agent.is_online,
            "shift": f"{agent.shift_start}-{agent.shift_end}",
            "shift_match_now": verdict.eligible or any("shift" not in r for r in verdict.reasons),
            "eligible_generic": verdict.eligible,
            "utilization_pct": round(100 * state.active_load / agent.max_capacity, 1)
            if agent.max_capacity else 100.0,
            "reference_score": round(reference.total_score, 2),
        })
    board.sort(key=lambda row: (-row["reference_score"], row["active_load"], row["agent_id"]))
    return board


def _urgency_for(ticket: Ticket) -> tuple[dict, float]:
    payload = sla_payload(ticket)
    weight = payload.get("urgency_weight", 0.7)
    return payload, float(weight)


def build_decision(db: Session, ticket: Ticket) -> dict:
    sla_data, urgency = _urgency_for(ticket)
    states, excluded, _ = eligible_agents(
        db, ticket_region=ticket.region, priority=ticket.priority, sla_state=sla_data["state"],
    )
    scored = [
        routing_math.compute_route_score(state, ticket_region=ticket.region, urgency_weight=urgency)
        for state in states
    ]
    ranked = routing_math.rank_candidates(scored)
    tie_break = len(ranked) > 1 and ranked[0].total_score == ranked[1].total_score
    winner = ranked[0] if ranked else None
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "ticket_region": ticket.region,
        "sla_state": sla_data["state"],
        "urgency_weight": round(urgency, 4),
        "candidates": [c.as_dict() for c in ranked],
        "excluded": excluded,
        "winner": winner.as_dict() if winner else None,
        "tie_break_applied": tie_break,
    }


def explain(ticket: Ticket, decision: dict) -> str:
    winner = decision["winner"]
    if winner is None:
        return "No eligible agent: every candidate failed a hard eligibility filter"
    runner = decision["candidates"][1] if len(decision["candidates"]) > 1 else None
    text = (
        f"{winner['full_name']} scored {winner['total_score']:.2f}/100 "
        f"(region {winner['region_match'] * 35:.0f} + shift {winner['shift_match'] * 25:.0f} + "
        f"skill {winner['skill_component']:.2f} + capacity {winner['capacity_component']:.2f})"
    )
    if runner:
        text += f"; next best {runner['full_name']} at {runner['total_score']:.2f}"
    if decision["tie_break_applied"]:
        text += "; tie-break applied (lower active load, then lower agent id)"
    return text


def route_ticket(db: Session, ticket: Ticket, *, actor: User, triggered_by: str = "MANUAL") -> dict:
    decision = build_decision(db, ticket)
    reason = explain(ticket, decision)
    winner = decision["winner"]

    audit = RoutingAudit(
        ticket_id=ticket.id,
        candidate_scores_json=decision["candidates"],
        excluded_json=decision["excluded"],
        eligible_count=len(decision["candidates"]),
        selected_agent_id=winner["agent_id"] if winner else None,
        selected_score=winner["total_score"] if winner else None,
        decision_reason=reason,
        tie_break_applied=decision["tie_break_applied"],
        triggered_by=triggered_by,
        created_at=utcnow(),
    )
    db.add(audit)

    if winner:
        ticket.assigned_user_id = winner["agent_id"]
        ticket.queue = f"{ticket.region}-SUPPORT"
        if ticket.status == "OPEN":
            ticket.status = "IN_PROGRESS"
        ticket.updated_at = utcnow()
        db.add(ActivityTimeline(
            ticket_id=ticket.id,
            event_type="ROUTED",
            actor_name=actor.full_name,
            description=f"Assigned to {winner['full_name']} — {reason}",
            metadata_json={
                "agent_id": winner["agent_id"],
                "score": winner["total_score"],
                "eligible": len(decision["candidates"]),
                "excluded": len(decision["excluded"]),
            },
            created_at=utcnow(),
        ))
    else:
        db.add(ActivityTimeline(
            ticket_id=ticket.id,
            event_type="ROUTING_SKIPPED",
            actor_name=actor.full_name,
            description="No eligible agent — left unassigned rather than force-assigned",
            metadata_json={"excluded": len(decision["excluded"])},
            created_at=utcnow(),
        ))

    db.commit()
    db.refresh(ticket)

    assigned = db.get(User, ticket.assigned_user_id) if ticket.assigned_user_id else None
    fifo_note = (
        "FIFO would hand this to whoever has waited longest. Routing instead scores every eligible "
        "agent on region, shift, skill and capacity, so the ticket lands with someone who is on shift, "
        "senior enough and has room — and every excluded agent is explained in the audit row."
    )
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "assigned_to": {
            "id": assigned.id if assigned else None,
            "name": assigned.full_name if assigned else None,
            "region": assigned.region if assigned else None,
            "skill_rank": assigned.skill_rank if assigned else None,
            "active_load": decision["winner"]["active_load"] if winner else None,
            "max_capacity": decision["winner"]["max_capacity"] if winner else None,
        } if assigned else None,
        "decision": {
            **decision,
            "score": decision["winner"]["total_score"] if winner else 0.0,
            "assigned_agent_id": winner["agent_id"] if winner else None,
            "decision_reason": reason,
        },
        "audit_id": audit.id,
        "fifo_note": fifo_note,
    }


def reassign(db: Session, ticket: Ticket, *, actor: User, agent_id: int, note: str | None) -> dict:
    agent = db.get(User, agent_id)
    if agent is None or agent.role not in AGENT_ROLES:
        raise ValueError("Target agent is not an operational agent")
    previous = ticket.assigned_user_id
    ticket.assigned_user_id = agent.id
    ticket.queue = f"{ticket.region}-SUPPORT"
    ticket.updated_at = utcnow()
    db.add(RoutingAudit(
        ticket_id=ticket.id,
        candidate_scores_json=[],
        excluded_json=[],
        eligible_count=0,
        selected_agent_id=agent.id,
        selected_score=None,
        decision_reason=f"Manager override by {actor.full_name}: {note or 'no note'}",
        tie_break_applied=False,
        triggered_by="OVERRIDE",
        created_at=utcnow(),
    ))
    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="REASSIGNED",
        actor_name=actor.full_name,
        description=f"Manager override: {previous or 'unassigned'} → {agent.full_name}",
        metadata_json={"from": previous, "to": agent.id, "note": note},
        created_at=utcnow(),
    ))
    db.commit()
    db.refresh(ticket)
    return {
        "ticket_id": ticket.id,
        "assigned_to": {"id": agent.id, "name": agent.full_name, "region": agent.region},
        "previous_agent_id": previous,
        "note": note,
    }


def performance(db: Session) -> list[dict]:
    board = build_board(db)
    now = utcnow()
    resolved = db.execute(
        select(Ticket.assigned_user_id, Ticket.created_at, Ticket.resolved_at).where(
            Ticket.resolved_at.is_not(None), Ticket.assigned_user_id.is_not(None)
        )
    ).all()
    hours: dict[int, list[float]] = {}
    for agent_id, created, done in resolved:
        if created and done:
            hours.setdefault(agent_id, []).append((done - created).total_seconds() / 3600.0)
    out = []
    for row in board:
        samples = hours.get(row["agent_id"], [])
        out.append({
            **row,
            "resolved_tickets": len(samples),
            "avg_resolution_hours": round(sum(samples) / len(samples), 1) if samples else None,
            "on_shift_now": routing_math.is_within_shift(
                now, row["timezone"], row["shift"].split("-")[0], row["shift"].split("-")[1]
            ),
        })
    return out
