"""Module tests — Stage A deterministic extraction."""
from __future__ import annotations

import pytest

from backend.services.extraction import extract_entities, extract_tboh_ids, normalise_tboh


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Booking TBOH-778899 needs a refund", ["TBOH-778899"]),
        ("ref tboh_554411 please", ["TBOH-554411"]),
        ("see TBOH 640017 and TBOH-901244", ["TBOH-640017", "TBOH-901244"]),
        ("duplicate TBOH-778899 TBOH-778899", ["TBOH-778899"]),
        ("no booking reference here", []),
    ],
)
def test_tboh_extraction_patterns(text, expected):
    assert extract_tboh_ids(text) == expected


def test_normalise_tboh_variants():
    assert normalise_tboh("tboh 778899") == "TBOH-778899"
    assert normalise_tboh("TBOH_778899") == "TBOH-778899"
    assert normalise_tboh("TBOH-778899") == "TBOH-778899"


def test_field_wins_over_description():
    result = extract_entities(
        title="Refund",
        description="The booking TBOH-111111 is stuck",
        tboh_field="TBOH-222222",
    )
    assert result.tboh_ids[0] == "TBOH-222222"
    assert "TBOH-111111" in result.tboh_ids  # sibling reference retained
    assert result.extraction_source == "FIELD"


def test_description_fallback_when_field_empty():
    """The exact Journey A failure mode."""
    result = extract_entities(
        title="Refund not received",
        description="Our client cancelled and the refund for TBOH-778899 is pending.",
        tboh_field="",
    )
    assert result.tboh_ids == ["TBOH-778899"]
    assert result.extraction_source == "DESCRIPTION"


def test_no_booking_present():
    result = extract_entities(title="General question", description="How do I reset my password?")
    assert result.tboh_ids == []
    assert result.extraction_source == "NONE"


def test_supplier_hotel_and_amount_extraction():
    result = extract_entities(
        title="Refund delay",
        description=(
            "Hotelbeds booking at Atlantis The Palm, refund of USD 1,450 still pending "
            "before 12/03/2026."
        ),
    )
    assert "Hotelbeds" in result.suppliers
    assert any("Atlantis" in h for h in result.hotels)
    assert result.amounts and result.amounts[0]["value"] == 1450.0
    assert "2026-03-12" in result.dates


def test_partial_tboh_tokens_are_not_extracted():
    # A 3-digit number must not be treated as a booking id.
    assert extract_tboh_ids("TBOH-123 reference") == []
