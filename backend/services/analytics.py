"""Module 5 — Ops Lead analytics and product intelligence.

Every figure is computed from ticket rows. Bug proposals require at least
``min_tickets`` tickets sharing the same supplier *and* intent — the threshold
is enforced, not decorative.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import sla_payload, ticket_row
from backend.models import ProductBug, ThemeTag, Ticket, TicketLink
from backend.models.base import utcnow
from backend.services import sla as sla_service
from backend.services.classifier import INTENT_LABELS

INVENTORY_INTENT = "INVENTORY_RATE_SYNC_BUG"
REFUND_INTENT = "REFUND_DELAY"

THEME_RULES = {
    "INVENTORY_RATE_SYNC_BUG": ("API / inventory", ["api", "cache", "sync", "rate", "availability", "error"]),
    "REFUND_DELAY": ("Refunds", ["refund", "credit", "credited", "reversal", "money"]),
    "VOUCHER_CONFIRMATION_ISSUE": ("Vouchers", ["voucher", "confirmation", "confirmed", "front desk"]),
    "CANCELLATION_LCD_WAIVER": ("Cancellation policy", ["waiver", "lcd", "penalty", "cancel"]),
    "SPECIAL_REQUEST": ("Guest experience", ["honeymoon", "cake", "cot", "view", "birthday"]),
    "SUPPLIER_OVERBOOKING_RELOCATION": ("Overbooking", ["overbooked", "oversold", "relocation", "walked"]),
    "BILLING_INVOICE_DISPUTE": ("Billing", ["invoice", "credit note", "commission", "gst"]),
    "AMENDMENT_NAME_DATE": ("Amendments", ["amend", "name", "date change", "passport"]),
}


def _iso_week(value) -> str:
    iso = value.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def queue_snapshot(db: Session) -> dict:
    tickets = db.scalars(
        select(Ticket).where(Ticket.is_deleted.is_(False)).order_by(Ticket.created_at)
    ).all()

    states = {"HEALTHY": 0, "AT_RISK": 0, "BREACHED": 0, "RESOLVED": 0}
    by_region: Counter = Counter()
    by_intent: Counter = Counter()
    weekly: Counter = Counter()
    by_priority: Counter = Counter()
    agent_loads: dict[int, int] = defaultdict(int)
    rows: list[dict] = []

    for ticket in tickets:
        sla = sla_payload(ticket)
        states[sla["state"]] = states.get(sla["state"], 0) + 1
        by_region[ticket.region] += 1
        by_intent[ticket.intent or "UNCLASSIFIED"] += 1
        by_priority[ticket.priority] += 1
        if ticket.created_at:
            weekly[_iso_week(ticket.created_at)] += 1
        if ticket.assigned_user_id:
            agent_loads[ticket.assigned_user_id] += 1
        rows.append(ticket_row(db, ticket))

    total = len(tickets)
    active = len([t for t in tickets if t.status not in ("RESOLVED",)])
    compliance = round(100 * states["HEALTHY"] / active, 2) if active else 0.0

    from backend.models import User

    agents = db.scalars(
        select(User).where(User.is_deleted.is_(False), User.role.in_(("OPS_AGENT", "ESCALATION_MANAGER", "OPS_LEAD")))
    ).all()
    workload = [
        {
            "agent_id": agent.id,
            "name": agent.full_name,
            "region": agent.region,
            "active_load": agent_loads.get(agent.id, 0),
            "max_capacity": agent.max_capacity,
            "skill_rank": agent.skill_rank,
            "is_online": agent.is_online,
        }
        for agent in agents
    ]

    upcoming = sorted(
        [row for row in rows if row["status"] != "RESOLVED" and row["sla"]["state"] != "RESOLVED"],
        key=lambda row: row["sla"]["effective_due_at"] or "",
    )[:6]

    return {
        "totals": {
            "tickets": total,
            "active": active,
            "at_risk": states["AT_RISK"],
            "breached": states["BREACHED"],
            "escalated": len([t for t in tickets if t.escalated or t.status == "ESCALATED"]),
            "unassigned": len([t for t in tickets if t.assigned_user_id is None]),
        },
        "sla_states": states,
        "sla_compliance": {
            "compliance_pct": compliance,
            "healthy": states["HEALTHY"],
            "active": active,
            "definition": "HEALTHY tickets / all non-resolved tickets",
        },
        "by_region": [{"region": region, "count": count} for region, count in by_region.most_common()],
        "by_intent": [
            {"intent": intent, "label": INTENT_LABELS.get(intent, intent), "count": count}
            for intent, count in by_intent.most_common()
        ],
        "by_priority": [{"priority": p, "count": c} for p, c in by_priority.most_common()],
        "weekly_volume": [{"week": week, "count": count} for week, count in sorted(weekly.items())],
        "agent_workload": workload,
        "next_travel": upcoming,
        "sla_matrix": __import__("backend.api.deps", fromlist=["sla_matrix"]).sla_matrix(),
        "tickets": rows,
    }


def product_intelligence(db: Session, window_days: int = 30) -> dict:
    since = utcnow() - timedelta(days=window_days)
    tickets = db.scalars(
        select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.created_at >= since)
    ).all()
    if not tickets:
        tickets = db.scalars(select(Ticket).where(Ticket.is_deleted.is_(False))).all()

    intent_counts = Counter(t.intent or "UNCLASSIFIED" for t in tickets)
    supplier_counts: Counter = Counter()
    inventory_tickets = []
    refund_open = []
    resolutions: list[float] = []
    region_stats: dict[str, dict] = defaultdict(lambda: {"tickets": 0, "breached": 0, "resolved": 0, "hours": []})
    weekly: Counter = Counter()

    for ticket in tickets:
        booking = ticket.booking
        if booking:
            supplier_counts[booking.supplier_name] += 1
        if ticket.intent == INVENTORY_INTENT:
            inventory_tickets.append(ticket)
        sla = sla_payload(ticket)
        stats = region_stats[ticket.region]
        stats["tickets"] += 1
        if sla["state"] == "BREACHED":
            stats["breached"] += 1
        if ticket.status == "RESOLVED":
            stats["resolved"] += 1
            if ticket.resolved_at and ticket.created_at:
                hours = (ticket.resolved_at - ticket.created_at).total_seconds() / 3600
                resolutions.append(hours)
                stats["hours"].append(hours)
        if ticket.intent == REFUND_INTENT and ticket.status != "RESOLVED":
            refund_open.append((ticket, sla))
        weekly[_iso_week(ticket.created_at)] += 1

    def bucket(hours: float) -> str:
        if hours <= 4:
            return "0-4h"
        if hours <= 12:
            return "4-12h"
        if hours <= 24:
            return "12-24h"
        if hours <= 48:
            return "24-48h"
        return "48h+"

    buckets: Counter = Counter(bucket(h) for h in resolutions)
    order = ["0-4h", "4-12h", "12-24h", "24-48h", "48h+"]
    ages = [abs(sla["minutes_remaining"]) / 60 for _, sla in refund_open]
    oldest = None
    if refund_open:
        oldest_ticket, _ = max(refund_open, key=lambda item: item[0].created_at)
        oldest = {
            "ticket_number": oldest_ticket.ticket_number,
            "title": oldest_ticket.title,
            "supplier": oldest_ticket.booking.supplier_name if oldest_ticket.booking else None,
            "age_hours": round((utcnow() - oldest_ticket.created_at).total_seconds() / 3600, 1),
        }

    themes = [
        {"name": name, "category": THEME_RULES.get(name, ("Other", []))[0],
         "occurrences": count, "distinct_suppliers": 0}
        for name, count in intent_counts.most_common() if name in THEME_RULES
    ]

    return {
        "window_days": window_days,
        "window_start": since.isoformat(),
        "tickets_in_window": len(tickets),
        "intent_distribution": [
            {"intent": intent, "label": INTENT_LABELS.get(intent, intent), "count": count}
            for intent, count in intent_counts.most_common()
        ],
        "supplier_complaints": [
            {"supplier": supplier, "tickets": count} for supplier, count in supplier_counts.most_common()
        ],
        "resolution_time_distribution": [
            {"bucket": label, "count": buckets.get(label, 0)} for label in order
        ],
        "resolution_stats": {
            "resolved": len(resolutions),
            "avg_hours": round(sum(resolutions) / len(resolutions), 2) if resolutions else None,
        },
        "weekly_trends": [{"week": week, "count": count} for week, count in sorted(weekly.items())],
        "refund_bottleneck": {
            "open_refunds": len(refund_open),
            "avg_open_age_hours": round(sum(ages) / len(ages), 2) if ages else 0,
            "avg_resolved_hours": round(sum(resolutions) / len(resolutions), 2) if resolutions else None,
            "oldest_open": oldest,
        },
        "regional_performance": [
            {
                "region": region,
                "tickets": stats["tickets"],
                "breached": stats["breached"],
                "resolved": stats["resolved"],
                "avg_resolution_hours": round(sum(stats["hours"]) / len(stats["hours"]), 1)
                if stats["hours"] else None,
            }
            for region, stats in sorted(region_stats.items())
        ],
        "inventory_sync": {
            "ticket_count": len(inventory_tickets),
            "suppliers": sorted({t.booking.supplier_name for t in inventory_tickets if t.booking}),
            "ticket_numbers": [t.ticket_number for t in inventory_tickets][:12],
        },
        "themes": themes,
        "theme_tags": [
            {
                "name": tag.name,
                "category": tag.category,
                "occurrences": tag.occurrence_count,
                "distinct_suppliers": tag.distinct_suppliers,
                "last_seen": tag.last_seen.isoformat() if tag.last_seen else None,
            }
            for tag in db.scalars(select(ThemeTag).order_by(ThemeTag.occurrence_count.desc())).all()
        ],
        "data_notice": "All figures are computed from SYNTHETIC seeded tickets",
    }


def refresh_themes(db: Session) -> list[dict]:
    tickets = db.scalars(select(Ticket).where(Ticket.is_deleted.is_(False))).all()
    counts: Counter = Counter()
    suppliers: dict[str, set[str]] = defaultdict(set)
    for ticket in tickets:
        intent = ticket.intent
        if intent not in THEME_RULES:
            continue
        text = f"{ticket.title} {ticket.description}".lower()
        keywords = THEME_RULES[intent][1]
        if any(keyword in text for keyword in keywords):
            counts[intent] += 1
            if ticket.booking:
                suppliers[intent].add(ticket.booking.supplier_name)

    now = utcnow()
    existing = {tag.name: tag for tag in db.scalars(select(ThemeTag)).all()}
    for intent, count in counts.items():
        tag = existing.get(intent)
        if tag is None:
            tag = ThemeTag(name=intent, category=THEME_RULES[intent][0], intent=intent)
            db.add(tag)
        tag.occurrence_count = count
        tag.distinct_suppliers = len(suppliers[intent])
        tag.last_seen = now
    db.commit()
    return [
        {
            "name": tag.name,
            "category": tag.category,
            "occurrences": tag.occurrence_count,
            "distinct_suppliers": tag.distinct_suppliers,
        }
        for tag in db.scalars(select(ThemeTag).order_by(ThemeTag.occurrence_count.desc())).all()
    ]


def bug_suggestions(db: Session, *, window_days: int = 60, min_tickets: int = 3) -> dict:
    since = utcnow() - timedelta(days=window_days)
    tickets = db.scalars(
        select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.created_at >= since)
    ).all()
    groups: dict[tuple[str, str], list[Ticket]] = defaultdict(list)
    for ticket in tickets:
        if ticket.booking and ticket.intent:
            groups[(ticket.booking.supplier_name, ticket.intent)].append(ticket)

    suggestions = []
    for (supplier, intent), group in groups.items():
        if len(group) < min_tickets:
            continue
        group.sort(key=lambda t: t.created_at)
        related_links = len(db.scalars(
            select(TicketLink).where(TicketLink.source_ticket_id.in_([t.id for t in group]))
        ).all())
        evidence = [
            f"{t.ticket_number}: {t.title} ({t.created_at.strftime('%d %b %Y')})"
            for t in group[:5]
        ]
        suggestions.append({
            "supplier": supplier,
            "intent": intent,
            "intent_label": INTENT_LABELS.get(intent, intent),
            "frequency": len(group),
            "ticket_ids": [t.id for t in group],
            "ticket_numbers": [t.ticket_number for t in group],
            "evidence": evidence,
            "period": {
                "from": group[0].created_at.isoformat(),
                "to": group[-1].created_at.isoformat(),
            },
            "window_days": window_days,
            "confidence": "HIGH" if len(group) >= 4 else "MEDIUM",
            "suggested_action": (
                f"Engineering: audit the {supplier} {INTENT_LABELS.get(intent, intent).lower()} path. "
                f"{len(group)} tickets in the window share this supplier and intent — "
                "reproduce from the linked ticket ids, add a reconciliation assertion and an alert."
            ),
            "related_ticket_links": related_links,
        })

    suggestions.sort(key=lambda row: (-row["frequency"], row["supplier"]))
    return {
        "window_days": window_days,
        "min_tickets": min_tickets,
        "suggestions": suggestions,
        "method": "group tickets by (supplier, intent) and require frequency >= threshold",
        "note": (
            "These are local product-bug proposals stored in this database. "
            "No Jira or external tracker is connected or claimed."
        ),
    }


def create_product_bug(db: Session, *, supplier: str, intent: str | None, title: str,
                       suggested_action: str, related_ticket_ids: list[int] | None,
                       frequency: int, created_by: str) -> ProductBug:
    existing_codes = db.scalars(select(ProductBug.bug_code)).all()
    numbers = [int(code.split("-")[-1]) for code in existing_codes if code.split("-")[-1].isdigit()]
    next_number = max(numbers, default=100) + 1
    tickets = db.scalars(
        select(Ticket).where(Ticket.id.in_(related_ticket_ids or []))
    ).all() if related_ticket_ids else []
    evidence = "; ".join(f"{t.ticket_number}: {t.title}" for t in tickets) or "No tickets attached"
    bug = ProductBug(
        bug_code=f"PROD-BUG-{next_number}",
        title=title,
        supplier_name=supplier,
        intent=intent,
        frequency=frequency,
        status="PROPOSED",
        suggested_action=suggested_action,
        supporting_evidence=evidence,
        related_ticket_ids=related_ticket_ids or [],
        window_start=utcnow() - timedelta(days=60),
        window_end=utcnow(),
        created_at=utcnow(),
    )
    db.add(bug)
    db.commit()
    db.refresh(bug)
    return bug


def product_bug_payload(bug: ProductBug) -> dict:
    return {
        "bug_code": bug.bug_code,
        "title": bug.title,
        "supplier": bug.supplier_name,
        "intent": bug.intent,
        "intent_label": INTENT_LABELS.get(bug.intent or "", bug.intent),
        "frequency": bug.frequency,
        "status": bug.status,
        "suggested_action": bug.suggested_action,
        "supporting_evidence": bug.supporting_evidence,
        "related_ticket_ids": bug.related_ticket_ids or [],
        "window_start": bug.window_start.isoformat() if bug.window_start else None,
        "window_end": bug.window_end.isoformat() if bug.window_end else None,
        "created_at": bug.created_at.isoformat() if bug.created_at else None,
    }
