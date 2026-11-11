"""Module 1 — booking-first case graph.

Links are derived from real relationships:

* ``SAME_BOOKING``              — same TBOH booking (confidence 1.0)
* ``DUPLICATE_REFUND_PATTERN``  — repeat refund chase on one booking
* ``DUPLICATE_AMENDMENT_PATTERN``— repeat change request on one booking
* ``SAME_AGENCY_INTENT_WINDOW`` — same agency + intent within 30 days

Each row stores a human-readable reason, so the UI never shows a bare score.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models import Ticket, TicketLink
from backend.models.base import utcnow

SAME_BOOKING = "SAME_BOOKING"
DUPLICATE_REFUND = "DUPLICATE_REFUND_PATTERN"
DUPLICATE_AMENDMENT = "DUPLICATE_AMENDMENT_PATTERN"
SAME_AGENCY_INTENT = "SAME_AGENCY_INTENT_WINDOW"

WINDOW_DAYS = 30
UI_LINK_TYPES = (SAME_BOOKING, DUPLICATE_REFUND, DUPLICATE_AMENDMENT)


def _existing(db: Session, source_id: int, target_id: int, link_type: str) -> bool:
    return db.scalar(
        select(TicketLink.id).where(
            TicketLink.source_ticket_id == source_id,
            TicketLink.target_ticket_id == target_id,
            TicketLink.link_type == link_type,
        )
    ) is not None


def _add(db: Session, source: Ticket, target: Ticket, link_type: str, confidence: float, reason: str) -> bool:
    if source.id == target.id or _existing(db, source.id, target.id, link_type):
        return False
    db.add(TicketLink(
        source_ticket_id=source.id,
        target_ticket_id=target.id,
        link_type=link_type,
        confidence_score=confidence,
        reason=reason,
        created_at=utcnow(),
    ))
    return True


def build_case_links(db: Session, ticket: Ticket) -> list[TicketLink]:
    """Create (or refresh) every defensible link for ``ticket``."""
    created: list[TicketLink] = []

    # ---------------------------------------------------- same booking
    if ticket.booking_id is not None:
        siblings = db.scalars(
            select(Ticket).where(
                Ticket.booking_id == ticket.booking_id,
                Ticket.id != ticket.id,
                Ticket.is_deleted.is_(False),
            )
        ).all()
        tboh = ticket.booking.tboh_id if ticket.booking else "the same booking"
        for sibling in siblings:
            if _add(db, ticket, sibling, SAME_BOOKING, 1.0,
                    f"Same booking {tboh} — identical operational context"):
                created.append(sibling)
            if ticket.intent == "REFUND_DELAY" and sibling.intent == "REFUND_DELAY":
                _add(db, ticket, sibling, DUPLICATE_REFUND, 0.8,
                     "Duplicate REFUND_DELAY pattern: same booking, repeat refund chase")
            if ticket.intent in ("AMENDMENT_NAME_DATE",) and sibling.intent == ticket.intent:
                _add(db, ticket, sibling, DUPLICATE_AMENDMENT, 0.75,
                     "Duplicate AMENDMENT pattern: same booking, repeat change request")

    # ------------------------------------- same agency + intent in window
    if ticket.intent and ticket.created_at:
        window_start = ticket.created_at - timedelta(days=WINDOW_DAYS)
        window_end = ticket.created_at + timedelta(days=WINDOW_DAYS)
        related = db.scalars(
            select(Ticket).where(
                Ticket.agency_id == ticket.agency_id,
                Ticket.intent == ticket.intent,
                Ticket.id != ticket.id,
                Ticket.is_deleted.is_(False),
                Ticket.created_at >= window_start,
                Ticket.created_at <= window_end,
            )
        ).all()
        for other in related:
            _add(
                db, ticket, other, SAME_AGENCY_INTENT, 0.6,
                f"Same agency and intent ({ticket.intent}) within {WINDOW_DAYS} days",
            )

    db.flush()
    return db.scalars(
        select(TicketLink).where(TicketLink.source_ticket_id == ticket.id)
    ).all()


def unified_case_tickets(db: Session, ticket: Ticket, *, all_types: bool = True) -> list[Ticket]:
    """Every ticket in the same operational case, ticket first."""
    links = db.scalars(
        select(TicketLink).where(
            or_(TicketLink.source_ticket_id == ticket.id, TicketLink.target_ticket_id == ticket.id)
        )
    ).all()
    ids = {ticket.id}
    for link in links:
        if not all_types and link.link_type not in UI_LINK_TYPES:
            continue
        ids.add(link.target_ticket_id if link.source_ticket_id == ticket.id else link.source_ticket_id)
    if not ids:
        return [ticket]
    rows = db.scalars(
        select(Ticket).where(Ticket.id.in_(ids), Ticket.is_deleted.is_(False))
    ).all()
    ordered = sorted(rows, key=lambda row: (row.id != ticket.id, row.created_at or utcnow()))
    return ordered


def related_tickets(db: Session, ticket: Ticket) -> list[dict]:
    """Link rows for the case graph, de-duplicated by ticket number."""
    links = db.scalars(
        select(TicketLink).where(
            or_(TicketLink.source_ticket_id == ticket.id, TicketLink.target_ticket_id == ticket.id)
        )
    ).all()
    seen: dict[int, dict] = {}
    for link in links:
        other_id = link.target_ticket_id if link.source_ticket_id == ticket.id else link.source_ticket_id
        other = db.get(Ticket, other_id)
        if other is None or other.is_deleted:
            continue
        current = seen.get(other.id)
        payload = {
            "ticket_id": other.id,
            "ticket_number": other.ticket_number,
            "title": other.title,
            "intent": other.intent,
            "status": other.status,
            "priority": other.priority,
            "created_at": other.created_at.isoformat() if other.created_at else None,
            "link_type": link.link_type,
            "confidence": round(float(link.confidence_score or 0), 3),
            "reason": link.reason,
        }
        # Keep the strongest link per ticket (SAME_BOOKING outranks soft matches).
        if current is None or payload["confidence"] > current["confidence"]:
            seen[other.id] = payload
    return sorted(seen.values(), key=lambda row: (-row["confidence"], row["ticket_number"]))
