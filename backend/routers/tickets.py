"""Ticket APIs — list, create, detail, messages, status, classification, case brief."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import (
    agency_payload,
    booking_payload,
    get_ticket_or_404,
    message_payload,
    next_ticket_number,
    sla_matrix,
    sla_payload,
    ticket_detail,
    ticket_row,
    user_payload,
)
from backend.api.schemas import (
    IntentOverrideRequest,
    MessageCreate,
    SideConversationCreate,
    StatusUpdateRequest,
    TicketCreate,
    TransferRequest,
)
from backend.database import get_db
from backend.models import Agency, Booking, Ticket, User
from backend.security import ANY_ROLE, OPS_ROLES, get_current_user, require_roles
from backend.services import tickets as ticket_service
from backend.services.case_brief import generate_case_brief
from backend.services.extraction import extract_entities

router = APIRouter(prefix="/api", tags=["tickets"])


@router.get("/tickets")
def list_tickets(
    search: str | None = None,
    sla_state: str | None = Query(default=None, pattern="^(HEALTHY|AT_RISK|BREACHED|RESOLVED)$"),
    status: str | None = None,
    region: str | None = None,
    priority: str | None = None,
    intent: str | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    query = select(Ticket).where(Ticket.is_deleted.is_(False))
    if user.role == "AGENCY_REQUESTER":
        query = query.where(Ticket.agency_id == user.agency_id)
    if status:
        query = query.where(Ticket.status == status)
    if region:
        query = query.where(Ticket.region == region)
    if priority:
        query = query.where(Ticket.priority == priority)
    if intent:
        query = query.where(Ticket.intent == intent)

    tickets = db.scalars(query.order_by(Ticket.created_at.desc())).all()

    if search:
        needle = search.strip().lower()
        tickets = [
            t for t in tickets
            if needle in (t.ticket_number or "").lower()
            or needle in (t.title or "").lower()
            or needle in (t.description or "").lower()
            or needle in (t.extracted_tboh or "").lower()
            or needle in ((t.booking.tboh_id if t.booking else "") or "").lower()
            or needle in ((t.agency.name if t.agency else "") or "").lower()
            or needle in ((t.assigned_user.full_name if t.assigned_user else "") or "").lower()
        ]

    rows = [ticket_row(db, t) for t in tickets]
    if sla_state:
        rows = [row for row in rows if row["sla"]["state"] == sla_state]
    rows.sort(key=lambda row: row["sla"]["effective_due_at"] or "")
    rows = rows[:limit]
    return {"count": len(rows), "tickets": rows, "sla_matrix": sla_matrix()}


@router.post("/tickets", status_code=http_status.HTTP_201_CREATED)
def create_ticket(
    payload: TicketCreate,
    user: User = Depends(require_roles(*ANY_ROLE)),
    db: Session = Depends(get_db),
) -> dict:
    ticket, extraction, classification, booking = ticket_service.create_ticket(
        db,
        actor=user,
        title=payload.title,
        description=payload.description,
        tboh_id=payload.tboh_id,
        priority=payload.priority,
        agency_id=payload.agency_id,
        regional_holiday_flag=payload.regional_holiday_flag,
    )
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "status": ticket.status,
        "queue": ticket.queue,
        "priority": ticket.priority,
        "intent": ticket.intent,
        "extraction": extraction,
        "classification": classification,
        "booking": booking_payload(ticket.booking, ticket) if ticket.booking else booking,
        "sla": sla_payload(ticket),
    }


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    return ticket_detail(db, ticket, user)


@router.post("/tickets/{ticket_id}/messages", status_code=http_status.HTTP_201_CREATED)
def add_message(
    ticket_id: str,
    payload: MessageCreate,
    user: User = Depends(require_roles(*ANY_ROLE)),
    db: Session = Depends(get_db),
) -> dict:
    if payload.message_type == "INTERNAL_NOTE" and user.role not in OPS_ROLES:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Internal notes are for internal roles only")
    ticket = get_ticket_or_404(db, ticket_id, user)
    message = ticket_service.add_message(
        db, ticket, user, content=payload.content, message_type=payload.message_type
    )
    return {"message": message_payload(message), "ticket_status": ticket.status}


@router.post("/tickets/{ticket_id}/status")
def update_status(
    ticket_id: str,
    payload: StatusUpdateRequest,
    user: User = Depends(require_roles(*ANY_ROLE)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    if user.role == "AGENCY_REQUESTER" and payload.status not in ("OPEN", "RESOLVED"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Requesters may only close or reopen their tickets")
    updated = ticket_service.change_status(db, ticket, user, status=payload.status)
    return {"ticket_id": updated.id, "status": updated.status, "resolved_at": updated.resolved_at}


@router.post("/tickets/{ticket_id}/reclassify")
def reclassify(
    ticket_id: str,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    updated = ticket_service.reclassify(db, ticket, user)
    return {
        "ticket_id": updated.id,
        "intent": updated.intent,
        "confidence": updated.intent_confidence,
        "source": updated.intent_source,
        "reasoning": updated.intent_reasoning,
    }


@router.post("/tickets/{ticket_id}/intent-override")
def override_intent(
    ticket_id: str,
    payload: IntentOverrideRequest,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    updated = ticket_service.override_intent(db, ticket, user, intent=payload.intent, note=payload.note)
    return {
        "ticket_id": updated.id,
        "intent": updated.intent,
        "intent_source": updated.intent_source,
        "note": payload.note,
    }


@router.get("/tickets/{ticket_id}/case-brief")
def case_brief(
    ticket_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ticket = get_ticket_or_404(db, ticket_id, user)
    return generate_case_brief(db, ticket)


# ----------------------------------------------------- side conversations & transfer

@router.get("/tickets/{ticket_id}/side-conversations")
def list_side_conversations(
    ticket_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from backend.api.deps import side_conversation_payload
    from backend.models import SideConversation

    ticket = get_ticket_or_404(db, ticket_id, user)
    if user.role not in OPS_ROLES:
        return {"conversations": [], "note": "Side conversations are internal-only"}
    rows = db.scalars(
        select(SideConversation)
        .where(SideConversation.ticket_id == ticket.id)
        .order_by(SideConversation.created_at)
    ).all()
    return {"conversations": [side_conversation_payload(row) for row in rows], "count": len(rows)}


@router.post("/tickets/{ticket_id}/side-conversations", status_code=http_status.HTTP_201_CREATED)
def create_side_conversation(
    ticket_id: str,
    payload: SideConversationCreate,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    from backend.api.deps import side_conversation_payload
    from backend.services import side_conversations as conversation_service

    ticket = get_ticket_or_404(db, ticket_id, user)
    conversation = conversation_service.create_conversation(
        db,
        ticket,
        user,
        channel_type=payload.channel_type,
        subject=payload.subject,
        counterparty_name=payload.counterparty_name,
        recipients=payload.recipients,
    )
    return side_conversation_payload(conversation)


@router.post("/tickets/{ticket_id}/transfer")
def transfer(
    ticket_id: str,
    payload: TransferRequest,
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    from backend.services import side_conversations as conversation_service

    ticket = get_ticket_or_404(db, ticket_id, user)
    return conversation_service.transfer_ticket(
        db, ticket, user,
        to_queue=payload.to_queue, note=payload.note, to_user_id=payload.to_user_id,
    )


# ---------------------------------------------------------------- context APIs

@router.get("/bookings/{tboh_id}")
def booking_context(
    tboh_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    booking = db.scalar(select(Booking).where(Booking.tboh_id == tboh_id.upper()))
    if booking is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, f"Booking {tboh_id} not found")
    tickets = db.scalars(
        select(Ticket).where(Ticket.booking_id == booking.id, Ticket.is_deleted.is_(False))
    ).all()
    if user.role == "AGENCY_REQUESTER":
        tickets = [t for t in tickets if t.agency_id == user.agency_id]
        if booking.agency_id != user.agency_id:
            raise HTTPException(http_status.HTTP_403_FORBIDDEN, "Booking belongs to another agency")
    rows = [ticket_row(db, t) for t in sorted(tickets, key=lambda t: t.created_at)]
    return {
        "booking": booking_payload(booking),
        "tickets": rows,
        "count": len(rows),
        "intent_mix": [
            intent for intent in {row["intent"] for row in rows if row["intent"]}
        ],
    }


@router.get("/agencies")
def list_agencies(
    user: User = Depends(require_roles(*OPS_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    agencies = db.scalars(select(Agency).where(Agency.is_deleted.is_(False)).order_by(Agency.id)).all()
    return {"agencies": [agency_payload(a) for a in agencies]}


@router.get("/extract")
def extract(
    text: str = Query(min_length=1, max_length=4000),
    tboh_id: str | None = None,
    user: User = Depends(get_current_user),
) -> dict:
    result = extract_entities(title="", description=text, tboh_field=tboh_id)
    return result.as_dict()


@router.get("/sla/matrix")
def sla_matrix_endpoint(user: User = Depends(get_current_user)) -> dict:
    return sla_matrix()
