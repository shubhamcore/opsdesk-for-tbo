"""Ticket lifecycle: create, classify, plumb into the case graph, message, status."""
from __future__ import annotations

from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import next_ticket_number
from backend.models import ActivityTimeline, Booking, Message, Ticket, User
from backend.models.base import utcnow
from backend.services import sla as sla_service
from backend.services.classifier import INTENT_LABELS, get_classifier
from backend.services.extraction import extract_entities
from backend.services.linking import build_case_links


def _hours_until(value, now) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return round((value - now).total_seconds() / 3600.0, 2)


def _prior_count(db: Session, booking_id: int | None, exclude_id: int | None = None) -> int:
    if booking_id is None:
        return 0
    rows = db.scalars(
        select(Ticket.id).where(Ticket.booking_id == booking_id, Ticket.is_deleted.is_(False))
    ).all()
    return len([r for r in rows if r != exclude_id])


def classify_ticket_input(db: Session, *, title: str, description: str, tboh_id: str | None) -> tuple:
    extraction = extract_entities(title=title, description=description, tboh_field=tboh_id)
    booking = None
    if extraction.tboh_ids:
        booking = db.scalar(select(Booking).where(Booking.tboh_id == extraction.tboh_ids[0]))
    now = utcnow()
    prediction = get_classifier().classify(
        title=title,
        description=description,
        tboh_id=extraction.tboh_ids[0] if extraction.tboh_ids else None,
        extraction_source=extraction.extraction_source,
        prior_count=_prior_count(db, booking.id if booking else None),
        hours_to_checkin=_hours_until(booking.check_in if booking else None, now),
        hours_to_lcd=_hours_until(booking.lcd if booking else None, now),
    )
    return extraction, booking, prediction


def create_ticket(
    db: Session,
    *,
    actor: User,
    title: str,
    description: str,
    tboh_id: str | None = None,
    priority: str = "MEDIUM",
    agency_id: int | None = None,
    regional_holiday_flag: bool = False,
) -> tuple[Ticket, dict, dict, dict]:
    extraction, booking, prediction = classify_ticket_input(
        db, title=title, description=description, tboh_id=tboh_id
    )

    if actor.role == "AGENCY_REQUESTER":
        resolved_agency_id = actor.agency_id
        if resolved_agency_id is None:
            raise ValueError("Requester has no agency attached")
    elif agency_id is not None:
        resolved_agency_id = agency_id
    elif booking is not None:
        resolved_agency_id = booking.agency_id
    else:
        raise ValueError("Agency context is required: pass agency_id or reference a TBOH booking")

    now = utcnow()
    region = booking.region if booking else None
    if region is None:
        from backend.models import Agency

        agency = db.get(Agency, resolved_agency_id)
        region = agency.region if agency else "MEA"

    ticket = Ticket(
        ticket_number=next_ticket_number(db),
        booking_id=booking.id if booking else None,
        agency_id=resolved_agency_id,
        region=region,
        title=title.strip(),
        description=description.strip(),
        intent=prediction.intent,
        intent_confidence=round(prediction.confidence, 6),
        intent_reasoning=prediction.reasoning,
        intent_scores={k: round(v, 6) for k, v in prediction.scores.items()},
        intent_source=prediction.source,
        extracted_tboh=extraction.tboh_ids[0] if extraction.tboh_ids else None,
        extraction_source=extraction.extraction_source,
        priority=priority,
        status="OPEN",
        queue="UNASSIGNED",
        regional_holiday_flag=regional_holiday_flag,
        created_by_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()

    s = sla_service.compute_sla(
        created_at=now,
        priority=priority,
        lcd=booking.lcd if booking else None,
        check_in=booking.check_in if booking else None,
        regional_holiday_flag=regional_holiday_flag,
        now=now,
    )
    ticket.priority_due_at = s.priority_due_at
    ticket.effective_sla_due_at = s.effective_due_at
    ticket.sla_rule = s.governing_rule
    ticket.at_risk_threshold = s.at_risk_threshold

    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="TICKET_CREATED",
        actor_name=actor.full_name,
        description=(
            f"Ticket created and classified as {INTENT_LABELS.get(prediction.intent, prediction.intent)} "
            f"({prediction.confidence:.0%}, {prediction.source})"
        ),
        metadata_json={
            "intent": prediction.intent,
            "confidence": round(prediction.confidence, 6),
            "source": prediction.source,
            "extraction_source": extraction.extraction_source,
            "tboh_ids": extraction.tboh_ids,
        },
        created_at=now,
    ))
    db.flush()

    build_case_links(db, ticket)
    db.commit()
    db.refresh(ticket)
    return ticket, extraction.as_dict(), prediction.as_dict(), (
        {"tboh_id": booking.tboh_id} if booking else {}
    )


def add_message(db: Session, ticket: Ticket, actor: User, *, content: str, message_type: str) -> Message:
    message = Message(
        ticket_id=ticket.id,
        sender_id=actor.id,
        sender_name=actor.full_name,
        sender_role=actor.role,
        message_type=message_type,
        content=content.strip(),
        created_at=utcnow(),
    )
    db.add(message)
    if ticket.status == "OPEN" and message_type == "PUBLIC_REPLY":
        ticket.status = "IN_PROGRESS"
    ticket.updated_at = utcnow()
    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="INTERNAL_NOTE" if message_type == "INTERNAL_NOTE" else "PUBLIC_REPLY",
        actor_name=actor.full_name,
        description=(content.strip()[:180]),
        metadata_json={"message_type": message_type},
        created_at=utcnow(),
    ))
    db.commit()
    db.refresh(message)
    return message


def override_intent(db: Session, ticket: Ticket, actor: User, *, intent: str, note: str | None) -> Ticket:
    previous = ticket.intent
    ticket.intent = intent
    ticket.intent_source = "MANUAL"
    ticket.intent_reasoning = [
        f"Manually set to {INTENT_LABELS.get(intent, intent)} by {actor.full_name}"
        + (f" — {note}" if note else "")
    ]
    ticket.intent_scores = {intent: 1.0}
    ticket.intent_confidence = None
    ticket.updated_at = utcnow()
    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="INTENT_OVERRIDE",
        actor_name=actor.full_name,
        description=f"Intent changed from {previous or 'UNCLASSIFIED'} to {intent}",
        metadata_json={"previous": previous, "intent": intent, "note": note},
        created_at=utcnow(),
    ))
    db.commit()
    db.refresh(ticket)
    return ticket


def reclassify(db: Session, ticket: Ticket, actor: User) -> Ticket:
    booking = ticket.booking
    now = utcnow()
    prediction = get_classifier().classify(
        title=ticket.title,
        description=ticket.description,
        tboh_id=ticket.extracted_tboh,
        extraction_source=ticket.extraction_source,
        prior_count=_prior_count(db, ticket.booking_id, ticket.id),
        hours_to_checkin=_hours_until(booking.check_in if booking else None, now),
        hours_to_lcd=_hours_until(booking.lcd if booking else None, now),
    )
    previous = ticket.intent
    ticket.intent = prediction.intent
    ticket.intent_confidence = round(prediction.confidence, 6)
    ticket.intent_reasoning = prediction.reasoning
    ticket.intent_scores = {k: round(v, 6) for k, v in prediction.scores.items()}
    ticket.intent_source = prediction.source
    ticket.updated_at = now
    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="RECLASSIFIED",
        actor_name=actor.full_name,
        description=f"Re-ran the classifier: {previous or 'UNCLASSIFIED'} → {prediction.intent}",
        metadata_json={"previous": previous, "intent": prediction.intent,
                       "confidence": round(prediction.confidence, 6), "source": prediction.source},
        created_at=now,
    ))
    db.commit()
    db.refresh(ticket)
    return ticket


ALLOWED_STATUS = ("OPEN", "IN_PROGRESS", "PENDING_SUPPLIER", "ESCALATED", "RESOLVED")


def change_status(db: Session, ticket: Ticket, actor: User, *, status: str) -> Ticket:
    if status not in ALLOWED_STATUS:
        raise ValueError(f"Unknown status {status}")
    previous = ticket.status
    ticket.status = status
    ticket.updated_at = utcnow()
    ticket.resolved_at = utcnow() if status == "RESOLVED" else None
    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="STATUS_CHANGED",
        actor_name=actor.full_name,
        description=f"Status changed from {previous} to {status}",
        metadata_json={"previous": previous, "status": status},
        created_at=utcnow(),
    ))
    db.commit()
    db.refresh(ticket)
    return ticket
