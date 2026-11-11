"""Module 2 — explainable routing.

score = 35*RegionMatch
      + 25*ShiftMatch
      + 25*(SkillRank/5)*UrgencyWeight
      + 15*(1 - ActiveLoad/MaxCapacity)

Hard eligibility filters run *before* scoring (offline, capacity, shift,
seniority for critical work, regional eligibility), so an ineligible agent can
never receive a ticket no matter how high their raw score is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

W_REGION = 35.0
W_SHIFT = 25.0
W_SKILL = 25.0
W_CAPACITY = 15.0
MAX_SCORE = W_REGION + W_SHIFT + W_SKILL + W_CAPACITY

SENIOR_SKILL_FLOOR = 4
SENIOR_REQUIRED_PRIORITIES = ("CRITICAL",)
SENIOR_REQUIRED_SLA_STATES = ("AT_RISK", "BREACHED")


@dataclass
class AgentState:
    agent_id: int
    full_name: str
    email: str
    region: str | None
    skill_rank: int
    max_capacity: int
    active_load: int
    is_online: bool
    timezone: str
    shift_start: str
    shift_end: str
    shift_match: bool = True


@dataclass
class ScoredAgent:
    agent_id: int
    full_name: str
    region: str | None
    skill_rank: int
    active_load: int
    max_capacity: int
    region_match: float
    shift_match: float
    skill_component: float
    capacity_component: float
    total_score: float

    def as_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "full_name": self.full_name,
            "region": self.region,
            "skill_rank": self.skill_rank,
            "active_load": self.active_load,
            "max_capacity": self.max_capacity,
            "region_match": round(self.region_match, 4),
            "shift_match": round(self.shift_match, 4),
            "skill_component": round(self.skill_component, 4),
            "capacity_component": round(self.capacity_component, 4),
            "total_score": round(self.total_score, 4),
        }


@dataclass
class EligibilityVerdict:
    eligible: bool
    reasons: list[str] = field(default_factory=list)


def _hhmm(value: str | None) -> tuple[int, int] | None:
    if not value or ":" not in value:
        return None
    try:
        hours, minutes = value.split(":")[:2]
        return int(hours), int(minutes)
    except ValueError:
        return None


def is_within_shift(now: datetime, tz_name: str | None, start: str, end: str) -> bool:
    """Is ``now`` inside the agent's local shift window?

    A zero-length window means "not rostered" (00:00-00:00). An unknown
    timezone falls back to UTC rather than raising.
    """
    begin, finish = _hhmm(start), _hhmm(end)
    if begin is None or finish is None:
        return True
    if begin == finish:
        return False
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        tz = timezone.utc
    local = now.astimezone(tz)
    current = local.hour * 60 + local.minute
    start_min = begin[0] * 60 + begin[1]
    end_min = finish[0] * 60 + finish[1]
    if start_min < end_min:
        return start_min <= current < end_min
    # overnight window, e.g. 22:00 → 06:00
    return current >= start_min or current < end_min


def check_eligibility(
    agent: AgentState,
    *,
    ticket_region: str,
    priority: str,
    sla_state: str,
    allowed_regions: set[str] | None = None,
) -> EligibilityVerdict:
    reasons: list[str] = []

    if not agent.is_online:
        reasons.append("Agent is offline")
    if agent.max_capacity <= 0:
        reasons.append("Agent has no capacity configured (max_capacity=0)")
    elif agent.active_load >= agent.max_capacity:
        reasons.append(f"Agent at capacity ({agent.active_load}/{agent.max_capacity})")
    if not agent.shift_match:
        reasons.append(f"Outside eligible shift ({agent.shift_start}-{agent.shift_end} {agent.timezone})")

    senior_required = (
        (priority or "").upper() in SENIOR_REQUIRED_PRIORITIES
        or (sla_state or "").upper() in SENIOR_REQUIRED_SLA_STATES
    )
    if senior_required and agent.skill_rank < SENIOR_SKILL_FLOOR:
        reasons.append(
            f"SkillRank {agent.skill_rank} < {SENIOR_SKILL_FLOOR} required for {priority}/{sla_state}"
        )

    if allowed_regions is not None and ticket_region not in allowed_regions:
        reasons.append(f"Region {ticket_region} is not an eligible routing region")

    return EligibilityVerdict(eligible=not reasons, reasons=reasons)


def compute_route_score(
    agent: AgentState,
    *,
    ticket_region: str,
    urgency_weight: float,
) -> ScoredAgent:
    region_match = 1.0 if agent.region and agent.region == ticket_region else 0.0
    shift_match = 1.0 if agent.shift_match else 0.0

    skill_ratio = max(0.0, min(1.0, (agent.skill_rank or 0) / 5.0))
    urgency = max(0.0, min(1.0, urgency_weight or 0.0))
    skill_component = W_SKILL * skill_ratio * urgency

    if (agent.max_capacity or 0) <= 0:
        capacity_component = 0.0
    else:
        free_ratio = 1.0 - (agent.active_load / agent.max_capacity)
        capacity_component = W_CAPACITY * max(0.0, min(1.0, free_ratio))

    total = (
        W_REGION * region_match
        + W_SHIFT * shift_match
        + skill_component
        + capacity_component
    )
    return ScoredAgent(
        agent_id=agent.agent_id,
        full_name=agent.full_name,
        region=agent.region,
        skill_rank=agent.skill_rank,
        active_load=agent.active_load,
        max_capacity=agent.max_capacity,
        region_match=region_match,
        shift_match=shift_match,
        skill_component=skill_component,
        capacity_component=capacity_component,
        total_score=round(min(total, MAX_SCORE), 4),
    )


def rank_candidates(scored: list[ScoredAgent]) -> list[ScoredAgent]:
    """Deterministic ordering: score desc → lowest load → lowest agent id."""
    return sorted(scored, key=lambda c: (-c.total_score, c.active_load, c.agent_id))
