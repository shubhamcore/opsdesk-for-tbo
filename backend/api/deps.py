"""Serialisation helpers and access rules shared by the routers.

Everything the API returns is built here so the shape stays consistent between
list, detail and mutation endpoints.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    ActivityTimeline,
    Agency,
    Booking,
    EscalationRecord,
    Message,
    RoutingAudit,
    SideConversation,
    SideMessage,
    Ticket,
    TicketTransfer,
    User,
)
from backend.models.base import utcnow
from backend.security import OPS_ROLES
from backend.services import sla as sla_service
from backend.services.case_brief import generate_case_brief
from backend.services.classifier import INTENT_LABELS
from backend.services.linking import related_tickets


# ------------------------------------------------------------------ primitives

def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _local(dt: datetime | None, tz_name: str | None) -> str | None:
    if dt is None:
        return None
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = timezone.utc
    local = dt.astimezone(tz)
    suffix = local.strftime("%Z")
    if not suffix or suffix.isdigit() or suffix[0] in "+-":
        total = int(local.utcoffset().total_seconds())
        sign = "+" if total >= 0 else "-"
        hours, mins = divmod(abs(total) // 60, 60)
        suffix = f"UTC{sign}{hours:02d}:{mins:02d}"
    return local.strftime("%d %b %Y %H:%M ") + suffix


def agency_payload(agency: Agency | None) -> dict | None:
    if agency is None:
        return None
    return {
        "id": agency.id,
        "code": agency.code,
        "name": agency.name,
        "tier": agency.tier,
        "region": agency.region,
        "contact_email": agency.contact_email,
    }


def user_payload(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "region": user.region,
        "timezone": user.timezone,
        "skill_rank": user.skill_rank,
        "max_capacity": user.max_capacity,
        "is_online": user.is_online,
        "shift": f"{user.shift_start}-{user.shift_end}",
        "agency_id": user.agency_id,
    }


def booking_payload(booking: Booking | None, ticket: Ticket | None = None) -> dict | None:
    if booking is None:
        return None
    payload = {
        "id": booking.id,
        "tboh_id": booking.tboh_id,
        "hotel_name": booking.hotel_name,
        "supplier_name": booking.supplier_name,
        "supplier_email": booking.supplier_email,
        "destination_city": booking.destination_city,
        "destination_country": booking.destination_country,
        "region": booking.region,
        "timezone": booking.timezone,
        "check_in": iso(booking.check_in),
        "check_out": iso(booking.check_out),
        "lcd": iso(booking.lcd),
        "booking_status": booking.booking_status,
        "amount": float(booking.amount) if booking.amount is not None else None,
        "currency": booking.currency,
        "passenger_name": booking.passenger_name,
        "agency_id": booking.agency_id,
        "agency_name": booking.agency.name if booking.agency else None,
        "agency_tier": booking.agency.tier if booking.agency else None,
    }
    payload["display_timezone"] = booking.timezone
    payload["check_in_local"] = _local(booking.check_in, booking.timezone)
    payload["lcd_local"] = _local(booking.lcd, booking.timezone)
    if ticket is not None:
        payload["ticket_region"] = ticket.region
    return payload


def sla_payload(ticket: Ticket) -> dict:
    booking = ticket.booking
    now = utcnow()
    result = sla_service.compute_sla(
        created_at=ticket.created_at,
        priority=ticket.priority,
        lcd=booking.lcd if booking else None,
        check_in=booking.check_in if booking else None,
        regional_holiday_flag=ticket.regional_holiday_flag,
        now=now,
        status=ticket.status,
    )
    data = result.as_dict()
    for key in ("effective_due_at", "priority_due_at", "lcd_deadline", "checkin_deadline"):
        data[key] = iso(data[key])
    data["urgency_weight"] = sla_service.urgency_weight(result, ticket.priority)
    return data


def sla_matrix() -> dict:
    return {
        "priority_hours": dict(sla_service.PRIORITY_SLA_HOURS),
        "lcd_buffer_hours": sla_service.LCD_BUFFER_HOURS,
        "checkin_buffer_hours": sla_service.CHECKIN_BUFFER_HOURS,
        "default_at_risk_threshold": sla_service.DEFAULT_AT_RISK_THRESHOLD,
        "holiday_at_risk_threshold": sla_service.HOLIDAY_AT_RISK_THRESHOLD,
    }


# --------------------------------------------------------------------- tickets

def ticket_row(db: Session, ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "description": ticket.description,
        "intent": ticket.intent,
        "intent_label": INTENT_LABELS.get(ticket.intent or "", ticket.intent),
        "intent_confidence": ticket.intent_confidence,
        "intent_source": ticket.intent_source,
        "priority": ticket.priority,
        "status": ticket.status,
        "queue": ticket.queue,
        "region": ticket.region,
        "assigned_to": ticket.assigned_user.full_name if ticket.assigned_user else None,
        "assigned_user_id": ticket.assigned_user_id,
        "agency": ticket.agency.name if ticket.agency else None,
        "agency_id": ticket.agency_id,
        "booking": booking_payload(ticket.booking, ticket),
        "sla": sla_payload(ticket),
        "escalated": ticket.escalated,
        "regional_holiday_flag": ticket.regional_holiday_flag,
        "created_at": iso(ticket.created_at),
        "updated_at": iso(ticket.updated_at),
        "resolved_at": iso(ticket.resolved_at),
    }


def message_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "sender_name": message.sender_name,
        "sender_role": message.sender_role,
        "message_type": message.message_type,
        "content": message.content,
        "created_at": iso(message.created_at),
    }


def side_message_payload(message: SideMessage) -> dict:
    return {
        "id": message.id,
        "sender_email": message.sender_email,
        "recipient_email": message.recipient_email,
        "content": message.content,
        "direction": message.direction,
        "status": message.status,
        "created_at": iso(message.created_at),
    }


def side_conversation_payload(conversation: SideConversation) -> dict:
    return {
        "id": conversation.id,
        "ticket_id": conversation.ticket_id,
        "channel_type": conversation.channel_type,
        "subject": conversation.subject,
        "counterparty_name": conversation.counterparty_name,
        "explicit_recipients": list(conversation.explicit_recipients or []),
        "created_by_group": conversation.created_by_group,
        "status": conversation.status,
        "created_at": iso(conversation.created_at),
        "messages": [side_message_payload(m) for m in conversation.messages],
    }


def activity_payload(event: ActivityTimeline) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "actor_name": event.actor_name,
        "description": event.description,
        "metadata": event.metadata_json or {},
        "created_at": iso(event.created_at),
    }


def routing_audit_payload(audit: RoutingAudit) -> dict:
    return {
        "id": audit.id,
        "ticket_id": audit.ticket_id,
        "candidates": audit.candidate_scores_json or [],
        "excluded": audit.excluded_json or [],
        "eligible_count": audit.eligible_count,
        "selected_agent_id": audit.selected_agent_id,
        "selected_agent": (
            audit.selected_agent.full_name
            if getattr(audit, "selected_agent", None) is not None
            else None
        ),
        "selected_score": audit.selected_score,
        "decision_reason": audit.decision_reason,
        "tie_break_applied": audit.tie_break_applied,
        "triggered_by": audit.triggered_by,
        "created_at": iso(audit.created_at),
    }


def classification_payload(ticket: Ticket) -> dict:
    return {
        "intent": ticket.intent,
        "label": INTENT_LABELS.get(ticket.intent or "", ticket.intent),
        "confidence": ticket.intent_confidence,
        "reasoning": list(ticket.intent_reasoning or []),
        "scores": dict(ticket.intent_scores or {}),
        "source": ticket.intent_source,
    }


def escalation_payload(record: EscalationRecord, db: Session) -> dict:
    em = db.get(User, record.assigned_em_id)
    by = db.get(User, record.escalated_by_id)
    return {
        "id": record.id,
        "assigned_em": em.full_name if em else None,
        "assigned_em_id": record.assigned_em_id,
        "escalated_by": by.full_name if by else None,
        "previous_owner_id": record.previous_owner_id,
        "previous_status": record.previous_status,
        "previous_queue": record.previous_queue,
        "reason": record.reason,
        "escalated_at": iso(record.escalated_at),
    }


def transfer_payload(transfer: TicketTransfer) -> dict:
    return {
        "id": transfer.id,
        "from_queue": transfer.from_queue,
        "to_queue": transfer.to_queue,
        "note": transfer.note,
        "preserved_side_conversations": transfer.preserved_side_conversations,
        "preserved_recipients": transfer.preserved_recipients or [],
        "created_at": iso(transfer.created_at),
    }


def ticket_detail(db: Session, ticket: Ticket, viewer: User) -> dict:
    internal = viewer.role in OPS_ROLES
    payload = ticket_row(db, ticket)
    payload["classification"] = classification_payload(ticket)

    messages = db.scalars(
        select(Message).where(Message.ticket_id == ticket.id).order_by(Message.created_at)
    ).all()
    if not internal:
        messages = [m for m in messages if m.message_type == "PUBLIC_REPLY"]
    payload["messages"] = [message_payload(m) for m in messages]

    if internal:
        conversations = db.scalars(
            select(SideConversation)
            .where(SideConversation.ticket_id == ticket.id)
            .order_by(SideConversation.created_at)
        ).all()
        payload["side_conversations"] = [side_conversation_payload(c) for c in conversations]
        audits = db.scalars(
            select(RoutingAudit)
            .where(RoutingAudit.ticket_id == ticket.id)
            .order_by(RoutingAudit.created_at.desc())
        ).all()
        payload["routing_audits"] = [routing_audit_payload(a) for a in audits]
        events = db.scalars(
            select(ActivityTimeline)
            .where(ActivityTimeline.ticket_id == ticket.id)
            .order_by(ActivityTimeline.created_at.desc())
        ).all()
        payload["activity_timeline"] = [activity_payload(e) for e in events]
        transfers = db.scalars(
            select(TicketTransfer)
            .where(TicketTransfer.ticket_id == ticket.id)
            .order_by(TicketTransfer.created_at.desc())
        ).all()
        payload["transfers"] = [transfer_payload(t) for t in transfers]
        records = db.scalars(
            select(EscalationRecord)
            .where(EscalationRecord.ticket_id == ticket.id)
            .order_by(EscalationRecord.escalated_at.desc())
        ).all()
        payload["escalations"] = [escalation_payload(r, db) for r in records]
        payload["case_brief"] = generate_case_brief(db, ticket)
    else:
        payload["side_conversations"] = []
        payload["routing_audits"] = []
        payload["activity_timeline"] = []
        payload["transfers"] = []
        payload["escalations"] = []
        payload["case_brief"] = generate_case_brief(db, ticket)

    payload["related_tickets"] = related_tickets(db, ticket)
    return payload


# ------------------------------------------------------------- access control

def agency_scope(user: User) -> int | None:
    """Agency id a requester is limited to; ``None`` for internal roles."""
    return user.agency_id if user.role == "AGENCY_REQUESTER" else None


def ensure_ticket_access(ticket: Ticket, user: User) -> None:
    if user.role == "AGENCY_REQUESTER" and ticket.agency_id != user.agency_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This ticket belongs to another agency",
        )


def get_ticket_or_404(db: Session, ticket_id: int | str, user: User) -> Ticket:
    """Resolve a ticket by numeric id or by human ticket number (``TCK-101``).

    Accepting the ticket number keeps URLs shareable — the console links to
    ``/w2/TCK-101`` and every API call behind it uses the same identifier.
    """
    ticket = None
    if isinstance(ticket_id, str):
        key = ticket_id.strip().upper()
        if key.startswith("TCK-"):
            ticket = db.scalar(select(Ticket).where(Ticket.ticket_number == key))
        elif key.isdigit():
            ticket = db.get(Ticket, int(key))
    else:
        ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    ensure_ticket_access(ticket, user)
    return ticket


def resolve_agency_id(db: Session, user: User, tboh_id: str | None, payload_agency_id: int | None) -> int:
    """Ops users may raise tickets for an agency; requesters are pinned."""
    if user.role == "AGENCY_REQUESTER":
        if user.agency_id is None:
            raise ValueError("Requester has no agency attached")
        return user.agency_id
    if payload_agency_id is not None:
        return payload_agency_id
    if tboh_id:
        booking = db.scalar(select(Booking).where(Booking.tboh_id == tboh_id))
        if booking is not None:
            return booking.agency_id
    raise ValueError("Agency context is required: pass agency_id or reference a TBOH booking")


def next_ticket_number(db: Session) -> str:
    numbers = db.scalars(select(Ticket.ticket_number)).all()
    highest = 100
    for number in numbers:
        digits = "".join(ch for ch in (number or "") if ch.isdigit())
        if digits:
            highest = max(highest, int(digits))
    return f"TCK-{highest + 1}"
