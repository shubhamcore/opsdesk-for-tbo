"""Module tests — Module 3 supplier conversations and transfer safety."""
from __future__ import annotations

from sqlalchemy import select

from backend.models import SideConversation


def _tck_301_id(client, auth) -> int:
    rows = client.get("/api/tickets", headers=auth("agent"), params={"search": "TCK-301"}).json()
    return next(t["id"] for t in rows["tickets"] if t["ticket_number"] == "TCK-301")


def test_recipient_validation_rejects_bad_emails(client, auth):
    ticket_id = _tck_301_id(client, auth)
    response = client.post(f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent"), json={
        "channel_type": "SUPPLIER",
        "subject": "Bad recipient",
        "counterparty_name": "Hilton",
        "recipients": ["not-an-email"],
    })
    assert response.status_code in (400, 422)


def test_seeded_supplier_conversation_has_explicit_recipients(client, auth, db):
    ticket_id = _tck_301_id(client, auth)
    conversations = client.get(
        f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent")
    ).json()["conversations"]
    assert conversations
    supplier = next(c for c in conversations if c["channel_type"] == "SUPPLIER")
    assert supplier["explicit_recipients"] == ["groups@hilton-paris.com"]
    assert supplier["counterparty_name"] == "Hilton Paris Opera"
    assert supplier["messages"], "seeded history expected"


def test_recipients_survive_ticket_transfer(client, auth, db):
    """The core Module 3 invariant."""
    ticket_id = _tck_301_id(client, auth)
    before = client.get(
        f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent")
    ).json()["conversations"]
    before_map = {c["id"]: list(c["explicit_recipients"]) for c in before}

    transferred = client.post(f"/api/tickets/{ticket_id}/transfer", headers=auth("agent"), json={
        "to_queue": "EU-SENIOR-OPS",
        "note": "pytest transfer check",
    })
    assert transferred.status_code == 200
    body = transferred.json()
    assert body["recipients_unchanged"] is True
    assert "Original recipients unchanged" in body["message"]
    assert body["preserved_side_conversations"] >= 1

    after = client.get(
        f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent")
    ).json()["conversations"]
    after_map = {c["id"]: list(c["explicit_recipients"]) for c in after}
    assert before_map == after_map

    db.expire_all()
    stored = db.scalars(
        select(SideConversation).where(SideConversation.ticket_id == ticket_id)
    ).all()
    assert all(c.explicit_recipients for c in stored)


def test_transfer_does_not_inherit_queue_recipients(client, auth):
    """A transfer must not append the new group's addresses to the supplier thread."""
    ticket_id = _tck_301_id(client, auth)
    client.post(f"/api/tickets/{ticket_id}/transfer", headers=auth("agent"),
                json={"to_queue": "EU-TRIAGE", "note": "back to triage"})
    conversations = client.get(
        f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent")
    ).json()["conversations"]
    for conversation in conversations:
        assert conversation["explicit_recipients"] == ["groups@hilton-paris.com"]
        assert not any("triage" in r.lower() or "senior" in r.lower()
                       for r in conversation["explicit_recipients"])


def test_side_message_is_stored_per_recipient(client, auth):
    ticket_id = _tck_301_id(client, auth)
    created = client.post(f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent"), json={
        "channel_type": "SUPPLIER",
        "subject": "Multi recipient thread",
        "counterparty_name": "Hilton Paris Opera",
        "recipients": ["groups@hilton-paris.com", "reservations@hilton-paris.com"],
    })
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    sent = client.post(f"/api/side-conversations/{conversation_id}/messages",
                       headers=auth("agent"), json={"content": "Please confirm the group block."})
    assert sent.status_code == 201
    assert sent.json()["messages_created"] == 2
    assert sent.json()["recipients"] == ["groups@hilton-paris.com",
                                         "reservations@hilton-paris.com"]

    conversations = client.get(
        f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agent")
    ).json()["conversations"]
    target = next(c for c in conversations if c["id"] == conversation_id)
    assert len(target["messages"]) == 2
    assert {m["recipient_email"] for m in target["messages"]} == {
        "groups@hilton-paris.com", "reservations@hilton-paris.com"
    }


def test_agency_requester_cannot_create_supplier_conversation(client, auth):
    ticket_id = _tck_301_id(client, auth)
    response = client.post(f"/api/tickets/{ticket_id}/side-conversations", headers=auth("agency"), json={
        "channel_type": "SUPPLIER", "subject": "Nope", "counterparty_name": "Hilton",
        "recipients": ["groups@hilton-paris.com"],
    })
    assert response.status_code == 403


def test_transfer_records_history_event(client, auth):
    ticket_id = _tck_301_id(client, auth)
    detail = client.get(f"/api/tickets/{ticket_id}", headers=auth("agent")).json()
    events = [e for e in detail["activity_timeline"] if e["event_type"] == "TRANSFERRED"]
    assert events
    assert events[0]["metadata"]["preserved_conversations"]
