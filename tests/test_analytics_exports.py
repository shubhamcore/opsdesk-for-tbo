"""Module tests — product intelligence, governance and streaming exports."""
from __future__ import annotations

import csv
import io
import json
import time

import pytest


# --------------------------------------------------------------- intelligence


def test_product_intelligence_uses_real_ticket_data(client, auth):
    response = client.get("/api/analytics/product-intelligence", headers=auth("lead"))
    assert response.status_code == 200
    data = response.json()

    assert data["tickets_in_window"] > 0
    assert data["intent_distribution"]
    total_from_distribution = sum(i["count"] for i in data["intent_distribution"])
    assert total_from_distribution <= data["tickets_in_window"]
    assert data["inventory_sync"]["ticket_count"] >= 11     # Journey E seed volume
    assert data["supplier_complaints"]
    assert data["resolution_time_distribution"]


def test_theme_aggregation_refresh(client, auth):
    response = client.post("/api/analytics/themes/refresh", headers=auth("lead"))
    assert response.status_code == 200
    themes = response.json()["themes"]
    assert themes
    assert all(t["occurrences"] > 0 for t in themes)
    names = {t["name"] for t in themes}
    assert "INVENTORY_RATE_SYNC_BUG" in names


def test_bug_suggestion_requires_three_tickets(client, auth):
    response = client.get("/api/analytics/bug-suggestions", headers=auth("lead"),
                          params={"window_days": 60, "min_tickets": 3})
    assert response.status_code == 200
    suggestions = response.json()["suggestions"]
    assert suggestions
    assert all(s["frequency"] >= 3 for s in suggestions)
    inventory = [s for s in suggestions if s["intent"] == "INVENTORY_RATE_SYNC_BUG"]
    assert inventory, "inventory sync pattern expected from the seed"
    assert inventory[0]["evidence"]
    assert inventory[0]["ticket_numbers"]

    # raising the threshold must reduce or keep the count
    strict = client.get("/api/analytics/bug-suggestions", headers=auth("lead"),
                        params={"min_tickets": 10}).json()["suggestions"]
    assert len(strict) <= len(suggestions)


def test_create_product_bug_record(client, auth):
    response = client.post("/api/analytics/product-bugs", headers=auth("lead"), json={
        "supplier": "Hotelbeds",
        "intent": "INVENTORY_RATE_SYNC_BUG",
        "title": "Hotelbeds rate cache mismatch",
        "suggested_action": "Audit cache invalidation between search and book.",
        "related_ticket_ids": [1, 2, 3],
        "frequency": 3,
    })
    assert response.status_code == 201, response.text
    bug = response.json()
    assert bug["bug_code"].startswith("PROD-BUG-")
    assert bug["status"] == "PROPOSED"

    listed = client.get("/api/analytics/product-bugs", headers=auth("lead")).json()["bugs"]
    assert any(b["bug_code"] == bug["bug_code"] for b in listed)


def test_agent_cannot_create_product_bug(client, auth):
    response = client.post("/api/analytics/product-bugs", headers=auth("agent"), json={
        "supplier": "Hotelbeds", "intent": "INVENTORY_RATE_SYNC_BUG",
        "title": "Nope", "suggested_action": "Not allowed for agents.",
    })
    assert response.status_code == 403


# ------------------------------------------------------------------- exports


def _stream(client, auth, payload, role="lead"):
    response = client.post("/api/exports/stream", headers=auth(role), json=payload)
    return response


def test_small_csv_export_is_valid_and_downloadable(client, auth):
    response = _stream(client, auth, {"file_format": "CSV", "source": "SYNTHETIC_BENCHMARK",
                                      "total_rows": 250})
    assert response.status_code == 200
    job_uuid = response.headers["X-Export-Job-Uuid"]

    text = response.text
    reader = list(csv.reader(io.StringIO(text)))
    assert len(reader) == 251  # header + 250 rows
    assert reader[0][0] == "row_id" and reader[0][1] == "ticket_number"
    assert len(reader[0]) == 25

    validation = client.get(f"/api/exports/{job_uuid}/validate", headers=auth("lead")).json()
    assert validation["result"] == "PASS"
    assert validation["actual_rows_in_file"] == 250
    assert validation["row_count_matches"] is True

    download = client.get(f"/api/exports/{job_uuid}/download", headers=auth("lead"))
    assert download.status_code == 200
    assert len(download.content) == validation["file_size_bytes"]


def test_jsonl_export_is_valid(client, auth):
    response = _stream(client, auth, {"file_format": "JSONL", "source": "SYNTHETIC_BENCHMARK",
                                      "total_rows": 100})
    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert len(lines) == 100
    first = json.loads(lines[0])
    assert "ticket_number" in first and "sla_state" in first
    assert json.loads(lines[-1])["row_id"] == 100


def test_db_backed_export_uses_live_records(client, auth):
    response = _stream(client, auth, {"file_format": "CSV", "source": "DB", "total_rows": 1})
    assert response.status_code == 200
    reader = list(csv.reader(io.StringIO(response.text)))
    assert len(reader) >= 2
    assert any(row[1].startswith("TCK-") for row in reader[1:])


def test_export_filters_are_applied(client, auth):
    response = _stream(client, auth, {"file_format": "CSV", "source": "DB",
                                      "region": "APAC", "total_rows": 1})
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows, "APAC tickets expected in the seed"
    assert {r["region"] for r in rows} == {"APAC"}


def test_export_access_is_restricted(client, auth):
    for role in ("agency", "agent"):
        response = _stream(client, auth, {"total_rows": 10}, role=role)
        assert response.status_code == 403, f"{role} must not export bulk data"


def test_export_row_limit_enforced(client, auth):
    response = _stream(client, auth, {"total_rows": 999999})
    assert response.status_code == 422


def test_fifty_thousand_row_export_benchmark(client, auth):
    """The headline Journey E benchmark, executed as a test."""
    started = time.perf_counter()
    response = _stream(client, auth, {"file_format": "CSV",
                                      "source": "SYNTHETIC_BENCHMARK", "total_rows": 50000})
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    reader = csv.reader(io.StringIO(response.text))
    header = next(reader)
    row_count = sum(1 for _ in reader)

    assert row_count == 50000
    assert len(header) == 25

    job_uuid = response.headers["X-Export-Job-Uuid"]
    job = client.get(f"/api/exports/jobs/{job_uuid}", headers=auth("lead")).json()
    assert job["status"] == "COMPLETED"
    assert job["rows_streamed"] == 50000
    assert job["duration_ms"] > 0
    assert job["throughput_rows_per_sec"] > 0
    assert job["file_size_bytes"] > 1_000_000

    validation = client.get(f"/api/exports/{job_uuid}/validate", headers=auth("lead")).json()
    assert validation["result"] == "PASS"
    assert validation["actual_rows_in_file"] == 50000
    assert elapsed < 120, f"export took {elapsed:.1f}s"
