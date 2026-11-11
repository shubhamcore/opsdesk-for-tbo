"""Multi-agent case review — behaviour, grounding, RBAC and persistence."""
from __future__ import annotations

import pytest

from backend.models import AgentRun, Message


CASE_WITH_HISTORY = "TCK-101"


def _run(client, auth, ticket=CASE_WITH_HISTORY, role="lead"):
    return client.post(f"/api/agents/cases/{ticket}/run", json={"objective": "CASE_REVIEW"}, headers=auth(role))


def test_registry_lists_every_agent_with_tools(client, auth):
    response = client.get("/api/agents/registry", headers=auth("lead"))
    assert response.status_code == 200
    payload = response.json()

    assert payload["count"] == len(payload["agents"]) == 8
    names = {agent["name"] for agent in payload["agents"]}
    assert {
        "intake",
        "sla_risk",
        "routing_advisor",
        "escalation",
        "comms",
        "qa",
        "product_intel",
        "playbook",
    } <= names
    for agent in payload["agents"]:
        assert agent["tools"], f"{agent['name']} declares no tools"
        assert agent["deterministic"] is True
        assert agent["external_model"] is None
    assert payload["runtime"]["external_model"] is None


def test_swarm_run_produces_a_grounded_plan(client, auth, db):
    response = _run(client, auth)
    assert response.status_code == 200, response.text
    run = response.json()

    assert run["run_uuid"].startswith("AGT-")
    assert run["status"] == "COMPLETED"
    assert run["agent_count"] == 8
    assert len(run["agents"]) == 8
    assert 0.0 < run["overall_confidence"] <= 1.0
    assert run["plan"], "a breached high-priority case must produce at least one action"

    by_agent = {agent["agent"]: agent for agent in run["agents"]}
    # Grounding: the specialist must read the same numbers the API reports.
    ticket = client.get(f"/api/tickets/{CASE_WITH_HISTORY}", headers=auth("lead")).json()
    assert by_agent["sla_risk"]["evidence"]["state"] == ticket["sla"]["state"]
    assert by_agent["intake"]["evidence"]["intent"] == ticket["intent"]
    assert by_agent["sla_risk"]["evidence"]["governing_rule"] == ticket["sla"]["governing_rule"]

    # Every agent traces its tool use, and no tool call is silent about failures.
    for agent in run["agents"]:
        if agent["status"] in {"OK", "ATTENTION"}:
            assert agent["tool_calls"], f"{agent['agent']} produced findings without calling a tool"
        for call in agent["tool_calls"]:
            assert call["ok"] is True, f"{agent['agent']} -> {call['tool']} failed: {call['preview']}"

    stored = db.query(AgentRun).filter(AgentRun.run_uuid == run["run_uuid"]).one()
    assert len(stored.agents_json) == 8
    assert stored.plan_json == run["plan"]


def test_swarm_is_side_effect_free(client, auth, db):
    """Reviewing a case must not post messages, reassign or escalate anything."""
    from backend.models import Ticket

    before_messages = db.query(Message).filter(Message.ticket_id == 1).count()
    before_ticket = db.get(Ticket, 1)
    before_state = (before_ticket.assigned_user_id, before_ticket.status, before_ticket.escalated, before_ticket.queue)

    assert _run(client, auth).status_code == 200

    db.expire_all()
    assert db.query(Message).filter(Message.ticket_id == 1).count() == before_messages
    after = db.get(Ticket, 1)
    assert (after.assigned_user_id, after.status, after.escalated, after.queue) == before_state


def test_runs_are_listed_and_retrievable(client, auth):
    run_uuid = _run(client, auth, "TCK-104").json()["run_uuid"]

    listing = client.get("/api/agents/runs", params={"ticket_id": 2, "limit": 5}, headers=auth("lead"))
    assert listing.status_code == 200
    assert any(item["run_uuid"] == run_uuid for item in listing.json()["runs"])

    detail = client.get(f"/api/agents/runs/{run_uuid}", headers=auth("lead"))
    assert detail.status_code == 200
    assert detail.json()["agents"][0]["agent"] == "intake"

    assert client.get("/api/agents/runs/AGT-NOPE", headers=auth("lead")).status_code == 404


def test_requester_cannot_run_the_swarm(client, auth):
    response = _run(client, auth, "TCK-101", role="agency")
    assert response.status_code == 403
    assert "AGENCY_REQUESTER" in response.json()["detail"]


def test_resolved_case_is_rejected(client, auth, db):
    from backend.models import Ticket
    from backend.models.base import utcnow

    ticket = db.query(Ticket).filter(Ticket.status == "RESOLVED").first()
    if ticket is None:  # pragma: no cover - seed always has resolved tickets
        pytest.skip("no resolved ticket in the seed")
    response = _run(client, auth, ticket.ticket_number)
    assert response.status_code == 409


def test_telemetry_reflects_real_runs(client, auth):
    _run(client, auth, "TCK-109")
    telemetry = client.get("/api/agents/telemetry", headers=auth("lead")).json()

    assert telemetry["total_runs"] >= 1
    assert telemetry["tickets_reviewed"] >= 1
    assert telemetry["avg_run_ms"] > 0
    assert len(telemetry["agents"]) == 8
    for agent in telemetry["agents"]:
        assert agent["runs"] >= 1
        assert 0.0 <= agent["success_rate"] <= 1.0
        assert agent["tool_calls"] >= 0


def test_agent_failure_is_contained(monkeypatch, client, auth):
    """A raising specialist must degrade to an ERROR entry, not a 500."""
    from backend.agents import specialists

    original = specialists.QaAgent.run

    def boom(self, box):
        raise RuntimeError("synthetic tool outage")

    monkeypatch.setattr(specialists.QaAgent, "run", boom)
    response = _run(client, auth, "TCK-201")
    monkeypatch.setattr(specialists.QaAgent, "run", original)

    assert response.status_code == 200
    run = response.json()
    qa = next(agent for agent in run["agents"] if agent["agent"] == "qa")
    assert qa["status"] == "ERROR"
    assert "synthetic tool outage" in qa["summary"]
    assert run["status"] == "PARTIAL"
    assert run["agent_count"] == 8  # the other seven still ran
