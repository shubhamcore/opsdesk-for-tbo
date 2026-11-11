# OpsDesk for TBO — Phase 1: Architecture & Implementation Plan

**Version:** 2.0 · **Date:** 2026-11-09 · **Track:** Track 1 — Zendesk Replacement

Core product thesis:

> **A booking is the operational context. A ticket is only one interaction associated with that booking.**

---

## 1. Environment audit (measured, not assumed)

| Component | Version | Notes |
|---|---|---|
| Python | 3.13.16 | FastAPI 0.162.2, SQLAlchemy 2.1.8, Pydantic 2.14.2 |
| scikit-learn | 1.6.1 | `CalibratedClassifierCV(estimator=...)` API (pre-1.6 name `base_estimator` avoided) |
| pandas / numpy | 2.2.3 / 2.3.5 | |
| DuckDB | 2.0.0 | analytical tier queries |
| SQLite | 3.46.1 | WAL mode, foreign keys ON |
| Node / npm | 20.20.2 / 10.8.2 | React 18 + Vite 5 + TS + Tailwind 3.4 |
| LibreOffice | 25.2.3 | headless PPTX→PDF |
| FFmpeg | 7.1.5 | webm→mp4 |
| Playwright + Chromium | 1248 | recording + screenshots |
| CPU / RAM | 2 vCPU / 1.9 GB | drives streaming & batching decisions |

---

## 2. Six problems → six architectural decisions

| # | Problem | Zendesk limitation | OpsDesk architecture decision |
|---|---|---|---|
| 1 | Context & linkage | Isolated ticket IDs | `bookings` is the graph root; `ticket_links` materialises inferred relationships with confidence + reason |
| 2 | Routing | FIFO / static rules | Deterministic 4-factor additive score (0–100) + hard eligibility filters + immutable `routing_audits` |
| 3 | Supplier comms | Conversations orphaned on transfer | `side_conversations.explicit_recipients` is immutable JSON; transfer never rewrites it |
| 4 | SLA | Static priority timers | `EffectiveSLADueAt = MIN(priority, LCD−2h, checkin−4h)`, UTC storage, booking-local display |
| 5 | Product feedback | Issues buried in tickets | Intent tags + keyword theme clustering → `product_bugs` proposals with evidence |
| 6 | Data access | Export ceilings / archive cost | True `StreamingResponse` generator, 5 000-row cursor batches, hot/warm/cold strategy |

---

## 3. System architecture

```
┌──────────────────────────── Browser (React 18 + Vite + TS + Tailwind + Recharts) ────────────────────────────┐
│  Role switcher (Agency Requester · Ops Agent · Escalation Manager · Ops Lead)                                  │
│  W1 Queue & SLA   W2 Ticket/Booking Case   W3 Routing Studio   W4 EM War Room   W5 Product & Governance   W6 Lab │
└───────────────────────────────────────┬──────────────────────────────────────────────────────────────────────┘
                                        │ fetch/JSON + Bearer token (RBAC enforced server-side)
┌───────────────────────────────────────▼──────────────────────────────────────────────────────────────────────┐
│ FastAPI app (single process)                                                                                  │
│  api/auth · api/tickets · api/bookings · api/routing · api/sla · api/side_conversations · api/escalations      │
│  api/analytics · api/product_intel · api/exports · api/simulation · api/agents                                 │
│                                                                                                               │
│  services/                                                                                                    │
│   extraction.py   TBOH-\d+ / agency / supplier / hotel / date regex + validation                              │
│   classifier.py   A: deterministic · B: calibrated ML pipeline · C: rule fallback                             │
│   linking.py      case-graph inference (same TBOH, agency+intent ≤30d, duplicate refund/amendment)            │
│   routing.py      eligibility filters → score → sort → assign → audit                                         │
│   sla.py          travel-aware deadline resolution + holiday threshold shift                                  │
│   escalation.py   transactional state machine + ownership transfer                                            │
│   analytics.py    DuckDB/pandas aggregations over live tables                                                 │
│   exports.py      streaming CSV/JSONL generator (batched server-side cursor)                                   │
├───────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ SQLAlchemy 2.x ORM → SQLite (WAL)  ·  joblib model artifacts in ai_models/saved_models                         │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Why one process:** the MVP is judged on correctness and reproducibility, not on distributed infra. Static SPA is served by FastAPI from `backend/static`, so `uvicorn` alone runs the whole product with zero Node dependency at runtime.

---

## 4. Database schema (14 required tables + 2 supporting)

```
agencies ──< bookings ──< tickets ──< ticket_links (self-referencing M:N)
   │                          ├──< messages
   │                          ├──< side_conversations ──< side_messages
   │                          ├──< routing_audits        (immutable)
   │                          ├──< escalation_records    (immutable)
   │                          ├──< activity_timeline     (immutable, append-only)
   │                          └──< ticket_transfers      (supporting)
   └──< users (agents/EMs; agency_id for requesters)

theme_tags, product_bugs, export_jobs  (standalone analytical/governance)
```

Key constraints: `bookings.tboh_id` UNIQUE · `tickets.ticket_number` UNIQUE · `ticket_links (source,target,link_type)` UNIQUE · `side_conversations.explicit_recipients` NOT NULL JSON array · FKs with `ON DELETE RESTRICT` semantics emulated by soft delete (`is_deleted`).

UTC everywhere (`DateTime(timezone=True)`), rendered per booking timezone (`Asia/Dubai`, `Asia/Singapore`, `Europe/Paris`, `America/New_York`, `Asia/Kolkata`).

---

## 5. AI classification pipeline (Module 1)

```
title + description ──► TfidfVectorizer(ngram=(1,2), max_features=1500, sublinear_tf=True)
                                    │
                                    ├──► ColumnTransformer ──► CalibratedClassifierCV(
hours_to_checkin,                   │        (FeatureUnion)        LogisticRegression(class_weight='balanced'),
hours_to_lcd,                       │                              method='sigmoid', cv=3)
prior_tboh_ticket_count ──► StandardScaler()
```

* Numeric features are computed **independently** of the text (from booking context at request time).
* Stratified 80/20 held-out split, fixed `random_state=42`; metrics reported verbatim from `classification_report` (no invented numbers).
* Training corpus is **explicitly synthetic** (`ai_models/training/synthetic_corpus.py`), template-generated with paraphrase variation and label noise in the held-out set only via unseen phrasings.
* Persistence: `joblib.dump` → `ai_models/saved_models/intent_pipeline.joblib` + `metrics.json`.
* Load at startup; **rule-based fallback** (`classifier.RuleBasedClassifier`) if artifact is missing/corrupt — surfaced in `/api/health` as `classifier_mode: ML|FALLBACK`.
* Stage A extraction runs first and always wins on identifiers: `TBOH-\d+` (empty field → auto-extract from description, with `extraction_source=DESCRIPTION`).

8 canonical intents: REFUND_DELAY, CANCELLATION_LCD_WAIVER, VOUCHER_CONFIRMATION_ISSUE, AMENDMENT_NAME_DATE, INVENTORY_RATE_SYNC_BUG, SPECIAL_REQUEST, SUPPLIER_OVERBOOKING_RELOCATION, BILLING_INVOICE_DISPUTE.

---

## 6. Routing mathematics (Module 2)

```
RouteScore(a,t) = 35·RegionMatch + 25·ShiftMatch + 25·(SkillRank/5)·UrgencyWeight
                + 15·(1 − ActiveLoad/MaxCapacity)
```

All terms non-negative ⇒ score ∈ [0, 100] (`35+25+25+15`). Hard filters applied **before** scoring:

1. `is_online` false → excluded
2. `ActiveLoad >= MaxCapacity` → excluded (so division-by-zero cannot occur; `MaxCapacity==0` also excluded)
3. outside shift window (agent-local time) → excluded
4. CRITICAL/AT_RISK urgency ⇒ `SkillRank >= 4`
5. regional eligibility restriction (`users.region` ∈ allowed set)

Tie-break: lower ActiveLoad → lower agent id. Decision persisted in `routing_audits.candidate_scores_json` (every candidate, every component) + append-only `activity_timeline` event.

---

## 7. SLA algorithm (Module 4)

```
priorityDue  = created_at + {CRITICAL:1h, HIGH:4h, MEDIUM:12h, LOW:24h}
lcdDue       = lcd − 2h          (only if lcd present & future-or-equal)
checkinDue   = check_in − 4h     (only if check_in present & future-or-equal)
effectiveDue = MIN(all present candidates)
```

Missing dates are **skipped, never coerced to 0**. Expired travel deadlines produce `BREACHED` with `expired_travel_deadline=true` reason. State: elapsed ratio `r = (now−created)/(due−created)`; `BREACHED` if `r ≥ 1`; `AT_RISK` if `r ≥ threshold` where threshold = **0.75**, or **0.50** when `regional_holiday_flag` (reason recorded + returned to UI).

---

## 8. Six workspaces (no page sprawl)

| WS | Name | Panels |
|---|---|---|
| W1 | Ops Queue & SLA Command Center | KPI strip, live SLA table + countdown, region/intent/priority filters, volume charts, agent workload |
| W2 | Unified Ticket & Booking Case Workspace | 3-pane: navigation · thread/classification/AI brief · booking context, graph, side conversations, transfer |
| W3 | Routing & Capacity Studio | agent board, score comparator, formula breakdown, audit log, manual override |
| W4 | Escalation War Room | EM queue, travel urgency, handover, escalation timeline |
| W5 | Product Intelligence & Governance | themes, supplier complaints, bug suggestions, trends, export bench, storage tiers |
| W6 | Simulation Lab | seed/reset, start/pause/step/fast-forward, timeline, expected vs actual |

Shared design system: light theme, white/`#F6F8FB` surfaces, `#0F2540` navy text, `#2563EB` primary, emerald/amber/rose status, Inter-style system font stack, 8-pt spacing grid, one Recharts wrapper.

---

## 9. Seed data & five journeys

Synthetic (clearly labelled) — 4 agencies, 8 agents/EMs/lead, 6 bookings incl. the journey fixtures, 40+ tickets (25 background for Journey E: 11 inventory, 8 refund, 6 special-request), linked cases for TBOH-778899, TCK-401 LCD+55min / TCK-402 check-in+90min, 2 pre-escalated tickets, 1 supplier side conversation on TCK-301 (`groups@hilton-paris.com`).

Seeding is **relative to run time** so travel deadlines are always live. `POST /api/simulation/seed` and `/reset` are idempotent.

---

## 10. Build order & verification gates

| Phase | Deliverable | Gate |
|---|---|---|
| 1 | this plan + API contract + schema | docs committed |
| 2 | DB + services + routers | pytest module suite green |
| 3 | 6 workspaces wired to real APIs | `npm run build` clean, no mock data |
| 4 | trained model + 5 journeys | journey A–E pass via HTTP |
| 5 | full test run, 50k export benchmark, screenshots | measured results JSON |
| 6 | PPTX/PDF + Playwright videos + SRT | files open / play verified |
| 7 | docs, acceptance checklist | every box evidence-backed |

**Non-negotiables:** no fabricated accuracy, no hardcoded confidence, no fake export completion, no claimed integrations, no untested pass marks.
