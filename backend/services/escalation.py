"""Module 4 — Escalate to Escalation Manager with real ownership transfer."""
from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import sla_payload, ticket_row
from backend.models import ActivityTimeline, EscalationRecord, Ticket, User
from backend.models.base import utcnow

EM_QUEUE = "ESCALATION_MANAGER"
MIN_REASON = 8


def eligible_managers(db: Session) -> list[User]:
    return db.scalars(
        select(User).where(
            User.role == "ESCALATION_MANAGER",
            User.is_deleted.is_(False),
            User.is_online.is_(True),
        ).order_by(User.id)
    ).all()


def manager_load(db: Session, manager_id: int) -> int:
    return len(db.scalars(
        select(Ticket.id).where(
            Ticket.assigned_user_id == manager_id,
            Ticket.status == "ESCALATED",
            Ticket.is_deleted.is_(False),
        )
    ).all())


def pick_manager(db: Session) -> User:
    managers = eligible_managers(db)
    if not managers:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "No Escalation Manager is online")
    return min(managers, key=lambda m: (manager_load(db, m.id), m.id))


def escalate(db: Session, ticket: Ticket, *, actor: User, reason: str) -> dict:
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"An escalation reason of at least {MIN_REASON} characters is required",
        )
    if ticket.status == "RESOLVED":
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "A resolved ticket cannot be escalated",
        )

    manager = pick_manager(db)
    now = utcnow()
    previous = {
        "owner_id": ticket.assigned_user_id,
        "status": ticket.status,
        "queue": ticket.queue,
    }

    record = EscalationRecord(
        ticket_id=ticket.id,
        escalated_by_id=actor.id,
        assigned_em_id=manager.id,
        previous_owner_id=ticket.assigned_user_id,
        previous_status=ticket.status,
        previous_queue=ticket.queue,
        reason=reason,
        escalated_at=now,
    )
    db.add(record)

    ticket.status = "ESCALATED"
    ticket.queue = EM_QUEUE
    ticket.assigned_user_id = manager.id
    ticket.escalated = True
    ticket.escalated_at = now
    ticket.escalated_by_id = actor.id
    ticket.updated_at = now

    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="ESCALATED",
        actor_name=actor.full_name,
        description=(
            f"Escalated to {manager.full_name} (Escalation Manager). Reason: {reason}"
        ),
        metadata_json={
            "assigned_em_id": manager.id,
            "assigned_em": manager.full_name,
            "escalated_by_id": actor.id,
            "previous_owner_id": previous["owner_id"],
            "previous_status": previous["status"],
            "previous_queue": previous["queue"],
            "reason": reason,
        },
        created_at=now,
    ))
    # One transaction: ownership and the audit record land together or not at all.
    db.commit()
    db.refresh(ticket)

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "status": ticket.status,
        "queue": ticket.queue,
        "assigned_to": {
            "id": manager.id,
            "name": manager.full_name,
            "role": manager.role,
            "region": manager.region,
        },
        "previous": previous,
        "escalated_by": actor.full_name,
        "escalated_at": now.isoformat(),
        "reason": reason,
        "escalation_id": record.id,
    }


def history(db: Session, ticket: Ticket) -> list[dict]:
    from backend.api.deps import escalation_payload

    records = db.scalars(
        select(EscalationRecord)
        .where(EscalationRecord.ticket_id == ticket.id)
        .order_by(EscalationRecord.escalated_at.desc())
    ).all()
    return [escalation_payload(record, db) for record in records]


def queue(db: Session, viewer: User) -> dict:
    """Everything an Escalation Manager must act on: escalated first, then
    at-risk and breached work ordered by the travel deadline."""
    rows = db.scalars(
        select(Ticket).where(Ticket.is_deleted.is_(False)).order_by(Ticket.effective_sla_due_at.asc())
    ).all()
    escalated = [t for t in rows if t.status == "ESCALATED" or t.escalated]
    at_risk = [t for t in rows if t.status != "RESOLVED" and sla_payload(t)["state"] == "AT_RISK"]
    breached = [t for t in rows if t.status != "RESOLVED" and sla_payload(t)["state"] == "BREACHED"]

    pool: dict[int, Ticket] = {t.id: t for t in escalated + breached + at_risk}
    ordered = sorted(
        pool.values(),
        key=lambda t: (0 if t.status == "ESCALATED" else 1, t.effective_sla_due_at or utcnow()),
    )
    managers = eligible_managers(db)
    return {
        "counts": {
            "escalated": len(escalated),
            "at_risk": len(at_risk),
            "breached": len(breached),
            "healthy": len([t for t in rows if t.status != "RESOLVED"
                            and sla_payload(t)["state"] == "HEALTHY"]),
        },
        "managers": [
            {
                "id": m.id,
                "full_name": m.full_name,
                "region": m.region,
                "timezone": m.timezone,
                "active_escalations": manager_load(db, m.id),
                "is_online": m.is_online,
            }
            for m in managers
        ],
        "tickets": [ticket_row(db, t) for t in ordered[:40]],
        "viewer": viewer.full_name,
    }


def trend(db: Session, weeks: int = 8) -> dict:
    rows = db.scalars(select(EscalationRecord).order_by(EscalationRecord.escalated_at)).all()
    buckets: dict[str, int] = {}
    for record in rows:
        if record.escalated_at is None:
            continue
        iso = record.escalated_at.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        buckets[key] = buckets.get(key, 0) + 1
    ordered = sorted(buckets.items())[-weeks:]
    return {
        "by_week": [{"week": week, "count": count} for week, count in ordered],
        "total": len(rows),
        "window_weeks": weeks,
    }


def upcoming_deadlines(db: Session, hours: int = 48) -> list[dict]:
    cutoff = utcnow() + timedelta(hours=hours)
    rows = db.scalars(
        select(Ticket).where(
            Ticket.is_deleted.is_(False),
            Ticket.status != "RESOLVED",
        ).order_by(Ticket.effective_sla_due_at.asc())
    ).all()
    out = []
    for ticket in rows[:200]:  # bounded scan
        payload = sla_payload(ticket)
        out.append({
            "ticket_number": ticket.ticket_number,
            "title": ticket.title,
            "due_at": payload["effective_due_at"],
            "state": payload["state"],
            "governing_rule": payload["governing_rule"],
        })
    return [row for row in out if row["due_at"] and row["due_at"] <= cutoff.isoformat()][:10]
