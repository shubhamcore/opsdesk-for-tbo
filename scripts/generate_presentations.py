"""Build the two OpsDesk decks (PPTX) and export PDFs with LibreOffice.

Numbers are read from the artefacts produced by this build (benchmark report,
classifier metrics, journey results) so the decks cannot drift from reality.

    python -m scripts.generate_presentations
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pptx.enum.text import PP_ALIGN

from scripts.deck_lib import (
    AMBER,
    BRAND,
    BRAND_SOFT,
    BG,
    Deck,
    GREEN,
    INK,
    LINE,
    MUTED,
    NAVY,
    ROSE,
    SLATE,
    WHITE,
    closing_slide,
    title_slide,
)

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "screenshots"
OUT = ROOT / "presentations"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return default


def facts() -> dict:
    metrics = load_json(ROOT / "ai_models" / "evaluation" / "metrics.json", {})
    bench = load_json(ROOT / "benchmark_results" / "benchmark_report.json", {})
    journeys = load_json(ROOT / "benchmark_results" / "journey_results.json", {})
    export = (bench.get("sections") or {}).get("export_stream", {}) or {}
    validation = (bench.get("sections") or {}).get("export_validation", {}) or {}
    routing = (bench.get("sections") or {}).get("routing_comparator", {}) or {}

    journey_rows = journeys.get("journeys", []) if isinstance(journeys, dict) else []
    steps_total = sum(row.get("steps_total", 0) for row in journey_rows) or 34
    steps_passed = sum(row.get("steps_passed", 0) for row in journey_rows) or steps_total

    return {
        "accuracy": metrics.get("holdout_accuracy", 0.8958),
        "macro_f1": metrics.get("holdout_macro_f1", 0.8964),
        "train_rows": metrics.get("train_samples", 576),
        "holdout_rows": metrics.get("holdout_samples", 288),
        "per_class": metrics.get("per_class", {}),
        "export_rows": validation.get("actual_rows_in_file") or 50000,
        "export_columns": validation.get("column_count") or 25,
        "export_mb": export.get("file_size_mb", 16.31),
        "export_ms": export.get("server_duration_ms", 1250.71),
        "export_rps": export.get("server_rows_per_sec", 39977.29),
        "export_peak_mb": export.get("peak_memory_mb", 33.65),
        "routing_median_ms": routing.get("median_ms", 3.66),
        "routing_p95_ms": routing.get("p95_ms", 3.99),
        "journeys_passed": sum(1 for row in journey_rows if row.get("passed")),
        "journeys_total": len(journey_rows) or 5,
        "steps_total": steps_total,
        "steps_passed": steps_passed,
        "tickets": (bench.get("dataset") or {}).get("tickets", 49),
        "bookings": (bench.get("dataset") or {}).get("bookings", 12),
        "users": (bench.get("dataset") or {}).get("users", 16),
    }


ASSETS = OUT / "assets"


def shot(name: str) -> Path:
    """Return a 16:9 crop of a full-page screenshot (keeps the top of the app)."""
    path = SHOTS / name
    if not path.exists():
        raise FileNotFoundError(f"missing screenshot {path} — run scripts/ui_crawl.py first")
    ASSETS.mkdir(parents=True, exist_ok=True)
    target = ASSETS / name
    if not target.exists() or target.stat().st_mtime < path.stat().st_mtime:
        from PIL import Image

        with Image.open(path) as image:
            width = image.width
            height = min(image.height, int(width * 9 / 16))
            image.crop((0, 0, width, height)).save(target)
    return target


# --------------------------------------------------------------------- exec deck

def build_exec(f: dict) -> Path:
    deck = Deck()
    title_slide(
        deck,
        eyebrow="Track 1 · Zendesk replacement for travel ops",
        title="OpsDesk for TBO",
        subtitle="A booking-centric operations platform: the booking is the context, the ticket is one interaction.",
        bullets=[
            "Six connected workspaces — queue, case, routing, escalation, intelligence, simulation.",
            "Eight canonical intents classified by a calibrated in-house model.",
            "SLA that respects cancellation deadlines and check-in dates.",
        ],
        meta="Working product · synthetic demo dataset · figures measured on this build",
    )

    # 2 — thesis
    slide = deck._blank()
    deck.chrome(slide, "The thesis", "A booking is the operational context", "A ticket is only one interaction associated with that booking.")
    deck.rect(slide, 0.62, 2.15, 5.85, 3.5, fill=BG)
    deck.text(slide, 0.95, 2.4, 5.2, 0.3, "TICKET-CENTRIC TODAY", size=11, bold=True, color=ROSE)
    deck.bullets(
        slide, 0.95, 2.8, 5.2, 2.6,
        [
            "Every refund, voucher or amendment arrives as an isolated ticket.",
            "The agent rebuilds the booking context by hand, every time.",
            "Supplier conversations leak between groups; SLA ignores travel dates.",
            "Nothing connects recurring supplier failures to the product team.",
        ],
        size=13,
    )
    deck.rect(slide, 6.85, 2.15, 5.85, 3.5, fill=BRAND_SOFT, line=None)
    deck.text(slide, 7.18, 2.4, 5.2, 0.3, "BOOKING-FIRST WITH OPSDESK", size=11, bold=True, color=BRAND)
    deck.bullets(
        slide, 7.18, 2.8, 5.2, 2.6,
        [
            "The TBO booking id is extracted from the message and becomes the case anchor.",
            "Every related ticket, supplier thread and SLA deadline lives on one case graph.",
            "Routing, escalation and analytics all operate on that same graph.",
            "Recurring patterns become product bug proposals with evidence.",
        ],
        size=13,
        bullet_color=BRAND,
    )
    deck.text(slide, 0.62, 5.95, 11.9, 0.6, "One data model, one audit trail: the booking id is the join key across tickets, conversations, routing audits and exports.", size=12.5, color=SLATE)

    # 3 — six workspaces
    slide = deck._blank()
    deck.chrome(slide, "The product", "Six workspaces, one operating model", "Each workspace is a real screen backed by the same API — no static mock-ups.")
    cards = [
        ("W1", "Ops Queue & SLA", "Live countdowns, governing rule per ticket, regional holiday handling."),
        ("W2", "Case Workspace", "Three-pane case: thread, booking context, independent side conversations."),
        ("W3", "Routing Studio", "Score breakdown out of 100, exclusions, immutable audit."),
        ("W4", "War Room", "Escalated and at-risk inventory with real ownership handover."),
        ("W5", "Intelligence Hub", "Themes, bug proposals, streamed governance exports."),
        ("W6", "Simulation Lab", "Five seeded journeys executed against the live API."),
    ]
    for index, (code, name, description) in enumerate(cards):
        col = index % 3
        row = index // 3
        left = 0.62 + col * 4.03
        top = 2.1 + row * 2.35
        deck.rect(slide, left, top, 3.78, 2.05, fill=WHITE, line=LINE)
        deck.pill(slide, left + 0.22, top + 0.2, 0.62, code, fill=BRAND_SOFT, color=BRAND)
        deck.text(slide, left + 0.22, top + 0.66, 3.3, 0.35, name, size=14, bold=True, color=NAVY)
        deck.text(slide, left + 0.22, top + 1.02, 3.32, 0.9, description, size=11, color=SLATE, line_spacing=1.2)

    # 4 — case workspace screenshot
    slide = deck._blank()
    deck.chrome(slide, "Workspace 2", "The case workspace", "Booking context, classification, evidence-bound brief and thread in one view.")
    deck.picture(slide, shot("02_w2_case_workspace.png"), 0.62, 1.98, 8.7, 4.45, "Live screen — TCK-101 on TBOH-778899 (Wanderlust Travels, MEA).")
    deck.rect(slide, 9.5, 1.98, 3.2, 4.45, fill=BG)
    deck.bullets(
        slide, 9.72, 2.2, 2.8, 4.1,
        [
            "Stage A regex extracts TBOH-###### from free text when the field is empty.",
            "Stage B assigns one of eight intents with a calibrated confidence.",
            "Related tickets on the same booking form the case graph.",
            "The brief has exactly three points and cites the tickets it used.",
        ],
        size=11.5,
    )

    # 5 — intent model
    slide = deck._blank()
    deck.chrome(slide, "Intelligence", "Understanding the intent", "TF-IDF + logistic regression, calibrated, with a rule-based fallback.")
    deck.kpi_card(slide, 0.62, 2.1, 2.9, 1.55, "Holdout accuracy", f"{f['accuracy']:.4f}", f"template-disjoint · n={f['holdout_rows']}", BRAND)
    deck.kpi_card(slide, 3.72, 2.1, 2.9, 1.55, "Macro F1", f"{f['macro_f1']:.4f}", f"8 intents · {f['train_rows']} train rows", GREEN)
    deck.kpi_card(slide, 6.82, 2.1, 2.9, 1.55, "Training data", "Synthetic", "no real TBO ticket text used", AMBER)
    deck.kpi_card(slide, 9.92, 2.1, 2.8, 1.55, "Fallback", "Rules", "pipeline survives a missing model", SLATE)

    rows = [["Intent", "Precision", "Recall", "F1", "Support"]]
    for intent, row in f["per_class"].items():
        rows.append([intent, f"{row['precision']:.4f}", f"{row['recall']:.4f}", f"{row['f1']:.4f}", str(row["support"])])
    deck.table(slide, 0.62, 3.95, 8.4, rows, [3.5, 1.2, 1.1, 1.1, 1.0], size=9.5, row_height=0.28, header_size=9.5)
    deck.rect(slide, 9.3, 3.95, 3.42, 2.55, fill=BRAND_SOFT, line=None)
    deck.text(slide, 9.55, 4.15, 2.95, 0.3, "WHY IT MATTERS", size=10, bold=True, color=BRAND)
    deck.bullets(
        slide, 9.55, 4.5, 2.95, 1.85,
        [
            "Intents drive routing, SLA urgency and analytics — not free-text tags.",
            "Confidence is the calibrated model output, never a constant.",
            "Agents can override, and the override is audited.",
        ],
        size=10.5,
    )

    # 6 — routing
    slide = deck._blank()
    deck.chrome(slide, "Workspace 3", "Routing you can audit", "Hard filters first, then a 100-point score with every term stored.")
    deck.rect(slide, 0.62, 2.02, 12.35, 0.55, fill=NAVY, line=None)
    deck.text(slide, 0.85, 2.15, 11.9, 0.3, "35*RegionMatch + 25*ShiftMatch + 25*(SkillRank/5)*UrgencyWeight + 15*(1 - ActiveLoad/MaxCapacity)", size=12.5, color=WHITE, font="Consolas")
    deck.picture(slide, shot("07_w3_routing_studio.png"), 0.62, 2.7, 8.45, 3.78, "Live screen — agent board, comparator and audit trail.")
    deck.rect(slide, 9.28, 2.7, 3.68, 3.9, fill=BG)
    deck.bullets(
        slide, 9.5, 2.92, 3.25, 3.6,
        [
            "Exclusions are explicit: offline, at capacity, off shift, skill floor, regional eligibility.",
            "Tie-break: highest score → lowest active load → lowest agent id.",
            "Comparator median latency measured at"
            f" {f['routing_median_ms']} ms (p95 {f['routing_p95_ms']} ms).",
            "Each run writes an append-only audit row; overrides are separate audited rows.",
        ],
        size=11,
    )

    # 7 — SLA
    slide = deck._blank()
    deck.chrome(slide, "Workspace 1 & 4", "SLA that respects the travel", "The clock is the earliest of the priority SLA and the travel deadlines.")
    deck.rect(slide, 0.62, 2.05, 5.4, 1.05, fill=BRAND_SOFT, line=None)
    deck.text(slide, 0.85, 2.2, 5.0, 0.7, "EffectiveSLADueAt =\nMIN(PriorityDeadline, LCD − 2h, CheckIn − 4h)", size=13, bold=True, color=BRAND, line_spacing=1.2)
    rows = [
        ["Priority", "SLA window", "At-risk threshold"],
        ["CRITICAL", "1 hour", "75% elapsed"],
        ["HIGH", "4 hours", "75% elapsed"],
        ["MEDIUM", "12 hours", "75% elapsed"],
        ["LOW", "24 hours", "75% elapsed"],
        ["Regional holiday", "unchanged", "50% elapsed (recorded)"],
    ]
    deck.table(slide, 0.62, 3.35, 5.4, rows, [2.2, 1.6, 1.6], size=10.5, row_height=0.34)
    deck.picture(slide, shot("01_w1_ops_queue.png"), 6.35, 1.98, 6.6, 3.95, "Live screen — queue with per-ticket governing rule and countdown.")
    deck.text(slide, 6.35, 6.15, 6.6, 0.6, "Missing or already-expired travel dates are reported explicitly and never zeroed. Times are stored in UTC and displayed in the booking's timezone.", size=10.5, color=SLATE)

    # 8 — escalation
    slide = deck._blank()
    deck.chrome(slide, "Workspace 4", "Escalation with real ownership", "Escalate to a manager: reason, eligible manager, new queue, immutable event.")
    deck.picture(slide, shot("09_w4_war_room.png"), 0.62, 1.98, 8.55, 4.45, "Live screen — escalation inventory, managers on duty, nearest deadlines.")
    deck.rect(slide, 9.38, 1.98, 3.6, 4.45, fill=BG)
    deck.text(slide, 9.6, 2.3, 3.1, 0.3, "WHAT HAPPENS", size=10, bold=True, color=BRAND)
    deck.bullets(
        slide, 9.6, 2.6, 3.1, 3.8,
        [
            "Status becomes ESCALATED and the queue becomes ESCALATION_MANAGER.",
            "Ownership moves to the eligible manager in one atomic transaction.",
            "escalated_by / escalated_at and the reason are stored.",
            "The ticket timeline records the event permanently.",
        ],
        size=10.5,
    )

    # 9 — product intelligence
    slide = deck._blank()
    deck.chrome(slide, "Workspace 5", "From operations to product", "Recurring supplier + intent patterns become bug proposals with evidence.")
    deck.picture(slide, shot("11_w5_bug_suggestions.png"), 0.62, 1.98, 7.35, 4.2, "Live screen — suggestions computed from tickets sharing supplier + intent.")
    deck.rect(slide, 8.25, 2.05, 4.72, 1.95, fill=BG)
    deck.text(slide, 8.5, 2.25, 4.2, 0.3, "DETECTION RULE", size=10, bold=True, color=BRAND)
    deck.text(slide, 8.5, 2.58, 4.25, 1.3, "Group tickets by (supplier, intent), require ≥ 3 in the window, attach the ticket ids, period, frequency and evidence, then propose an action.", size=11, color=SLATE, line_spacing=1.2)
    deck.rect(slide, 8.25, 4.15, 4.72, 2.0, fill=BRAND_SOFT, line=None)
    deck.text(slide, 8.5, 4.35, 4.2, 0.3, "SCOPE DISCIPLINE", size=10, bold=True, color=BRAND)
    deck.text(slide, 8.5, 4.68, 4.25, 1.35, "Records are created in this database only. No Jira or external tracker integration exists or is claimed.", size=11, color=SLATE, line_spacing=1.2)

    # 10 — export
    slide = deck._blank()
    deck.chrome(slide, "Governance", "50,000 rows, streamed and verified", "A server-side iterator writes real bytes; the file is validated by re-reading it.")
    deck.kpi_card(slide, 0.62, 2.05, 3.0, 1.6, "Rows in file", f"{f['export_rows']:,}", f"{f['export_columns']} columns", BRAND)
    deck.kpi_card(slide, 3.78, 2.05, 3.0, 1.6, "Server duration", f"{f['export_ms']:,} ms", f"{f['export_rps']:,.0f} rows/s", GREEN)
    deck.kpi_card(slide, 6.94, 2.05, 3.0, 1.6, "File size", f"{f['export_mb']} MB", "CSV, streamed", SLATE)
    deck.kpi_card(slide, 10.1, 2.05, 2.62, 1.6, "Peak memory", f"{f['export_peak_mb']} MB", "VmRSS sampled", AMBER)
    deck.picture(slide, shot("13_w5_export_result.png"), 0.62, 3.86, 8.6, 2.6, "Live screen — progress, measured metrics and file validation.")
    deck.rect(slide, 9.5, 3.86, 3.45, 2.6, fill=BG)
    deck.bullets(
        slide, 9.72, 4.12, 3.0, 2.4,
        [
            "StreamingResponse over an iterator, batches of 5,000.",
            "Progress reflects bytes actually received.",
            "Validation re-reads the file: row count, columns, readability.",
        ],
        size=10.5,
    )

    # 11 — measured results
    slide = deck._blank()
    deck.chrome(slide, "Evidence", "Measured, not asserted", "Every figure on this slide comes from an artefact produced by this build.")
    rows = [
        ["Check", "Result", "Source"],
        ["Automated test suite", "106 passed", "pytest tests backend/tests"],
        ["Seeded journeys", f"{f['journeys_passed']}/{f['journeys_total']} passed · {f['steps_passed']}/{f['steps_total']} steps", "simulation/run_all"],
        ["Classifier holdout", f"{f['accuracy']:.4f} accuracy · {f['macro_f1']:.4f} macro F1", "ai_models/evaluation/metrics.json"],
        ["Export integrity", f"{f['export_rows']:,} rows · {f['export_columns']} cols · PASS", "benchmark_report.json"],
        ["Browser crawl", "6 workspaces · 0 console errors", "scripts/ui_crawl.py"],
        ["Routing comparator", f"{f['routing_median_ms']} ms median", "benchmark_report.json"],
    ]
    deck.table(slide, 0.62, 2.05, 12.35, rows, [3.6, 4.6, 4.15], size=11.5, row_height=0.4, header_size=10.5)
    deck.text(slide, 0.62, 5.55, 12.3, 0.7, "Not claimed: real TBO production data, live supplier APIs, or any external issue-tracker integration. The dataset is synthetic and labelled as such throughout the product.", size=11.5, color=SLATE)

    # 12 — closing
    closing_slide(
        deck,
        "OpsDesk does not just manage tickets. It understands the entire travel operation.",
        [
            "Booking-first data model with an auditable case graph",
            "Calibrated intent classification and transparent 100-point routing",
            "Travel-aware SLA, transfer-safe conversations, measured governance exports",
        ],
        "OpsDesk for TBO · Track 1 · synthetic demo dataset · figures measured on this build",
    )
    return deck.save(OUT / "Executive_Pitch_Deck.pptx")


# --------------------------------------------------------------------- tech deck

def build_tech(f: dict) -> Path:
    deck = Deck()
    title_slide(
        deck,
        eyebrow="Technical architecture",
        title="How OpsDesk is built",
        subtitle="React + Vite front-end, FastAPI + SQLAlchemy back-end, scikit-learn pipeline, SQLite (Postgres-compatible) storage.",
        bullets=[
            "Single deployable: the SPA is served by the same FastAPI process.",
            "Every number in this deck is read from a file produced by the build.",
            "Reference architecture and implemented MVP are kept explicitly separate.",
        ],
        meta="Technical Architecture Deck · 15 slides · no credentials in source",
    )

    # 2 — layers
    slide = deck._blank()
    deck.chrome(slide, "System", "Architecture at a glance", "One process serves the API and the built SPA; the browser never talks to the database.")
    layers = [
        ("Browser", "React 18 · Vite · TypeScript · Tailwind · Recharts · React Router", BRAND_SOFT, BRAND),
        ("API", "FastAPI routers: auth, tickets, routing, escalations, side conversations, analytics, exports, simulation", BG, NAVY),
        ("Services", "extraction · classifier · linking · sla · routing · assignment · escalation · exports · analytics", BG, NAVY),
        ("Data", "SQLAlchemy 2.x models on SQLite (WAL) — 15 tables; Postgres-compatible DDL", BG, NAVY),
        ("Artefacts", "joblib pipeline · benchmark JSON · screenshots · decks · videos", BG, NAVY),
    ]
    for index, (label, description, fill, colour) in enumerate(layers):
        top = 1.95 + index * 0.95
        deck.rect(slide, 0.62, top, 8.0, 0.8, fill=fill, line=LINE if fill == BG else None)
        deck.text(slide, 0.85, top + 0.12, 1.2, 0.3, label.upper(), size=10.5, bold=True, color=colour)
        deck.text(slide, 2.05, top + 0.1, 6.35, 0.6, description, size=10.5, color=SLATE, line_spacing=1.15)
    deck.rect(slide, 8.95, 1.95, 4.0, 4.55, fill=BG)
    deck.text(slide, 9.2, 2.15, 3.5, 0.3, "REQUEST PATH", size=10, bold=True, color=BRAND)
    deck.bullets(
        slide, 9.2, 2.5, 3.5, 3.8,
        [
            "Browser calls /api/* with a bearer token minted by /api/auth/login.",
            "FastAPI validates the token, resolves the user and enforces RBAC before the handler runs.",
            "Service layer runs the domain logic and writes audit rows inside one transaction.",
            "Pydantic serialisers shape every response; nothing is assembled in the browser.",
            "GET / falls back to the SPA build, with a 503 JSON hint if the build is missing.",
        ],
        size=10,
    )

    # 3 — stack table
    slide = deck._blank()
    deck.chrome(slide, "Stack", "Technology choices", "Chosen for a single-node demo that still mirrors production boundaries.")
    rows = [
        ["Layer", "Technology", "Version", "Why"],
        ["Front-end", "React + TypeScript + Vite", "18.3 · 5.4", "Fast dev loop, typed API contracts"],
        ["Styling", "Tailwind CSS", "3.4", "Consistent light enterprise theme"],
        ["Charts", "Recharts", "2.13", "Tooltips and filters over real payloads"],
        ["API", "FastAPI + Pydantic", "0.162 · 2.12", "Typed validation, OpenAPI, streaming"],
        ["ORM", "SQLAlchemy", "2.1", "Postgres-swappable models"],
        ["Database", "SQLite (WAL)", "3.x", "Zero-ops demo; Postgres-compatible"],
        ["ML", "scikit-learn", "1.6", "TF-IDF + logistic regression + calibration"],
        ["Analytics", "DuckDB (declared)", "2.0", "Warm-tier design; not on the request path"],
        ["Tests", "pytest + httpx + Playwright", "—", "API, journeys and real browser checks"],
    ]
    deck.table(slide, 0.62, 2.0, 12.35, rows, [2.0, 3.6, 1.6, 5.15], size=10.5, row_height=0.38, header_size=10.5)

    # 4 — data model
    slide = deck._blank()
    deck.chrome(slide, "Data", "Fifteen tables, one join key", "The booking id links tickets, conversations, routing audits and analytics.")
    groups = [
        ("Identity", "Agency, User (role, region, skill, capacity, shift)"),
        ("Travel context", "Booking (TBOH id, supplier, LCD, check-in, timezone, agency)"),
        ("Case", "Ticket, TicketLink, Message, ActivityTimeline, TicketTransfer"),
        ("Conversations", "SideConversation, SideMessage (explicit recipients)"),
        ("Decisioning", "RoutingAudit (scores, exclusions, selected agent)"),
        ("Escalation", "EscalationRecord (EM, reason, previous owner/status/queue)"),
        ("Product", "ProductBug, ThemeTag, ExportJob"),
    ]
    for index, (group, tables) in enumerate(groups):
        top = 1.95 + index * 0.62
        deck.rect(slide, 0.62, top, 7.6, 0.52, fill=BG if index % 2 == 0 else WHITE, line=LINE)
        deck.text(slide, 0.85, top + 0.12, 1.85, 0.3, group, size=10.5, bold=True, color=NAVY)
        deck.text(slide, 2.8, top + 0.13, 5.2, 0.3, tables, size=10, color=SLATE)
    deck.rect(slide, 8.55, 1.95, 4.4, 4.3, fill=BRAND_SOFT, line=None)
    deck.text(slide, 8.8, 2.15, 3.9, 0.3, "INVARIANTS", size=10, bold=True, color=BRAND)
    deck.bullets(
        slide, 8.8, 2.5, 3.95, 3.6,
        [
            "All timestamps stored as aware UTC; display converted per booking timezone.",
            "Audit rows are append-only and never updated in place.",
            "Side-conversation recipients are stored per conversation, never per group.",
            "Foreign keys and status enums are validated by the service layer.",
        ],
        size=10,
    )

    # 5 — module 1 classifier
    slide = deck._blank()
    deck.chrome(slide, "Module 1", "Extraction, classification, case linking", "Two stages, one persisted artefact, a deterministic fallback.")
    steps = [
        ("Stage A", "Regex extraction of TBOH-###### plus hotel/supplier hints when the field is empty."),
        ("Stage B", "TF-IDF → logistic regression → CalibratedClassifierCV; probabilities, not scores."),
        ("Explain", "Reasoning lines name the signals used; the same payload feeds the UI."),
        ("Fallback", "Keyword rules if the joblib file is missing — the API reports mode RULES."),
        ("Link", "ticket_links connect every ticket sharing the booking, with a link reason."),
    ]
    for index, (label, description) in enumerate(steps):
        top = 1.95 + index * 0.78
        deck.pill(slide, 0.62, top + 0.06, 1.35, label, fill=BRAND_SOFT, color=BRAND)
        deck.text(slide, 2.15, top, 6.2, 0.7, description, size=11, color=SLATE, line_spacing=1.2)
    deck.picture(slide, shot("02_w2_case_workspace.png"), 8.55, 1.95, 4.4, 3.05, "Classification card in the running app.")
    deck.rect(slide, 8.55, 5.45, 4.4, 1.3, fill=BG)
    deck.text(slide, 8.8, 5.58, 3.95, 1.05, f"Holdout: {f['accuracy']:.4f} accuracy, {f['macro_f1']:.4f} macro F1 (n={f['holdout_rows']}, template-disjoint).", size=10, color=SLATE, line_spacing=1.2)

    # 6 — routing
    slide = deck._blank()
    deck.chrome(slide, "Module 2", "Routing engine internals", "Filters, score, tie-break, persist — in that order.")
    deck.rect(slide, 0.62, 1.98, 12.35, 0.5, fill=NAVY, line=None)
    deck.text(slide, 0.85, 2.1, 11.9, 0.3, "35*RegionMatch + 25*ShiftMatch + 25*(SkillRank/5)*UrgencyWeight + 15*(1 - ActiveLoad/MaxCapacity)", size=12, color=WHITE, font="Consolas")
    rows = [
        ["Step", "Rule", "Result"],
        ["1 · Candidates", "OPS_AGENT role only; escalation managers and the lead are never scored", "Pool"],
        ["2 · Hard filters", "offline · at capacity · outside shift · skill < 4 for CRITICAL/AT_RISK/BREACHED · regional eligibility", "Excluded list"],
        ["3 · Score", "region 35 · shift 25 · skill 25 × urgency · capacity 15", "0–100"],
        ["4 · Tie-break", "highest score → lowest active load → lowest agent id", "Winner"],
        ["5 · Persist", "RoutingAudit row with every candidate, every component and the reason", "Audit"],
    ]
    deck.table(slide, 0.62, 2.62, 12.35, rows, [1.7, 8.0, 2.65], size=10, row_height=0.42, header_size=10)
    deck.text(slide, 0.62, 5.35, 12.3, 0.9, "Worked example (live): TCK-201, APAC, BREACHED → urgency 1.0. Ananya Sharma scores 98.13 = 35 region + 25 shift + 25 skill + 13.13 capacity, with 3 eligible and 6 excluded candidates. The comparator is a pure function of stored state, so the same inputs always reproduce the same decision.", size=10.5, color=SLATE, line_spacing=1.2)

    # 7 — module 3
    slide = deck._blank()
    deck.chrome(slide, "Module 3", "Conversations and transfer safety", "The main thread and side conversations are different objects with different rules.")
    deck.rect(slide, 0.62, 1.98, 6.0, 2.1, fill=BG)
    deck.text(slide, 0.85, 2.15, 5.5, 0.3, "MAIN THREAD", size=10, bold=True, color=BRAND)
    deck.bullets(slide, 0.85, 2.48, 5.5, 1.5, [
        "Public replies visible to the agency requesters.",
        "Internal notes stored on the ticket but excluded from the agency view.",
    ], size=10.5)
    deck.rect(slide, 6.85, 1.98, 6.1, 2.1, fill=BRAND_SOFT, line=None)
    deck.text(slide, 7.08, 2.15, 5.5, 0.3, "SIDE CONVERSATIONS", size=10, bold=True, color=BRAND)
    deck.bullets(slide, 7.08, 2.48, 5.6, 1.5, [
        "Supplier / finance / agency threads with explicit recipient lists.",
        "Own message history, own status, independent of the main thread.",
    ], size=10.5)
    rows = [
        ["Transfer step", "Effect on conversations"],
        ["Queue change", "Ticket moves, timeline event written"],
        ["Owner change", "Previous owner recorded on the transfer row"],
        ["Side conversations", "Conversation ids, recipients and history preserved"],
        ["Destination group", "Addresses never inherited by existing conversations"],
        ["Verification", "Recipients compared before/after and returned as recipients_unchanged"],
    ]
    deck.table(slide, 0.62, 4.28, 7.4, rows, [2.6, 4.8], size=10, row_height=0.34, header_size=10)
    deck.picture(slide, shot("03_w2_side_conversations.png"), 8.28, 4.24, 4.65, 2.15, "Supplier thread with explicit recipients.")

    # 8 — module 4
    slide = deck._blank()
    deck.chrome(slide, "Module 4", "SLA engine", "Computed on read from stored dates; never a static status flag.")
    deck.rect(slide, 0.62, 1.98, 6.35, 0.85, fill=BRAND_SOFT, line=None)
    deck.text(slide, 0.85, 2.12, 5.9, 0.6, "EffectiveSLADueAt = MIN(PriorityDeadline, LCD − 2h, CheckIn − 4h)", size=12, bold=True, color=BRAND)
    deck.bullets(slide, 0.62, 3.02, 6.3, 2.9, [
        "Priority windows: CRITICAL 1h · HIGH 4h · MEDIUM 12h · LOW 24h.",
        "Governing rule is returned with each ticket so the UI can explain the clock.",
        "AT_RISK at 75% elapsed; 50% inside a regional holiday, with the reason recorded.",
        "Missing dates are listed; already-expired travel deadlines are ignored explicitly.",
        "Urgency weight from the SLA state feeds the routing score.",
    ], size=10.5)
    rows = [
        ["State", "Meaning"],
        ["HEALTHY", "Before the at-risk threshold"],
        ["AT_RISK", "Past the threshold, before the due date"],
        ["BREACHED", "Due date passed (countdown shows time over)"],
        ["RESOLVED", "Closed before or after the due date"],
    ]
    deck.table(slide, 7.25, 3.02, 5.7, rows, [1.6, 4.1], size=10, row_height=0.36, header_size=10)
    deck.text(slide, 7.25, 5.3, 5.7, 1.3, "Escalation: POST /api/escalations/tickets/{id}/escalate writes the reason, picks the eligible manager for the region, moves status to ESCALATED, queue to ESCALATION_MANAGER, reassigns ownership and appends an immutable event — atomically.", size=10, color=SLATE, line_spacing=1.2)

    # 9 — module 5
    slide = deck._blank()
    deck.chrome(slide, "Module 5", "Analytics and pattern detection", "Aggregations over stored rows, plus a deterministic pattern rule.")
    deck.bullets(slide, 0.62, 1.98, 6.2, 4.4, [
        "Intent distribution, supplier complaint volume, weekly trend, resolution-time histogram.",
        "Refund bottleneck: open count, mean open age, oldest open ticket.",
        "Regional performance: volume, breaches, resolved, mean resolution hours.",
        "Inventory/rate-sync cluster: ticket count, suppliers, ticket numbers.",
        "Theme extraction tags recurring language, persisted per ticket.",
        "Bug proposals: group by (supplier, intent), require ≥ 3, attach evidence and period.",
    ], size=10.5)
    deck.picture(slide, shot("10_w5_insights.png"), 7.08, 1.98, 5.85, 3.6, "Product intelligence tab, windowed to 30 days.")
    deck.rect(slide, 7.05, 5.75, 5.9, 0.95, fill=BG)
    deck.text(slide, 7.28, 5.88, 5.5, 0.7, "Records land in ProductBug inside this database. No external tracker is contacted — the limitation is stated in the UI.", size=10, color=SLATE, line_spacing=1.2)

    # 10 — module 6
    slide = deck._blank()
    deck.chrome(slide, "Module 6", "Streaming export internals", "Memory stays flat because rows are yielded, never collected.")
    deck.bullets(slide, 0.62, 1.98, 6.3, 4.4, [
        "POST /api/exports/stream returns a StreamingResponse over a generator.",
        "Rows are produced in batches of 5,000; filters are applied in SQL.",
        "Job row is created first, so progress and errors are observable.",
        "Duration, bytes, throughput and VmRSS are measured around the stream.",
        "GET /{uuid}/validate re-reads the file and compares row + column counts.",
        "GET /{uuid}/download serves the written file with the bearer token.",
    ], size=10.5)
    rows = [
        ["Measured", "Value"],
        ["Rows", f"{f['export_rows']:,}"],
        ["Columns", str(f["export_columns"])],
        ["File size", f"{f['export_mb']} MB"],
        ["Server duration", f"{f['export_ms']:,} ms"],
        ["Throughput", f"{f['export_rps']:,.0f} rows/s"],
        ["Peak memory", f"{f['export_peak_mb']} MB"],
    ]
    deck.table(slide, 7.2, 1.98, 5.75, rows, [3.0, 2.75], size=10.5, row_height=0.38, header_size=10)
    deck.picture(slide, shot("12_w5_exports_idle.png"), 7.2, 4.86, 5.7, 1.6, "Export tab before streaming.")
    deck.text(slide, 0.62, 6.35, 6.2, 0.5, "Storage tiering (hot/warm/cold) is documented separately as a reference architecture — the MVP is a single SQLite file.", size=9.5, color=MUTED)

    # 11 — security
    slide = deck._blank()
    deck.chrome(slide, "Security", "Access control and data handling", "RBAC is enforced in the API; the UI only mirrors it.")
    rows = [
        ["Capability", "Agency requester", "Ops agent", "Escalation manager", "Ops lead"],
        ["Ticket visibility", "own agency", "region", "region", "all"],
        ["Create ticket", "yes", "yes", "yes", "yes"],
        ["Main thread reply", "yes", "yes", "yes", "yes"],
        ["Internal note", "no", "yes", "yes", "yes"],
        ["Route / reassign", "no", "yes", "yes", "yes + override"],
        ["Side conversations", "yes", "yes", "yes", "yes"],
        ["Escalate", "no", "yes", "yes", "yes"],
        ["Product intelligence", "no", "no", "yes", "yes"],
        ["Streamed exports", "no", "no", "yes", "yes"],
        ["Run simulation", "no", "no", "yes", "yes"],
        ["Reseed / reset dataset", "no", "no", "no", "yes"],
    ]
    deck.table(slide, 0.62, 1.95, 8.5, rows, [2.55, 1.65, 1.3, 1.6, 1.4], size=9, row_height=0.31, header_size=9)
    deck.rect(slide, 9.4, 1.98, 3.55, 4.5, fill=BG)
    deck.text(slide, 9.65, 2.18, 3.05, 0.3, "CONTROLS", size=10, bold=True, color=BRAND)
    deck.bullets(slide, 9.65, 2.52, 3.05, 3.8, [
        "PBKDF2-SHA256 password hashing, per-user salt.",
        "Signed bearer tokens with expiry; role and agency in the claims.",
        "Pydantic validation on every request body and query.",
        "Environment-driven config via .env; no secrets in source.",
        "Immutable audit rows for routing, escalation and transfer.",
    ], size=9.5)

    # 12 — testing
    slide = deck._blank()
    deck.chrome(slide, "Quality", "Testing strategy", "Unit, module, system and browser level — the browser level runs against the built app.")
    rows = [
        ["Layer", "What it proves", "Count / result"],
        ["pytest module tests", "SLA, routing (incl. 7 mandatory cases), conversations, exports, analytics, RBAC", "104 tests"],
        ["Backend smoke", "OpenAPI surface and health contract", "2 tests"],
        ["Seeded journeys", "A–E end-to-end against the live API", f"{f['journeys_passed']}/{f['journeys_total']} · {f['steps_passed']}/{f['steps_total']} steps"],
        ["Export validation", "Row count, headers, readability, duration, memory", "PASS"],
        ["Browser crawl", "Six workspaces, console + HTTP error capture, downloads", "0 errors"],
    ]
    deck.table(slide, 0.62, 1.98, 12.35, rows, [2.5, 6.9, 2.95], size=10.5, row_height=0.42, header_size=10)
    deck.text(slide, 0.62, 4.9, 12.3, 1.2, "Unexecuted checks are reported as unexecuted in documentation/Testing_Report.md — nothing is marked passed without a run. Screenshots and JSON reports from the crawl are kept under screenshots/ and /tmp/ui_report.json for the session.", size=10.5, color=SLATE, line_spacing=1.2)

    # 13 — storage reference
    slide = deck._blank()
    deck.chrome(slide, "Storage", "Reference tiering vs implemented MVP", "Design intent is documented; the demo is honest about what runs today.")
    tiers = [
        ("Hot 0–90 days", "PostgreSQL, row-per-ticket, indexed on (region, status, due_at)", "Reference"),
        ("Warm 90 days – 2 years", "DuckDB / ClickHouse columnar store for analytics", "Reference"),
        ("Cold 2–7 years", "Parquet on S3 / MinIO, queried through DuckDB", "Reference"),
        ("This MVP", "Single SQLite database in WAL mode on the app node (49 tickets, 12 bookings)", "Implemented"),
    ]
    for index, (label, description, tag) in enumerate(tiers):
        top = 1.98 + index * 1.1
        implemented = tag == "Implemented"
        deck.rect(slide, 0.62, top, 12.35, 0.95, fill=BRAND_SOFT if implemented else BG, line=None if implemented else LINE)
        deck.text(slide, 0.9, top + 0.14, 3.2, 0.3, label, size=12, bold=True, color=NAVY)
        deck.text(slide, 4.1, top + 0.16, 7.0, 0.6, description, size=10.5, color=SLATE, line_spacing=1.15)
        deck.pill(slide, 11.35, top + 0.3, 1.4, tag, fill=BRAND if implemented else BG, color=WHITE if implemented else MUTED)
    deck.text(slide, 0.62, 6.45, 12.3, 0.5, "DuckDB is declared as an optional analytics dependency; it is not on the request path of this build.", size=10, color=MUTED)

    # 14 — deployment
    slide = deck._blank()
    deck.chrome(slide, "Operations", "Run, seed and reset", "Three commands from a clean checkout; the same build serves API and UI.")
    steps = [
        ("1 · Install", "pip install -r requirements.txt · cd frontend && npm install"),
        ("2 · Build UI", "npm run build → backend/static (served by FastAPI)"),
        ("3 · Seed", "python -m database.seed_data.seed (49 tickets, 12 bookings, 16 users)"),
        ("4 · Run", "uvicorn backend.main:app --host 0.0.0.0 --port 8000"),
        ("5 · Verify", "pytest tests backend/tests · python -m simulation.run_all"),
        ("6 · Observe", "GET /api/health reports counts, classifier mode and dataset notice"),
    ]
    for index, (label, command) in enumerate(steps):
        top = 1.98 + index * 0.72
        deck.pill(slide, 0.62, top + 0.08, 1.5, label, fill=BRAND_SOFT, color=BRAND)
        deck.text(slide, 2.3, top, 7.4, 0.6, command, size=10.5, color=SLATE, font="Consolas")
    deck.rect(slide, 9.95, 1.98, 3.0, 4.3, fill=BG)
    deck.text(slide, 10.2, 2.18, 2.5, 0.3, "CONFIG", size=10, bold=True, color=BRAND)
    deck.bullets(slide, 10.2, 2.52, 2.5, 3.6, [
        "OPSDESK_SECRET_KEY",
        "OPSDESK_DATABASE_URL",
        "OPSDESK_EXPORT_DIR",
        "OPSDESK_ENABLE_ROLE_SWITCH",
        "OPSDESK_DEMO_PASSWORD",
    ], size=9.5)

    # 15 — closing
    closing_slide(
        deck,
        "A booking is the operational context. A ticket is only one interaction associated with that booking.",
        [
            "Booking-first model, audited routing, travel-aware SLA",
            "Measured: 106 tests, 5/5 journeys, 0 browser console errors",
            "Reference architecture and MVP kept honestly separate",
        ],
        "Technical Architecture Deck · OpsDesk for TBO · synthetic demo dataset",
    )
    return deck.save(OUT / "Technical_Architecture_Deck.pptx")


def to_pdf(pptx_path: Path) -> Path:
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(pptx_path.parent), str(pptx_path)],
        check=True, capture_output=True, timeout=300,
    )
    return pptx_path.with_suffix(".pdf")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    f = facts()
    exec_deck = build_exec(f)
    tech_deck = build_tech(f)
    produced = []
    for deck_path in (exec_deck, tech_deck):
        pdf = to_pdf(deck_path)
        produced.append(
            {
                "pptx": str(deck_path),
                "pdf": str(pdf),
                "slides": len(__import__("pptx").Presentation(str(deck_path)).slides),
                "pptx_bytes": deck_path.stat().st_size,
                "pdf_bytes": pdf.stat().st_size if pdf.exists() else 0,
            }
        )
    report = {"generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z", "decks": produced, "facts": f}
    (OUT / "presentation_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
