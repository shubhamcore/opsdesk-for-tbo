"""Module 3 — independent side conversations and transfer-safe ownership.

Recipients are explicit and stored per conversation. A transfer changes queue
and owner only: conversation ids, recipient lists and message history are never
rewritten, and the new group's addresses are never inherited.
"""
from __future__ import annotations

import re

from fastapi import HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import ActivityTimeline, SideConversation, SideMessage, Ticket, TicketTransfer, User
from backend.models.base import utcnow

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
CHANNELS = ("SUPPLIER", "FINANCE", "AGENCY", "INTERNAL")


def validate_recipients(recipients: list[str]) -> list[str]:
    cleaned: list[str] = []
    for address in recipients or []:
        value = (address or "").strip().lower()
        if not value:
            continue
        if not EMAIL_RE.match(value):
            raise HTTPException(
                http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"'{address}' is not a valid email address",
            )
        if value not in cleaned:
            cleaned.append(value)
    if not cleaned:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            "At least one explicit recipient is required",
        )
    return cleaned


def create_conversation(
    db: Session,
    ticket: Ticket,
    actor: User,
    *,
    channel_type: str,
    subject: str,
    counterparty_name: str,
    recipients: list[str],
) -> SideConversation:
    channel = (channel_type or "").upper()
    if channel not in CHANNELS:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown channel {channel_type}")
    cleaned = validate_recipients(recipients)
    conversation = SideConversation(
        ticket_id=ticket.id,
        channel_type=channel,
        subject=subject.strip(),
        counterparty_name=counterparty_name.strip(),
        explicit_recipients=cleaned,
        created_by_group=ticket.queue,
        status="OPEN",
        created_at=utcnow(),
    )
    db.add(conversation)
    db.flush()
    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="SIDE_CONVERSATION_CREATED",
        actor_name=actor.full_name,
        description=f"{channel.title()} conversation opened with {counterparty_name} ({', '.join(cleaned)})",
        metadata_json={"conversation_id": conversation.id, "recipients": cleaned},
        created_at=utcnow(),
    ))
    db.commit()
    db.refresh(conversation)
    return conversation


def send_side_message(db: Session, conversation: SideConversation, actor: User, *, content: str) -> dict:
    if conversation.status != "OPEN":
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Conversation is closed")
    recipients = list(conversation.explicit_recipients or [])
    if not recipients:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Conversation has no recipients")

    created = []
    now = utcnow()
    for address in recipients:
        message = SideMessage(
            side_conversation_id=conversation.id,
            sender_email=actor.email,
            recipient_email=address,
            content=content.strip(),
            direction="OUTBOUND",
            status="SENT",
            created_at=now,
        )
        db.add(message)
        created.append(message)
    db.add(ActivityTimeline(
        ticket_id=conversation.ticket_id,
        event_type="SIDE_MESSAGE_SENT",
        actor_name=actor.full_name,
        description=(
            f"{conversation.channel_type.title()} message to "
            f"{conversation.counterparty_name} ({len(recipients)} recipient(s))"
        ),
        metadata_json={"conversation_id": conversation.id, "recipients": recipients},
        created_at=now,
    ))
    db.commit()
    return {
        "conversation_id": conversation.id,
        "messages_created": len(created),
        "recipients": recipients,
        "content": content.strip(),
    }


def transfer_ticket(
    db: Session,
    ticket: Ticket,
    actor: User,
    *,
    to_queue: str,
    note: str | None,
    to_user_id: int | None = None,
) -> dict:
    target_queue = (to_queue or "").strip()
    if not target_queue:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Target queue is required")
    if target_queue == ticket.queue:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Ticket is already in that queue")

    before = db.scalars(
        select(SideConversation).where(SideConversation.ticket_id == ticket.id)
    ).all()
    before_map = {c.id: list(c.explicit_recipients or []) for c in before}

    from_queue = ticket.queue
    previous_user = ticket.assigned_user_id
    now = utcnow()

    transfer = TicketTransfer(
        ticket_id=ticket.id,
        from_queue=from_queue,
        to_queue=target_queue,
        from_user_id=previous_user,
        to_user_id=to_user_id,
        note=note,
        preserved_side_conversations=len(before),
        preserved_recipients=[{"conversation_id": cid, "recipients": rec} for cid, rec in before_map.items()],
        transferred_by_id=actor.id,
        created_at=now,
    )
    db.add(transfer)

    ticket.queue = target_queue
    if to_user_id is not None:
        ticket.assigned_user_id = to_user_id
    ticket.updated_at = now
    db.flush()

    # ---- verification: nothing about the conversations changed -------------
    after = db.scalars(
        select(SideConversation).where(SideConversation.ticket_id == ticket.id)
    ).all()
    after_map = {c.id: list(c.explicit_recipients or []) for c in after}
    recipients_unchanged = before_map == after_map

    db.add(ActivityTimeline(
        ticket_id=ticket.id,
        event_type="TRANSFERRED",
        actor_name=actor.full_name,
        description=(
            f"Transferred {from_queue} → {target_queue}. "
            f"{len(after)} side conversation(s) preserved with original recipients."
        ),
        metadata_json={
            "from_queue": from_queue,
            "to_queue": target_queue,
            "preserved_conversations": len(after),
            "preserved_recipients": [rec for rec in after_map.values()],
            "recipients_unchanged": recipients_unchanged,
            "note": note,
        },
        created_at=now,
    ))
    db.commit()
    db.refresh(ticket)

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "from_queue": from_queue,
        "to_queue": target_queue,
        "preserved_side_conversations": len(after),
        "recipients_unchanged": recipients_unchanged,
        "message": (
            f"Ticket moved to {target_queue}. Original recipients unchanged "
            f"({len(after)} conversation(s), {sum(len(v) for v in after_map.values())} recipient(s))."
        ),
        "transfer_id": transfer.id,
        "note": note,
    }
