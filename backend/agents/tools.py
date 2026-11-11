"""Tool wrappers exposed to agents.

Each function is a thin, side-effect-free adapter over a service the REST API
already relies on. Tools take ``(db, ticket, **kwargs)`` and return plain data.
Keeping them side-effect free is deliberate: an agent proposes actions, it never
mutates the database — mutations stay behind the authenticated endpoints so RBAC
and the audit trail apply to machines exactly as they do to people.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import EscalationRecord, Message, SideConversation, Ticket, User
from backend.models.base import utcnow
from backend.services import analytics, assignment, linking
from backend.services import sla as sla_service
from backend.services.classifier import INTENT_LABELS, get_classifier
from backend.services.extraction import extract_entities

from backend.agents.runtime import ToolSpec


def _hours_until(value: datetime | None) -> float | None:
    if value is None:
        return None
    return round((value - utcnow()).total_seconds() / 3600, 2)


# --------------------------------------------------------------------- lookups

def classify_intent(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Run the live classifier over the ticket text plus booking context."""
    booking = ticket.booking
    prediction = get_classifier().classify(
        title=ticket.title,
        description=ticket.description,
        tboh_id=booking.tboh_id if booking else None,
        extraction_source="TOOL",
        prior_count=max(len(linking.unified_case_tickets(db, ticket)) - 1, 0),
        hours_to_checkin=_hours_until(booking.check_in if booking else None),
        hours_to_lcd=_hours_until(booking.lcd if booking else None),
    )
    return {
        "intent": prediction.intent,
        "label": INTENT_LABELS.get(prediction.intent, prediction.intent),
        "confidence": prediction.confidence,
        "source": prediction.source,
        "top_scores": dict(sorted(prediction.scores.items(), key=lambda kv: -kv[1])[:3]),
        "stored_intent": ticket.intent,
        "agrees_with_stored": prediction.intent == ticket.intent,
    }


def extract_references(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Regex entity extraction (TBOH references, amounts, dates, suppliers)."""
    result = extract_entities(
        title=ticket.title,
        description=ticket.description,
        tboh_field=ticket.booking.tboh_id if ticket.booking else None,
    )
    return result.as_dict()


def case_links(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Booking-first case graph: sibling tickets sharing the booking context."""
    tickets = linking.unified_case_tickets(db, ticket)
    return {
        "case_size": len(tickets),
        "ticket_numbers": [t.ticket_number for t in tickets],
        "other_tickets": [
            {
                "ticket_number": t.ticket_number,
                "intent": t.intent,
                "status": t.status,
                "priority": t.priority,
            }
            for t in tickets
            if t.id != ticket.id
        ],
    }


def sla_state(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Travel-aware SLA: MIN(priority deadline, LCD − 2h, check-in − 4h)."""
    booking = ticket.booking
    result = sla_service.compute_sla(
        created_at=ticket.created_at,
        priority=ticket.priority,
        lcd=booking.lcd if booking else None,
        check_in=booking.check_in if booking else None,
        regional_holiday_flag=ticket.regional_holiday_flag,
        now=utcnow(),
        status=ticket.status,
    )
    data = result.as_dict()
    return {
        "state": data["state"],
        "governing_rule": data["governing_rule"],
        "effective_due_at": data["effective_due_at"].isoformat() if data["effective_due_at"] else None,
        "minutes_remaining": data["minutes_remaining"],
        "elapsed_ratio": data["elapsed_ratio"],
        "at_risk_threshold": data["at_risk_threshold"],
        "holiday_adjustment_applied": data["holiday_adjustment_applied"],
        "missing_dates": data["missing_dates"],
        "reasons": data["reasons"],
        "urgency_weight": sla_service.urgency_weight(result, ticket.priority),
    }


def routing_decision(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Explainable routing comparator — candidates, exclusions and the winner."""
    decision = assignment.build_decision(db, ticket)
    return {
        "winner": decision["winner"],
        "candidates": decision["candidates"][:4],
        "excluded": decision["excluded"][:6],
        "eligible_count": len(decision["candidates"]),
        "excluded_count": len(decision["excluded"]),
        "tie_break_applied": decision["tie_break_applied"],
        "urgency_weight": decision["urgency_weight"],
        "explanation": assignment.explain(ticket, decision),
        "current_assignee_id": ticket.assigned_user_id,
    }


def thread_messages(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Main thread, split into customer-visible replies and internal notes."""
    messages = db.scalars(
        select(Message).where(Message.ticket_id == ticket.id).order_by(Message.created_at)
    ).all()
    return {
        "count": len(messages),
        "public": [
            {"sender": m.sender_name, "role": m.sender_role, "content": m.content}
            for m in messages
            if m.message_type == "PUBLIC_REPLY"
        ],
        "internal": [
            {"sender": m.sender_name, "role": m.sender_role, "content": m.content}
            for m in messages
            if m.message_type != "PUBLIC_REPLY"
        ],
    }


def side_conversations(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Independent supplier / finance / agency threads and their recipients."""
    conversations = db.scalars(
        select(SideConversation).where(SideConversation.ticket_id == ticket.id)
    ).all()
    return {
        "count": len(conversations),
        "conversations": [
            {
                "id": c.id,
                "channel_type": c.channel_type,
                "counterparty": c.counterparty_name,
                "explicit_recipients": list(c.explicit_recipients or []),
                "message_count": len(c.messages),
                "status": c.status,
            }
            for c in conversations
        ],
    }


def escalation_context(db: Session, ticket: Ticket, **_ignored: Any) -> dict:
    """Existing escalation (if any) plus escalation managers eligible by region."""
    records = db.scalars(
        select(EscalationRecord).where(EscalationRecord.ticket_id == ticket.id)
    ).all()
    managers = db.scalars(
        select(User).where(User.role == "ESCALATION_MANAGER", User.is_deleted.is_(False))
    ).all()
    regional = [m for m in managers if m.region == ticket.region]
    return {
        "already_escalated": bool(records) or ticket.escalated,
        "escalation_count": len(records),
        "eligible_managers": [
            {"id": m.id, "full_name": m.full_name, "region": m.region}
            for m in (regional or managers)
        ],
        "queue": ticket.queue,
        "status": ticket.status,
    }


def product_patterns(db: Session, ticket: Ticket, min_tickets: int = 3) -> dict:
    """Recurring (supplier, intent) patterns around this ticket's supplier."""
    suggestions = analytics.bug_suggestions(db, window_days=90, min_tickets=min_tickets)["suggestions"]
    supplier = ticket.booking.supplier_name if ticket.booking else None
    matching = [s for s in suggestions if supplier and s["supplier"] == supplier]
    return {
        "supplier": supplier,
        "all_suggestions": len(suggestions),
        "supplier_suggestions": matching[:3],
        "min_tickets": min_tickets,
    }


def activity_events(db: Session, ticket: Ticket, limit: int = 10) -> dict:
    from backend.models import ActivityTimeline

    events = db.scalars(
        select(ActivityTimeline)
        .where(ActivityTimeline.ticket_id == ticket.id)
        .order_by(ActivityTimeline.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "count": len(events),
        "events": [
            {"type": e.event_type, "actor": e.actor_name, "description": e.description}
            for e in events
        ],
    }


REGISTRY: dict[str, ToolSpec] = {
    t.name: t
    for t in (
        ToolSpec("classify_intent", "Run the trained intent classifier with booking context", classify_intent),
        ToolSpec("extract_references", "Extract TBOH ids, amounts, dates and suppliers from text", extract_references),
        ToolSpec("case_links", "Resolve the booking-first case graph for this ticket", case_links),
        ToolSpec("sla_state", "Compute the travel-aware effective SLA and its governing rule", sla_state),
        ToolSpec("routing_decision", "Score every eligible agent and explain the ranking", routing_decision),
        ToolSpec("thread_messages", "Read the main thread (public replies and internal notes)", thread_messages),
        ToolSpec("side_conversations", "Read supplier/finance/agency side conversations", side_conversations),
        ToolSpec("escalation_context", "Check escalation state and eligible escalation managers", escalation_context),
        ToolSpec("product_patterns", "Find recurring supplier/intent patterns for bug suggestions", product_patterns),
        ToolSpec("activity_events", "Read the immutable activity timeline for this ticket", activity_events),
    )
}
