"""Case swarm orchestrator.

Runs the specialist agents over a single ticket, contains their failures, folds
their recommendations into one prioritised plan and persists the whole trace.

The orchestrator is deliberately synchronous and side-effect free apart from the
single ``agent_runs`` insert: a case review must be reproducible from the stored
trace, and concurrent mutation would make that impossible.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from backend.agents import specialists
from backend.agents.runtime import AgentResult, ToolBox, new_run_uuid, summarise
from backend.models import AgentRun, Ticket, User
from backend.models.base import utcnow


def registry_payload() -> dict:
    agents = [agent.spec() for agent in specialists.ALL_AGENTS]
    return {
        "agents": agents,
        "count": len(agents),
        "runtime": {
            "execution": "in-process, synchronous, per-case",
            "external_model": None,
            "note": (
                "Agents are deterministic specialists: each one is restricted to an explicit tool "
                "allow-list over the same services the REST API uses. No external LLM endpoint is "
                "contacted in this build."
            ),
        },
    }


def run_case_swarm(
    db: Session,
    ticket: Ticket,
    *,
    actor: User | None = None,
    objective: str = "CASE_REVIEW",
    persist: bool = True,
) -> dict:
    run_uuid = new_run_uuid()
    blackboard: dict = {"ticket_id": ticket.id, "ticket_number": ticket.ticket_number}
    results: list[AgentResult] = []
    started = time.perf_counter()

    for agent in specialists.ALL_AGENTS:
        box = ToolBox(db=db, ticket=ticket, blackboard=blackboard)
        agent_started = time.perf_counter()
        try:
            result = agent.run(box)
        except Exception as exc:  # one broken agent must not sink the review
            result = AgentResult(
                agent=agent.name,
                title=agent.title,
                status="ERROR",
                summary=f"{type(exc).__name__}: {exc}",
                findings=[],
                recommendations=[],
                confidence=0.0,
                evidence={"error": str(exc)},
                tool_calls=list(box.calls),
                duration_ms=(time.perf_counter() - agent_started) * 1000,
            )
        if not result.tool_calls:
            result.tool_calls = list(box.calls)
        if not result.duration_ms:
            result.duration_ms = (time.perf_counter() - agent_started) * 1000
        results.append(result)

    duration_ms = (time.perf_counter() - started) * 1000
    summary = summarise(results)
    errors = summary["status_counts"]["ERROR"]
    status = "FAILED" if errors == len(results) else ("PARTIAL" if errors else "COMPLETED")

    if persist:
        record = AgentRun(
            run_uuid=run_uuid,
            ticket_id=ticket.id,
            objective=objective,
            status=status,
            agent_count=len(results),
            overall_confidence=summary["overall_confidence"],
            summary=summary["headline"],
            agents_json=[r.as_dict() for r in results],
            plan_json=summary["plan"],
            duration_ms=duration_ms,
            created_by_id=actor.id if actor else None,
            created_at=utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    return payload_from_results(
        run_uuid=run_uuid,
        ticket=ticket,
        results=results,
        summary=summary,
        duration_ms=duration_ms,
        status=status,
        objective=objective,
        created_at=utcnow(),
        actor=actor,
    )


def payload_from_results(
    *,
    run_uuid: str,
    ticket: Ticket,
    results: list[AgentResult],
    summary: dict,
    duration_ms: float,
    status: str,
    objective: str,
    created_at,
    actor: User | None,
) -> dict:
    return {
        "run_uuid": run_uuid,
        "ticket_id": ticket.id,
        "ticket_number": ticket.ticket_number,
        "objective": objective,
        "status": status,
        "agent_count": len(results),
        "overall_confidence": summary["overall_confidence"],
        "headline": summary["headline"],
        "plan": summary["plan"],
        "needs_human": summary["needs_human"],
        "status_counts": summary["status_counts"],
        "agents": [r.as_dict() for r in results],
        "duration_ms": round(duration_ms, 2),
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        "created_by": actor.full_name if actor else "system",
    }


def record_payload(record: AgentRun, ticket: Ticket | None = None) -> dict:
    return {
        "run_uuid": record.run_uuid,
        "ticket_id": record.ticket_id,
        "ticket_number": ticket.ticket_number if ticket else None,
        "objective": record.objective,
        "status": record.status,
        "agent_count": record.agent_count,
        "overall_confidence": record.overall_confidence,
        "headline": record.summary,
        "plan": record.plan_json or [],
        "agents": record.agents_json or [],
        "duration_ms": round(record.duration_ms, 2),
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def telemetry(db: Session) -> dict:
    """Aggregate real run history — no synthetic numbers."""
    from sqlalchemy import func, select

    runs = db.scalars(select(AgentRun)).all()
    per_agent: dict[str, dict] = {}
    for run in runs:
        for agent in run.agents_json or []:
            stats = per_agent.setdefault(
                agent["agent"],
                {
                    "agent": agent["agent"],
                    "title": agent["title"],
                    "runs": 0,
                    "ok": 0,
                    "attention": 0,
                    "skipped": 0,
                    "error": 0,
                    "duration_ms_total": 0.0,
                    "tool_calls": 0,
                    "tool_failures": 0,
                },
            )
            stats["runs"] += 1
            key = {"OK": "ok", "ATTENTION": "attention", "SKIPPED": "skipped", "ERROR": "error"}[
                agent["status"]
            ]
            stats[key] += 1
            stats["duration_ms_total"] += agent.get("duration_ms", 0.0)
            stats["tool_calls"] += len(agent.get("tool_calls", []))
            stats["tool_failures"] += sum(1 for c in agent.get("tool_calls", []) if not c.get("ok", True))

    agents = []
    for stats in sorted(per_agent.values(), key=lambda s: s["agent"]):
        runs_count = max(stats["runs"], 1)
        agents.append(
            {
                **{k: v for k, v in stats.items() if k != "duration_ms_total"},
                "avg_duration_ms": round(stats["duration_ms_total"] / runs_count, 2),
                "success_rate": round(stats["ok"] / runs_count, 4),
            }
        )

    total_runs = len(runs)
    return {
        "total_runs": total_runs,
        "tickets_reviewed": len({r.ticket_id for r in runs}),
        "avg_run_ms": round(sum(r.duration_ms for r in runs) / total_runs, 2) if total_runs else 0.0,
        "plan_actions": sum(len(r.plan_json or []) for r in runs),
        "agents": agents,
        "generated_at": utcnow().isoformat(),
        "source": "agent_runs table",
    }
