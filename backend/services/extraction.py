"""Stage A — deterministic entity extraction (regex, no model, no guessing).

Extraction runs before classification so that booking context, supplier,
property and money are available as *features* for the model and as evidence
for the case brief. It never invents: a value that is not literally present in
the text is not returned.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

TBOH_PATTERN = re.compile(r"\bTBOH[\s_-]?(\d{6,8})\b", re.IGNORECASE)

SUPPLIER_HINTS = (
    "Hotelbeds", "Accor", "Marriott", "Hilton", "Rotana", "Agoda", "Expedia",
    "Booking.com", "Travelgate", "Sabre", "Amadeus", "RateHawk", "WebBeds",
    "TBO Holidays", "Grupo", "Minor Hotels", "Radisson",
)

# Curated property names — a generic regex over "The Palm" style phrases
# produced far too many false positives during development.
KNOWN_HOTELS = (
    "Atlantis The Palm", "Marina Bay Sands", "Hilton Paris Opera", "Ibis Styles Bali",
    "Novotel Bangkok Sukhumvit", "Rotana Downtown Dubai", "Marriott Marquis",
    "Raffles Dubai", "Fairmont The Palm", "Sofitel Dubai The Palm",
    "Address Downtown", "Jumeirah Beach Hotel", "W Singapore Sentosa Cove",
    "Park Hyatt Paris Vendôme", "The Langham London", "Burj Al Arab",
    "Shangri-La Singapore", "Mandarin Oriental Bangkok", "Kempinski Bali",
    "DoubleTree by Hilton London", "Movenpick Dubai", "Pullman Bali Legian",
)

AMOUNT_PATTERN = re.compile(
    r"\b(USD|EUR|GBP|INR|AED|SGD|AUD|THB)\s?([0-9][0-9,]*\.?\d*)", re.IGNORECASE
)
DATE_PATTERNS = (
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})[ -]([A-Za-z]{3})[a-z]*[ -](\d{4})\b"), "dMy"),
)

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


@dataclass
class ExtractionResult:
    tboh_ids: list[str] = field(default_factory=list)
    extraction_source: str = "NONE"          # FIELD | DESCRIPTION | NONE
    suppliers: list[str] = field(default_factory=list)
    hotels: list[str] = field(default_factory=list)
    amounts: list[dict] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "tboh_ids": self.tboh_ids,
            "extraction_source": self.extraction_source,
            "suppliers": self.suppliers,
            "hotels": self.hotels,
            "amounts": self.amounts,
            "dates": self.dates,
        }


def normalise_tboh(value: str | None) -> str | None:
    """Normalise ``tboh 778899`` / ``TBOH_778899`` / ``TBOH-778899``."""
    if not value:
        return None
    match = TBOH_PATTERN.search(value)
    if match:
        return f"TBOH-{match.group(1)}"
    digits = re.sub(r"\D", "", value)
    if 6 <= len(digits) <= 8:
        return f"TBOH-{digits}"
    return None


def extract_tboh_ids(text: str | None) -> list[str]:
    """All booking references in order of appearance, de-duplicated."""
    if not text:
        return []
    seen: list[str] = []
    for match in TBOH_PATTERN.finditer(text):
        candidate = f"TBOH-{match.group(1)}"
        if candidate not in seen:
            seen.append(candidate)
    return seen


def _extract_amounts(text: str) -> list[dict]:
    found: list[dict] = []
    for match in AMOUNT_PATTERN.finditer(text):
        raw = match.group(2).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        found.append({"currency": match.group(1).upper(), "value": value, "raw": match.group(0)})
    return found


def _extract_dates(text: str) -> list[str]:
    found: list[str] = []
    for pattern, kind in DATE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                if kind == "ymd":
                    year, month, day = (int(match.group(i)) for i in (1, 2, 3))
                elif kind == "dmy":
                    day, month, year = (int(match.group(i)) for i in (1, 2, 3))
                else:
                    day = int(match.group(1))
                    month = _MONTHS.get(match.group(2).lower()[:3])
                    year = int(match.group(3))
                    if month is None:
                        continue
                iso = datetime(year, month, day).date().isoformat()
            except (ValueError, TypeError):
                continue
            if iso not in found:
                found.append(iso)
    return found


def _extract_suppliers(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name in SUPPLIER_HINTS if name.lower() in lowered]


def _extract_hotels(text: str) -> list[str]:
    lowered = text.lower()
    return [name for name in KNOWN_HOTELS if name.lower() in lowered]


def extract_entities(
    title: str = "",
    description: str = "",
    tboh_field: str | None = None,
) -> ExtractionResult:
    """Extract entities from a ticket.

    A populated TBOH field always wins; the description is still scanned so
    sibling references (other bookings mentioned in the text) are retained.
    """
    text = f"{title or ''} {description or ''}".strip()
    field_tboh = normalise_tboh(tboh_field)
    text_ids = extract_tboh_ids(text)

    if field_tboh:
        ids = [field_tboh] + [tid for tid in text_ids if tid != field_tboh]
        source = "FIELD"
    elif text_ids:
        ids = text_ids
        source = "DESCRIPTION"
    else:
        ids = []
        source = "NONE"

    return ExtractionResult(
        tboh_ids=ids,
        extraction_source=source,
        suppliers=_extract_suppliers(text),
        hotels=_extract_hotels(text),
        amounts=_extract_amounts(text),
        dates=_extract_dates(text),
    )
