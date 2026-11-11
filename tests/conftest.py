"""Pytest fixtures. A throwaway SQLite database is used for every test session."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Must be set BEFORE backend modules import settings.
_TMP = tempfile.mkdtemp(prefix="opsdesk-test-")
os.environ["OPSDESK_DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"
os.environ["OPSDESK_EXPORT_DIR"] = str(Path(_TMP) / "exports")
os.environ["OPSDESK_SECRET_KEY"] = "test-secret-not-for-production"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.database import SessionLocal, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import Agency, Booking, Ticket, User  # noqa: E402

DEMO_PASSWORD = "OpsDesk#2026"


@pytest.fixture(scope="session")
def seeded_db():
    init_db()
    from database.seed_data.seed import seed_database

    summary = seed_database(reset=True)
    return summary


@pytest.fixture(scope="session")
def client(seeded_db):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(seeded_db):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def tokens(client):
    """Bearer tokens for each demo role."""
    credentials = {
        "agency": "maya.requester@wanderlust-travels.com",
        "agent": "ananya.sharma@tbo.com",
        "em": "elena.rossi@tbo.com",
        "lead": "nisha.verma@tbo.com",
    }
    out = {}
    for role, email in credentials.items():
        response = client.post("/api/auth/login", json={"email": email, "password": DEMO_PASSWORD})
        assert response.status_code == 200, response.text
        out[role] = response.json()["access_token"]
    return out


@pytest.fixture()
def auth(tokens):
    def _headers(role: str) -> dict:
        return {"Authorization": f"Bearer {tokens[role]}"}

    return _headers


@pytest.fixture()
def agent_states(db):
    """Deterministic agent snapshots for pure routing maths."""
    from backend.services.routing import AgentState

    return [
        AgentState(
            agent_id=1, full_name="Region Match Agent", email="a@x.com", region="APAC",
            skill_rank=5, max_capacity=8, active_load=1, is_online=True,
            timezone="UTC", shift_start="00:00", shift_end="23:59", shift_match=True,
        ),
        AgentState(
            agent_id=2, full_name="Wrong Region Agent", email="b@x.com", region="EU",
            skill_rank=5, max_capacity=8, active_load=1, is_online=True,
            timezone="UTC", shift_start="00:00", shift_end="23:59", shift_match=True,
        ),
    ]
