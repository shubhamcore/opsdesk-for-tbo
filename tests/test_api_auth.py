"""System tests — authentication, RBAC, validation, error handling, health."""
from __future__ import annotations


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["classifier"]["mode"] in ("ML", "FALLBACK")
    assert body["counts"]["tickets"] > 0
    assert "SYNTHETIC" in body["data_notice"]


def test_login_success_and_failure(client):
    ok = client.post("/api/auth/login", json={
        "email": "nisha.verma@tbo.com", "password": "OpsDesk#2026"})
    assert ok.status_code == 200
    assert ok.json()["user"]["role"] == "OPS_LEAD"

    bad = client.post("/api/auth/login", json={
        "email": "nisha.verma@tbo.com", "password": "wrong"})
    assert bad.status_code == 401

    unknown = client.post("/api/auth/login", json={
        "email": "ghost@tbo.com", "password": "whatever"})
    assert unknown.status_code == 401


def test_protected_routes_require_token(client):
    assert client.get("/api/tickets").status_code == 401
    assert client.get("/api/analytics/queue").status_code == 401
    assert client.get("/api/routing/audits").status_code == 401


def test_invalid_token_rejected(client):
    response = client.get("/api/tickets", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_agency_scope_isolation(client, auth):
    agency_rows = client.get("/api/tickets", headers=auth("agency")).json()["tickets"]
    assert agency_rows
    assert {t["agency"] for t in agency_rows} == {"Wanderlust Travels"}

    lead_rows = client.get("/api/tickets", headers=auth("lead")).json()["tickets"]
    assert len(lead_rows) > len(agency_rows)


def test_agency_cannot_read_another_agencys_ticket(client, auth, db):
    from sqlalchemy import select

    from backend.models import Agency, Ticket

    other_agency = db.scalar(select(Agency).where(Agency.code == "AG-EWB"))
    foreign = db.scalar(select(Ticket).where(Ticket.agency_id == other_agency.id))
    response = client.get(f"/api/tickets/{foreign.id}", headers=auth("agency"))
    assert response.status_code == 403


def test_agency_cannot_read_internal_notes(client, auth, db):
    from sqlalchemy import select

    from backend.models import Ticket

    own = db.scalar(select(Ticket).where(Ticket.ticket_number == "TCK-101"))
    detail = client.get(f"/api/tickets/{own.id}", headers=auth("agency")).json()
    assert all(m["message_type"] == "PUBLIC_REPLY" for m in detail["messages"])
    assert detail["routing_audits"] == []


def test_input_validation_rejects_empty_ticket(client, auth):
    response = client.post("/api/tickets", headers=auth("agency"),
                           json={"title": "  ", "description": "   "})
    assert response.status_code == 422


def test_unknown_ticket_returns_404(client, auth):
    assert client.get("/api/tickets/999999", headers=auth("lead")).status_code == 404
    assert (client.post("/api/routing/tickets/999999/route", headers=auth("lead"),
                        json={}).status_code == 404)


def test_role_switch_issues_scoped_token(client, auth):
    response = client.post("/api/auth/switch-role", headers=auth("lead"),
                           json={"role": "AGENCY_REQUESTER", "agency_code": "AG-EWB"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == "AGENCY_REQUESTER"

    rows = client.get("/api/tickets",
                      headers={"Authorization": f"Bearer {body['access_token']}"}).json()["tickets"]
    assert {t["agency"] for t in rows} == {"EuroWings B2B"}


def test_queue_snapshot_consistency(client, auth):
    data = client.get("/api/analytics/queue", headers=auth("lead")).json()
    states = data["sla_states"]
    assert sum(states.values()) == data["totals"]["tickets"]
    assert 0 <= data["sla_compliance"]["compliance_pct"] <= 100
    assert len(data["agent_workload"]) >= 5
    assert data["weekly_volume"]


def test_database_persists_across_sessions(client, auth):
    """Data written through the API is visible to a brand-new session."""
    from backend.database import SessionLocal

    created = client.post("/api/tickets", headers=auth("agency"), json={
        "title": "Persistence check ticket",
        "description": "Verifying that the database retains records between sessions.",
        "tboh_id": "TBOH-778899",
        "priority": "LOW",
    })
    assert created.status_code == 201
    ticket_number = created.json()["ticket_number"]

    fresh = SessionLocal()
    try:
        from sqlalchemy import select

        from backend.models import Ticket

        found = fresh.scalar(select(Ticket).where(Ticket.ticket_number == ticket_number))
        assert found is not None
        assert found.title == "Persistence check ticket"
    finally:
        fresh.close()
