"""Module tests — booking-first case graph, classification and case brief."""
from __future__ import annotations

import pytest

from backend.services.classifier import INTENT_LABELS, IntentClassifier, get_classifier


def test_model_is_loaded_in_ml_mode():
    classifier = get_classifier()
    assert classifier.mode == "ML", f"expected ML mode, got {classifier.mode} ({classifier.load_error})"


def test_fallback_classifier_used_when_artifact_missing(tmp_path):
    """A missing/corrupt artifact must degrade to rules, never crash."""
    broken = IntentClassifier(model_path=tmp_path / "does-not-exist.joblib")
    assert broken.mode == "FALLBACK"
    prediction = broken.classify(
        title="Refund not received",
        description="The refund for our cancelled booking has not been credited.",
    )
    assert prediction.intent == "REFUND_DELAY"
    assert prediction.source == "FALLBACK"
    assert prediction.confidence <= 0.60  # uncalibrated → capped


def test_corrupt_artifact_falls_back(tmp_path):
    corrupt = tmp_path / "corrupt.joblib"
    corrupt.write_bytes(b"not-a-joblib-artifact")
    classifier = IntentClassifier(model_path=corrupt)
    assert classifier.mode == "FALLBACK"


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("Refund pending", "Refund of USD 1450 not received after 20 days for our cancelled stay.", "REFUND_DELAY"),
        ("Cancel after LCD", "Guest needs to cancel but we are past the last cancellation date; requesting a waiver of the penalty.", "CANCELLATION_LCD_WAIVER"),
        ("Voucher missing", "Hotel has no confirmation and the guest checks in tomorrow; voucher not received.", "VOUCHER_CONFIRMATION_ISSUE"),
        ("Name correction", "Please amend the guest name on the booking to the passport spelling.", "AMENDMENT_NAME_DATE"),
        ("Rate mismatch", "Supplier API returned rate mismatch error code 402 between search and book; looks like a cache bug.", "INVENTORY_RATE_SYNC_BUG"),
        ("Honeymoon", "Please arrange honeymoon decoration and a cake at the hotel.", "SPECIAL_REQUEST"),
        ("Overbooked", "The hotel is overbooked and cannot honour the booking; the guest was walked and needs relocation.", "SUPPLIER_OVERBOOKING_RELOCATION"),
        ("Invoice dispute", "The invoice shows a different amount; please issue a credit note for the duplicate charge.", "BILLING_INVOICE_DISPUTE"),
    ],
)
def test_classifier_covers_all_eight_intents(title, description, expected):
    prediction = get_classifier().classify(title=title, description=description)
    assert prediction.intent in INTENT_LABELS
    assert 0.0 <= prediction.confidence <= 1.0
    assert prediction.intent == expected, (
        f"expected {expected}, got {prediction.intent} @ {prediction.confidence:.2f}"
    )


def test_reasoning_is_evidence_based():
    prediction = get_classifier().classify(
        title="Refund not received",
        description="Refund of USD 1,450 for TBOH-778899 has not been credited.",
        tboh_id="TBOH-778899",
        extraction_source="DESCRIPTION",
        prior_count=2,
        hours_to_lcd=6,
    )
    joined = " ".join(prediction.reasoning)
    assert "refund" in joined.lower()
    assert "TBOH-778899" in joined
    assert "2 prior ticket" in joined
    assert "recovered from the description" in joined
    assert "LCD in" in joined


def test_journey_a_style_ticket_links_the_case(client, auth):
    created = client.post("/api/tickets", headers=auth("agency"), json={
        "title": "Refund still not received",
        "description": "The refund of USD 1,450 for TBOH-778899 has not been credited.",
        "tboh_id": "",
        "priority": "HIGH",
    })
    assert created.status_code == 201, created.text
    payload = created.json()

    assert payload["extraction"]["tboh_ids"] == ["TBOH-778899"]
    assert payload["extraction"]["extraction_source"] == "DESCRIPTION"
    assert payload["classification"]["intent"] == "REFUND_DELAY"
    assert payload["booking"]["tboh_id"] == "TBOH-778899"

    detail = client.get(f"/api/tickets/{payload['ticket_id']}", headers=auth("agent")).json()
    numbers = {r["ticket_number"] for r in detail["related_tickets"]}
    assert {"TCK-101", "TCK-104", "TCK-109"}.issubset(numbers)

    same_booking = [r for r in detail["related_tickets"] if r["link_type"] == "SAME_BOOKING"]
    assert len(same_booking) >= 3
    assert all(r["confidence"] == 1.0 for r in same_booking)
    assert all(r["reason"] for r in detail["related_tickets"])


def test_case_brief_has_three_evidence_bound_points(client, auth):
    detail = client.get("/api/tickets/1", headers=auth("agent")).json()
    brief = detail["case_brief"]
    assert len(brief["points"]) == 3
    assert brief["tickets_in_case"] >= 1
    assert brief["sources"]["booking_id"] is not None
    # every point must cite real, present data
    assert "TBOH-" in brief["points"][0]


def test_case_brief_never_invents_missing_supplier(client, auth):
    """A ticket without a booking must say so rather than fabricate one."""
    lead_headers = auth("lead")
    agencies = client.get("/api/agencies", headers=lead_headers).json()["agencies"]
    created = client.post("/api/tickets", headers=lead_headers, json={
        "title": "General enquiry about invoices",
        "description": "Please share the invoice template used for corporate accounts.",
        "priority": "LOW",
        "agency_id": agencies[0]["id"],
    })
    assert created.status_code == 201
    brief = client.get(
        f"/api/tickets/{created.json()['ticket_id']}/case-brief", headers=lead_headers
    ).json()
    assert "No booking record is linked" in brief["points"][1]
    assert brief["sources"]["booking_id"] is None


def test_manual_intent_override_is_audited(client, auth):
    response = client.post("/api/tickets/1/intent-override", headers=auth("agent"),
                           json={"intent": "SPECIAL_REQUEST", "note": "Agency clarified by phone"})
    assert response.status_code == 200
    assert response.json()["intent"] == "SPECIAL_REQUEST"
    assert response.json()["intent_source"] == "MANUAL"

    detail = client.get("/api/tickets/1", headers=auth("agent")).json()
    assert detail["classification"]["intent"] == "SPECIAL_REQUEST"
    events = [e["event_type"] for e in detail["activity_timeline"]]
    assert "INTENT_OVERRIDE" in events


def test_agency_requester_cannot_override_intent(client, auth):
    response = client.post("/api/tickets/1/intent-override", headers=auth("agency"),
                           json={"intent": "SPECIAL_REQUEST"})
    assert response.status_code == 403
