"""Backend smoke tests — the app boots, serves OpenAPI and the SPA shell."""
from __future__ import annotations


def test_app_boots_and_exposes_documented_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    for required in (
        "/api/health", "/api/auth/login", "/api/tickets", "/api/routing/board",
        "/api/escalations/queue", "/api/analytics/queue", "/api/exports/stream",
        "/api/simulation/status",
    ):
        assert required in paths, required


def test_root_serves_spa_or_explains_missing_build(client):
    response = client.get("/")
    # In test environments the frontend build may be absent; both responses are
    # honest outcomes — a served SPA, or a 503 that says how to build it.
    assert response.status_code in (200, 503)
    if response.status_code == 503:
        assert "npm run build" in response.json()["fix"]
