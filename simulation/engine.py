"""Journey engine — drives the *real* HTTP API, records expected vs actual.

Every step is executed against the running FastAPI service, so a green journey
is evidence that the API (not just an internal function) works.

    python -m simulation.run_all --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

DEMO_PASSWORD = "OpsDesk#2026"
CREDENTIALS = {
    "agency_wanderlust": ("maya.requester@wanderlust-travels.com", DEMO_PASSWORD),
    "agency_apex": ("kai.requester@apexglobalholidays.com", DEMO_PASSWORD),
    "ops_agent": ("ananya.sharma@tbo.com", DEMO_PASSWORD),
    "ops_agent_eu": ("sofia.lindqvist@tbo.com", DEMO_PASSWORD),
    "escalation_manager": ("elena.rossi@tbo.com", DEMO_PASSWORD),
    "ops_lead": ("nisha.verma@tbo.com", DEMO_PASSWORD),
}


@dataclass
class Step:
    name: str
    expected: str
    actual: str = ""
    passed: bool = False
    evidence: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
            "evidence": self.evidence,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
        }


class JourneyRunner:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self.token: str | None = None
        self.steps: list[Step] = []

    # ------------------------------------------------------------------ auth
    def login(self, key: str) -> None:
        email, password = CREDENTIALS[key]
        response = self.client.post("/api/auth/login", json={"email": email, "password": password})
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def switch_role(self, role: str, agency_code: str | None = None) -> dict:
        response = self.client.post(
            "/api/auth/switch-role", json={"role": role, "agency_code": agency_code}, headers=self.headers()
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        return data["user"]

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.client.get(path, headers=self.headers(), **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.client.post(path, headers=self.headers(), **kwargs)

    # ----------------------------------------------------------------- steps
    def step(self, name: str, expected: str, fn) -> Step:
        entry = Step(name=name, expected=expected)
        started = time.perf_counter()
        try:
            result = fn()
            if isinstance(result, tuple):
                actual, passed, evidence = result
            else:
                actual, passed, evidence = result, True, {}
            entry.actual = str(actual)
            entry.passed = bool(passed)
            entry.evidence = evidence or {}
        except Exception as exc:  # noqa: BLE001 - a failed step must not kill the journey
            entry.actual = f"ERROR: {type(exc).__name__}: {exc}"
            entry.passed = False
            entry.error = entry.actual
        entry.duration_ms = (time.perf_counter() - started) * 1000
        self.steps.append(entry)
        return entry

    def result(self, key: str, title: str, started_at: datetime) -> dict:
        return {
            "journey": key,
            "title": title,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "steps": [s.as_dict() for s in self.steps],
            "steps_total": len(self.steps),
            "steps_passed": sum(1 for s in self.steps if s.passed),
            "passed": all(s.passed for s in self.steps) and bool(self.steps),
        }

    def close(self) -> None:
        self.client.close()


# --------------------------------------------------------------------- helpers


def find_ticket(rows: list[dict], number: str) -> dict | None:
    return next((r for r in rows if r.get("ticket_number") == number), None)


def count_export_rows(response_stream) -> tuple[int, int, int]:
    """Count lines while streaming; returns (data_rows, bytes, columns)."""
    rows = 0
    total_bytes = 0
    columns = 0
    header_seen = False
    buffer = ""
    for chunk in response_stream.iter_text():
        total_bytes += len(chunk.encode())
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            if not line.strip():
                continue
            if not header_seen:
                columns = len(line.split(","))
                header_seen = True
                continue
            rows += 1
    return rows, total_bytes, columns


def pretty(result: dict) -> str:
    lines = [f"JOURNEY {result['journey']} — {result['title']}"]
    for step in result["steps"]:
        mark = "PASS" if step["passed"] else "FAIL"
        lines.append(f"  [{mark}] {step['name']}")
        lines.append(f"         expected: {step['expected']}")
        lines.append(f"         actual  : {step['actual']}")
    lines.append(
        f"  RESULT: {result['steps_passed']}/{result['steps_total']} steps passed "
        f"→ {'PASS' if result['passed'] else 'FAIL'}"
    )
    return "\n".join(lines)


def dump(result: dict, path) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(result, indent=2, default=str))
