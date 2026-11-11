"""Production-surface behaviour: probes, metrics, tracing, headers, rate limiting."""
from __future__ import annotations

import re

import pytest

from backend.config import settings


def test_readiness_probe(client):
    response = client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["classifier"] in {"ML", "FALLBACK"}
    assert body["problems"] == []


def test_metrics_are_prometheus_text_and_measured(client, auth):
    client.get("/api/health")
    client.get("/api/tickets", headers=auth("lead"))
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert "# TYPE opsdesk_http_requests_total counter" in text
    assert 'opsdesk_http_requests_total{route="/api/health"' in text
    assert "opsdesk_http_request_duration_ms" in text
    assert re.search(r"opsdesk_tickets_total \d+", text)
    # the gauge must match the database, not a constant
    tickets = client.get("/api/tickets", headers=auth("lead")).json()["count"]
    assert f"opsdesk_tickets_total {float(tickets)}" in text


def test_request_tracing_headers(client):
    response = client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["X-Request-ID"] == "trace-abc-123"
    assert float(response.headers["X-Response-Time-Ms"]) >= 0

    generated = client.get("/api/health")
    assert len(generated.headers["X-Request-ID"]) == 16


def test_security_headers_are_present(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "same-origin"
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    # No frame-ancestors directive: `*` would reject opaque ancestors and break
    # embedding in preview panes; framing policy is therefore delegated to the host.
    assert "frame-ancestors" not in csp


@pytest.fixture()
def tight_rate_limit():
    from backend.observability import _AUTH_WINDOW

    original = settings.rate_limit_per_minute
    settings.rate_limit_per_minute = 2
    _AUTH_WINDOW.clear()  # earlier fixtures authenticated; start from a clean window
    try:
        yield 2
    finally:
        settings.rate_limit_per_minute = original
        from backend.observability import _AUTH_WINDOW

        _AUTH_WINDOW.clear()


def test_login_rate_limit_returns_429_with_retry_after(client, tight_rate_limit):
    payload = {"email": "nisha.verma@tbo.com", "password": "wrong-password"}
    first = client.post("/api/auth/login", json=payload)
    second = client.post("/api/auth/login", json=payload)
    third = client.post("/api/auth/login", json=payload)

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert "Retry-After" in third.headers
    assert int(third.headers["Retry-After"]) >= 1
    assert "Too many sign-in attempts" in third.json()["detail"]


def test_rate_limit_counts_only_auth_paths(client, tight_rate_limit):
    # two auth calls (limit), then ordinary API traffic must still pass
    client.post("/api/auth/login", json={"email": "x@y.z", "password": "nope"})
    client.post("/api/auth/login", json={"email": "x@y.z", "password": "nope"})
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/auth/login", json={"email": "a@b.c", "password": "nope"}).status_code == 429


def test_hot_indexes_exist(db):
    from sqlalchemy import text

    names = {row[0] for row in db.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))}
    for expected in (
        "ix_tickets_status_queue",
        "ix_tickets_assigned",
        "ix_agent_runs_ticket",
        "ix_messages_ticket_created",
    ):
        assert expected in names, f"missing index {expected}"
