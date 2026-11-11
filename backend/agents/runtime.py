"""Agent runtime — tool allow-lists, traced execution and persistence.

Design rules that keep this honest:

* **Agents cannot invent facts.** Every agent may only read through the tool
  wrappers in :mod:`backend.agents.tools`, and every one of those wrappers calls
  the same deterministic service the REST API uses (classifier, SLA engine,
  routing maths, case-graph linker). There is no free-text generation step that
  could hallucinate a booking, an amount or a supplier.
* **Every step is traced.** A run records each tool call (name, arguments,
  duration, output preview) plus the per-agent findings, so a reviewer can
  reconstruct exactly why an action was proposed.
* **Failures are contained.** A raising agent is recorded as ``ERROR`` for that
  agent only; the rest of the swarm still completes and the run is marked
  ``PARTIAL``. A single bad tool never takes down a case review.
* **No external LLM is called.** ``OPSDESK_LLM_ENDPOINT`` is documented in
  ``.env.example`` as the extension point for a future hosted model, but nothing
  in this build contacts it — the platform does not claim a capability it lacks.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.models import Ticket


# --------------------------------------------------------------------- results

@dataclass(slots=True)
class ToolCall:
    tool: str
    args: dict[str, Any]
    ok: bool
    duration_ms: float
    preview: str

    def as_dict(self) -> dict:
        return {
            "tool": self.tool,
            "args": self.args,
            "ok": self.ok,
            "duration_ms": round(self.duration_ms, 2),
            "preview": self.preview,
        }


@dataclass(slots=True)
class AgentResult:
    agent: str
    title: str
    status: str                     # OK | ATTENTION | SKIPPED | ERROR
    summary: str
    findings: list[str] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    evidence: dict = field(default_factory=dict)
    tool_calls: list[ToolCall] = field(default_factory=list)
    duration_ms: float = 0.0

    def as_dict(self) -> dict:
        return {
            "agent": self.agent,
            "title": self.title,
            "status": self.status,
            "summary": self.summary,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence,
            "tool_calls": [c.as_dict() for c in self.tool_calls],
            "duration_ms": round(self.duration_ms, 2),
        }


# ----------------------------------------------------------------------- tools

ToolFunc = Callable[..., Any]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    func: ToolFunc

    def as_dict(self) -> dict:
        return {"name": self.name, "description": self.description}


class ToolBox:
    """Per-run context handed to an agent: database, ticket and a call recorder."""

    def __init__(self, *, db: Session, ticket: Ticket, blackboard: dict[str, Any]) -> None:
        self.db = db
        self.ticket = ticket
        self.blackboard = blackboard
        self.calls: list[ToolCall] = []

    def call(self, tool: ToolSpec, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            output = tool.func(self.db, self.ticket, **kwargs)
            ok = True
        except Exception as exc:  # a tool failure is data, not a crash
            output = {"error": f"{type(exc).__name__}: {exc}"}
            ok = False
        duration = (time.perf_counter() - started) * 1000
        self.calls.append(
            ToolCall(
                tool=tool.name,
                args={k: v for k, v in kwargs.items() if v is not None},
                ok=ok,
                duration_ms=duration,
                preview=_preview(output),
            )
        )
        if not ok:
            raise ToolFailure(tool.name, output["error"])
        return output


class ToolFailure(RuntimeError):
    def __init__(self, tool: str, detail: str) -> None:
        super().__init__(f"tool {tool} failed: {detail}")
        self.tool = tool
        self.detail = detail


def _preview(value: Any, limit: int = 240) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------- agents

class Agent:
    """Base class: declare identity plus the exact tools you are allowed to use."""

    name: str = "agent"
    title: str = "Agent"
    description: str = ""
    tool_names: tuple[str, ...] = ()

    def tools(self) -> list[ToolSpec]:
        from backend.agents import tools as tool_module

        registry = tool_module.REGISTRY
        missing = [n for n in self.tool_names if n not in registry]
        if missing:  # fail loudly at import time, not mid-run
            raise KeyError(f"{self.name} references unknown tools: {missing}")
        return [registry[n] for n in self.tool_names]

    # -------------------------------------------------------------- contract
    def run(self, box: ToolBox) -> AgentResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def spec(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "tools": [t.as_dict() for t in self.tools()],
            "external_model": None,
            "deterministic": True,
        }


# ------------------------------------------------------------- run persistence

def new_run_uuid() -> str:
    return f"AGT-{uuid.uuid4().hex[:12].upper()}"


def summarise(results: list[AgentResult]) -> dict:
    """Build the human-facing plan from the individual agent recommendations."""
    order = {"P0": 0, "P1": 1, "P2": 2}
    plan: list[dict] = []
    seen: set[str] = set()
    for result in results:
        for rec in result.recommendations:
            key = rec.get("action", "")
            if key in seen:
                continue
            seen.add(key)
            plan.append({**rec, "source_agent": result.agent})
    plan.sort(key=lambda r: (order.get(r.get("priority", "P2"), 9), r.get("action", "")))

    active = [r for r in results if r.status not in {"SKIPPED"}]
    confidence = round(
        sum(r.confidence for r in active) / len(active), 4
    ) if active else 0.0
    attention = [r.agent for r in results if r.status in {"ATTENTION", "ERROR"}]
    counts = {s: sum(1 for r in results if r.status == s) for s in ("OK", "ATTENTION", "SKIPPED", "ERROR")}
    return {
        "plan": plan[:8],
        "overall_confidence": confidence,
        "needs_human": attention,
        "status_counts": counts,
        "headline": (
            f"{len(plan)} action(s) proposed; {counts['ATTENTION']} agent(s) flagged a risk; "
            f"{counts['SKIPPED']} not applicable"
        ),
    }
