"""Module tests — escalation, ownership transfer and immutable audit."""
from __future__ import annotations

from sqlalchemy import select, update

from backend.models import ActivityTimeline, EscalationRecord, Ticket, User


def _find(client, auth, number: str) -> dict:
    rows = client.get("/api/tickets", headers=auth("agent"), params={"search": number}).json()
    return next(t for t in rows["tickets"] if t["ticket_number"] == number)


def test_escalation_transfers_real_ownership(client, auth, db):
    ticket = _find(client, auth, "TCK-402")
    previous_owner = ticket["assigned_user_id"]

    response = client.post(f"/api/escalations/tickets/{ticket['id']}/escalate",
                           headers=auth("agent"),
                           json={"reason": "Guest arriving imminently; supplier unresponsive."})
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["status"] == "ESCALATED"
    assert body["queue"] == "ESCALATION_MANAGER"
    assert body["assigned_to"]["role"] == "ESCALATION_MANAGER"
    assert body["previous"]["owner_id"] == previous_owner
    assert body["escalated_by"]

    # persisted ownership, not just a response field
    db.expire_all()
    stored = db.get(Ticket, ticket["id"])
    assert stored.status == "ESCALATED"
    assert stored.queue == "ESCALATION_MANAGER"
    assert stored.assigned_user_id == body["assigned_to"]["id"]
    assert stored.escalated is True
    assert stored.escalated_at is not None
    assert stored.escalated_by_id is not None


def test_escalation_requires_a_reason(client, auth):
    ticket = _find(client, auth, "TCK-205")
    response = client.post(f"/api/escalations/tickets/{ticket['id']}/escalate",
                           headers=auth("agent"), json={"reason": "no"})
    assert response.status_code == 422


def test_escalation_creates_immutable_audit_rows(client, auth, db):
    ticket = _find(client, auth, "TCK-301")
    client.post(f"/api/escalations/tickets/{ticket['id']}/escalate", headers=auth("agent"),
                json={"reason": "Supplier has not confirmed the group allocation."})
    db.expire_all()
    records = db.scalars(
        select(EscalationRecord).where(EscalationRecord.ticket_id == ticket["id"])
    ).all()
    assert records
    assert records[-1].previous_status and records[-1].previous_queue

    events = db.scalars(
        select(ActivityTimeline).where(
            ActivityTimeline.ticket_id == ticket["id"],
            ActivityTimeline.event_type == "ESCALATED",
        )
    ).all()
    assert events


def test_no_audit_mutation_api_exists(client, auth):
    """Audit surfaces are append-only: no PUT/PATCH/DELETE routes are exposed."""
    paths = client.get("/openapi.json").json()["paths"]
    for path, methods in paths.items():
        lowered = path.lower()
        if any(token in lowered for token in ("escalations", "routing/audits", "activity")):
            assert not ({"put", "patch", "delete"} & {m.lower() for m in methods}), path


def test_escalation_history_endpoint(client, auth):
    ticket = _find(client, auth, "TCK-403")   # pre-escalated in the seed
    response = client.get(f"/api/escalations/tickets/{ticket['id']}", headers=auth("agent"))
    assert response.status_code == 200
    history = response.json()["escalations"]
    assert history
    assert history[0]["assigned_em"]
    assert history[0]["reason"]


def test_em_queue_prioritises_travel_urgency(client, auth):
    response = client.get("/api/escalations/queue", headers=auth("em"))
    assert response.status_code == 200
    data = response.json()
    assert data["counts"]["at_risk"] + data["counts"]["breached"] > 0
    assert data["tickets"], "EM queue should not be empty"
    states = {t["sla"]["state"] for t in data["tickets"]}
    assert states <= {"AT_RISK", "BREACHED", "HEALTHY", "RESOLVED"}


def test_cannot_escalate_resolved_ticket(client, auth, db):
    db.expire_all()
    resolved = db.scalars(select(Ticket).where(Ticket.status == "RESOLVED")).first()
    assert resolved is not None, "seed should contain a resolved ticket"
    response = client.post(f"/api/escalations/tickets/{resolved.id}/escalate",
                           headers=auth("agent"), json={"reason": "Trying to escalate a closed case"})
    assert response.status_code == 409


def test_agency_cannot_escalate(client, auth):
    ticket = _find(client, auth, "TCK-101")
    response = client.post(f"/api/escalations/tickets/{ticket['id']}/escalate",
                           headers=auth("agency"), json={"reason": "Agency attempting escalation"})
    assert response.status_code == 403
