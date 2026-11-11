"""Module tests — routing mathematics, eligibility filters and the API path."""
from __future__ import annotations

import pytest

from backend.services.routing import (
    MAX_SCORE,
    W_CAPACITY,
    W_REGION,
    W_SHIFT,
    W_SKILL,
    AgentState,
    check_eligibility,
    compute_route_score,
    is_within_shift,
)
from datetime import datetime, timezone


def _agent(**overrides) -> AgentState:
    base = dict(
        agent_id=1, full_name="Agent", email="a@x.com", region="APAC", skill_rank=5,
        max_capacity=8, active_load=1, is_online=True, timezone="UTC",
        shift_start="00:00", shift_end="23:59", shift_match=True,
    )
    base.update(overrides)
    return AgentState(**base)


# --------------------------------------------------- MANDATORY ROUTING TESTS


def test_qualified_region_matched_agent_scores_higher(agent_states):
    """(1) region match + shift beats an otherwise comparable mismatch."""
    region_ok = compute_route_score(agent_states[0], ticket_region="APAC", urgency_weight=1.0)
    region_bad = compute_route_score(agent_states[1], ticket_region="APAC", urgency_weight=1.0)

    assert region_ok.region_match == 1.0
    assert region_bad.region_match == 0.0
    assert region_ok.total_score > region_bad.total_score
    assert region_ok.total_score - region_bad.total_score == pytest.approx(W_REGION)


def test_offline_agent_is_excluded():
    """(2) offline agents never receive a ticket."""
    offline = _agent(is_online=False)
    verdict = check_eligibility(offline, ticket_region="APAC", priority="HIGH", sla_state="HEALTHY")
    assert verdict.eligible is False
    assert any("offline" in reason.lower() for reason in verdict.reasons)


def test_agent_at_max_capacity_is_excluded():
    """(3) load == capacity means no assignment."""
    full = _agent(active_load=8, max_capacity=8)
    verdict = check_eligibility(full, ticket_region="APAC", priority="HIGH", sla_state="HEALTHY")
    assert verdict.eligible is False
    assert any("capacity" in reason.lower() for reason in verdict.reasons)


def test_critical_tickets_require_senior_agents():
    """(4) CRITICAL/AT_RISK/BREACHED require SkillRank >= 4."""
    junior = _agent(skill_rank=3)
    verdict = check_eligibility(junior, ticket_region="APAC", priority="CRITICAL", sla_state="AT_RISK")
    assert verdict.eligible is False
    assert any("skillrank" in reason.lower() for reason in verdict.reasons)

    senior = _agent(skill_rank=4)
    assert check_eligibility(senior, ticket_region="APAC", priority="CRITICAL",
                             sla_state="AT_RISK").eligible is True


def test_all_scoring_components_are_non_negative():
    """(5) every component >= 0 for adversarial inputs."""
    cases = [
        _agent(active_load=0, max_capacity=0),
        _agent(active_load=99, max_capacity=8),
        _agent(skill_rank=0),
        _agent(region=None, skill_rank=1, max_capacity=1, active_load=1),
    ]
    for agent in cases:
        scored = compute_route_score(agent, ticket_region="APAC", urgency_weight=0.0)
        assert scored.region_match >= 0
        assert scored.shift_match >= 0
        assert scored.skill_component >= 0
        assert scored.capacity_component >= 0
        assert scored.total_score >= 0


def test_maximum_possible_score_is_one_hundred():
    """(6) perfect agent saturates exactly at 100."""
    perfect = _agent(region="APAC", skill_rank=5, active_load=0, max_capacity=8, shift_match=True)
    scored = compute_route_score(perfect, ticket_region="APAC", urgency_weight=1.0)
    assert scored.total_score == pytest.approx(MAX_SCORE)
    assert MAX_SCORE == 100.0
    assert W_REGION + W_SHIFT + W_SKILL + W_CAPACITY == 100.0


def test_zero_max_capacity_is_handled_safely():
    """(7) no ZeroDivisionError, capacity component is 0."""
    zero = _agent(max_capacity=0, active_load=0)
    scored = compute_route_score(zero, ticket_region="APAC", urgency_weight=1.0)
    assert scored.capacity_component == 0.0
    verdict = check_eligibility(zero, ticket_region="APAC", priority="LOW", sla_state="HEALTHY")
    assert verdict.eligible is False


# ------------------------------------------------------- additional behaviour


def test_shift_window_logic():
    # 2026-11-09 12:00 UTC
    noon = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    assert is_within_shift(noon, "UTC", "09:00", "18:00") is True
    assert is_within_shift(noon, "UTC", "18:00", "23:00") is False
    # overnight window 22:00 → 06:00
    assert is_within_shift(noon, "UTC", "22:00", "06:00") is False
    midnight = datetime(2026, 11, 9, 0, 30, tzinfo=timezone.utc)
    assert is_within_shift(midnight, "UTC", "22:00", "06:00") is True
    # zero-length window = not rostered
    assert is_within_shift(noon, "UTC", "00:00", "00:00") is False
    # invalid timezone must not raise
    assert is_within_shift(noon, "Not/AZone", "09:00", "18:00") is True


def test_capacity_component_scales_linearly():
    half = compute_route_score(_agent(active_load=4, max_capacity=8),
                               ticket_region="APAC", urgency_weight=1.0)
    empty = compute_route_score(_agent(active_load=0, max_capacity=8),
                                ticket_region="APAC", urgency_weight=1.0)
    assert half.capacity_component == pytest.approx(W_CAPACITY * 0.5)
    assert empty.capacity_component == pytest.approx(W_CAPACITY)


def test_skill_is_scaled_by_urgency():
    scored_low = compute_route_score(_agent(skill_rank=5), ticket_region="APAC", urgency_weight=0.5)
    assert scored_low.skill_component == pytest.approx(W_SKILL * 1.0 * 0.5)


def test_regional_eligibility_restriction():
    verdict = check_eligibility(
        _agent(region="EU"), ticket_region="EU", priority="LOW", sla_state="HEALTHY",
        allowed_regions={"APAC", "MEA"},
    )
    assert verdict.eligible is False


# ----------------------------------------------------------------- API level


def test_tie_break_prefers_lower_load_then_id(client, auth):
    """Equal scores resolve deterministically: lower load, then lower agent id."""
    response = client.get("/api/routing/board", headers=auth("lead"))
    assert response.status_code == 200
    agents = response.json()["agents"]
    assert agents, "seeded agents expected"
    # reference scores must be sorted descending as returned
    scores = [a["reference_score"] for a in agents]
    assert scores == sorted(scores, reverse=True)


def test_routing_assigns_highest_scoring_eligible_agent(client, auth):
    response = client.post("/api/tickets", headers=auth("agent"), json={
        "title": "Voucher pending for TBOH-554411",
        "description": "Marina Bay Sands has no confirmation for TBOH-554411; guest arrives tomorrow.",
        "tboh_id": "TBOH-554411",
        "priority": "HIGH",
    })
    assert response.status_code == 201, response.text
    ticket_id = response.json()["ticket_id"]

    routed = client.post(f"/api/routing/tickets/{ticket_id}/route",
                         headers=auth("agent"), json={"triggered_by": "MANUAL"})
    assert routed.status_code == 200
    decision = routed.json()["decision"]

    assert decision["candidates"], "expected eligible candidates"
    top = decision["candidates"][0]
    assert top["agent_id"] == decision["assigned_agent_id"]
    assert all(top["total_score"] >= c["total_score"] for c in decision["candidates"])
    assert decision["score"] <= 100.0

    for excluded in decision["excluded"]:
        assert excluded["reasons"], "every exclusion must be explained"


def test_ineligible_agent_never_receives_ticket_even_with_high_score(client, auth):
    """An offline high-skill agent must be excluded, not merely out-scored."""
    routed = client.post("/api/routing/tickets/1/route", headers=auth("lead"),
                         json={"triggered_by": "MANUAL"})
    assert routed.status_code == 200
    payload = routed.json()
    excluded_names = {e["full_name"] for e in payload["decision"]["excluded"]}
    assert "Priya Nair" in excluded_names  # seeded offline agent
    assert payload["assigned_to"]["name"] not in excluded_names
