"""AI Case Brief — extractive, evidence-bound summarisation.

Design rule: the brief may only state facts that exist in the database. Each
point is generated from concrete fields; when a field is missing the generator
says so instead of filling the gap. No generative invention.
"""
from __future__ import annotations

from collections import Counter
from datetime import timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Message, SideConversation, Ticket
from backend.models.base import utcnow
from backend.services import sla as sla_service
from backend.services.linking import unified_case_tickets


def _fmt_money(amount, currency: str | None) -> str:
    try:
        return f"{currency or 'USD'} {float(amount):,.0f}"
    except (TypeError, ValueError):
        return "amount not recorded"


def _local(dt, tz_name: str | None) -> str:
    if dt is None:
        return "not recorded"
    tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    local = dt.astimezone(tz)
    suffix = local.strftime("%Z")
    if not suffix or suffix.isdigit() or suffix[0] in "+-":
        total = int(local.utcoffset().total_seconds())
        sign = "+" if total >= 0 else "-"
        hours, mins = divmod(abs(total) // 60, 60)
        suffix = f"UTC{sign}{hours:02d}:{mins:02d}"
    return local.strftime("%d %b %Y %H:%M ") + suffix


def _duration(minutes: float) -> str:
    """Human duration for SLA copy: 45m, 3h 20m, 2d 4h."""
    minutes = abs(float(minutes))
    if minutes < 60:
        return f"{minutes:.0f}m"
    if minutes < 60 * 24:
        hours, mins = divmod(int(minutes), 60)
        return f"{hours}h {mins:02d}m"
    days, rem = divmod(int(minutes), 60 * 24)
    return f"{days}d {rem // 60}h"


def generate_case_brief(db: Session, ticket: Ticket) -> dict:
    case = unified_case_tickets(db, ticket)
    booking = ticket.booking
    now = utcnow()
    total_tickets = len(case)

    # ---- point 1: case shape ------------------------------------------------
    intents = Counter(t.intent for t in case if t.intent)
    intent_summary = ", ".join(f"{i}×{n}" for i, n in intents.most_common(3))
    first = min((t.created_at for t in case if t.created_at), default=None)
    if total_tickets == 1:
        line1_parts = ["This is currently the only ticket in the case"]
    else:
        line1_parts = [f"{total_tickets} linked tickets in this case"]
    if booking:
        line1_parts.append(f"for {booking.tboh_id} ({booking.hotel_name}, {booking.destination_city})")
    else:
        line1_parts.append("with no booking attached")
    if first:
        line1_parts.append(f"since {first.strftime('%d %b %Y')}")
    if intent_summary:
        line1_parts.append(f"— dominant intents: {intent_summary}")
    point1 = " ".join(line1_parts)

    # ---- point 2: money / supplier / messages -------------------------------
    p2: list[str] = []
    if booking:
        p2.append(
            f"Booking value {_fmt_money(booking.amount, booking.currency)} with supplier "
            f"{booking.supplier_name}; status {booking.booking_status}"
        )
    else:
        p2.append("No booking record is linked, so supplier and value are unknown")
    side = db.scalars(
        select(SideConversation).where(SideConversation.ticket_id == ticket.id)
    ).all()
    all_messages = db.scalars(select(Message).where(Message.ticket_id == ticket.id)).all()
    last_msg = db.scalars(
        select(Message).where(Message.ticket_id == ticket.id).order_by(Message.created_at.desc()).limit(1)
    ).first()
    p2.append(f"{len(all_messages)} thread message(s) and {len(side)} supplier/finance side conversation(s)")
    if last_msg:
        p2.append(
            f"last message from {last_msg.sender_name} on "
            f"{_local(last_msg.created_at, booking.timezone if booking else None)}"
        )
    point2 = "; ".join(p2) + "."

    # ---- point 3: travel urgency -------------------------------------------
    if booking:
        sla = sla_service.compute_sla(
            created_at=ticket.created_at,
            priority=ticket.priority,
            lcd=booking.lcd,
            check_in=booking.check_in,
            regional_holiday_flag=ticket.regional_holiday_flag,
            now=now,
            status=ticket.status,
        )
        bits = [
            f"Travel urgency: {sla.state} ({sla.governing_rule})",
            f"effective SLA due {_local(sla.effective_due_at, booking.timezone)}",
        ]
        if sla.seconds_remaining <= 0:
            bits.append(f"overdue by {_duration(sla.minutes_remaining)}")
        else:
            bits.append(f"{_duration(sla.minutes_remaining)} remaining")
        if booking.lcd:
            bits.append(f"LCD {_local(booking.lcd, booking.timezone)}")
        if booking.check_in:
            bits.append(f"check-in {_local(booking.check_in, booking.timezone)}")
    else:
        bits = ["No travel dates available; urgency cannot be derived from booking context"]
    point3 = "; ".join(bits) + "."

    return {
        "generated_at": now.isoformat(),
        "method": "extractive-template (evidence-bound, no generative inference)",
        "tickets_in_case": total_tickets,
        "points": [point1, point2, point3],
        "sources": {
            "ticket_ids": [t.id for t in case],
            "booking_id": booking.tboh_id if booking else None,
            "message_count": len(all_messages),
            "side_conversation_count": len(side),
        },
    }
