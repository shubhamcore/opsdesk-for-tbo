# OpsDesk — Acceptance Checklist

Every line was verified on this build. Evidence is a command, a file or a screen — not an assertion.
Items that were **not** run are marked `NOT RUN` and are never reported as passing.

Legend: ✅ verified · ⚠️ verified with a stated limitation · ❌ not run

---

## A. Platform

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| A1 | React + Vite + TS + Tailwind + Recharts + React Router front end | `frontend/package.json`, `npm run build` (`tsc -b` + Vite production build, clean) | ✅ |
| A2 | FastAPI + SQLAlchemy + Pydantic back end | `backend/main.py`, `pip install -r requirements.txt` | ✅ |
| A3 | SQLite WAL, Postgres-compatible models | `backend/database.py`, `documentation/Database_Schema.md` | ✅ |
| A4 | Single process serves API + SPA | `GET /` → 200 from `backend/static` | ✅ |
| A5 | scikit-learn TF-IDF + LogReg + CalibratedClassifierCV artefact | `ai_models/saved_models/intent_pipeline.joblib`, `mode: ML` in `/api/health` | ✅ |
| A6 | Health endpoint reports counts + classifier mode | `GET /api/health` | ✅ |
| A7 | Synthetic data labelled in UI, API and docs | `data_notice` in health + intelligence payload, sidebar + login footers | ✅ |

## B. Module 1 — intake & understanding

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| B1 | Eight canonical intents | `services/classifier.py::INTENT_LABELS` (8 keys), dashboard donut | ✅ |
| B2 | Stage A regex `TBOH-\d+`, auto-extract when the field is empty | Journey A step 4 → `extraction_source: DESCRIPTION` | ✅ |
| B3 | Stage B calibrated classification with confidence + reasoning | W2 classification card; `test_extraction.py` | ✅ |
| B4 | Stratified/template-disjoint held-out evaluation | `ai_models/evaluation/metrics.json` → 0.8958 / 0.8964, n=288 | ✅ |
| B5 | joblib save/load + rule fallback | `mode: ML`; removing the artefact yields `RULES` (asserted) | ✅ |
| B6 | Booking-first case graph via `ticket_links` | W2 graph panel, 348 links seeded, `test_case_graph.py` | ✅ |
| B7 | "Generate AI Case Brief" → 3 points from actual data only | `case_brief.points` length 3 + `sources`; journey A step 7 | ✅ |

## C. Module 2 — routing

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| C1 | Score = 35/25/25/15, max 100 | `/api/routing/formula`; `test_maximum_possible_score_is_one_hundred` | ✅ |
| C2 | Hard filters first (offline, capacity, shift, skill ≥ 4, regional eligibility) | comparator `excluded[]` with reasons; 6 routing tests | ✅ |
| C3 | Tie-break: score → lowest load → lowest id | `test_tie_break_prefers_lower_load_then_id` | ✅ |
| C4 | Persisted breakdown + immutable routing audit | `routing_audits` rows shown in W3 audit table | ✅ |
| C5 | Comparator UI | W3 comparator with per-term columns | ✅ |
| C6 | Manager override with audit | W3 override panel (Ops Lead only) → new audit row | ✅ |
| C7 | Candidate pool excludes management roles | `AGENT_ROLES = ("OPS_AGENT",)` + journey B regression | ✅ |

## D. Module 3 — conversations

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| D1 | Main thread with public replies and internal notes | W2 thread; internal note posted in the crawl | ✅ |
| D2 | Independent side conversations (supplier/finance/agency) | `side_conversations` + `side_messages`; W2 panel | ✅ |
| D3 | Immutable `explicit_recipients` | `recipients-1` chips; `explicit_recipients` JSON per conversation | ✅ |
| D4 | Transfer preserves conversation id, recipients, history | journey C + crawl verification panel (`recipients_unchanged: true`) | ✅ |
| D5 | Transfer recorded + verification shown | `ticket_transfers` row + UI verification box | ✅ |
| D6 | Suppliers never inherit new group recipients | `preserved_recipients` snapshot compared after the move | ✅ |

## E. Module 4 — SLA & escalation

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| E1 | Matrix CRITICAL 1h / HIGH 4h / MEDIUM 12h / LOW 24h | `/api/sla/matrix`; `test_sla.py` | ✅ |
| E2 | `EffectiveSLADueAt = MIN(PriorityDeadline, LCD−2h, CheckIn−4h)` | `governing_rule` per ticket; SLA panel breakdown | ✅ |
| E3 | Missing/expired travel dates handled safely, never zeroed | `missing_dates`, `expired_travel_deadline` flags + tests | ✅ |
| E4 | UTC storage + booking-local display | `TZDateTime` (rejects naive) + `check_in_local`/`lcd_local` | ✅ |
| E5 | Holiday flips at-risk 75 % → 50 % with recorded reason | `holiday_adjustment_applied`; `TCK-401` shows it | ✅ |
| E6 | HEALTHY / AT_RISK / BREACHED + live countdowns | W1 `sla-*` cells tick each second | ✅ |
| E7 | Escalate: reason, eligible EM, status, queue, ownership, escalated_by/at, immutable event, atomic | W2 modal → `ESCALATED`; `test_escalation.py` (8 tests) | ✅ |
| E8 | Dedicated EM interface | W4 war room rendered for the EM identity in the crawl | ✅ |

## F. Module 5 — product intelligence

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| F1 | Common intents, supplier complaints, weekly trends | W5 charts 11–13 | ✅ |
| F2 | Refund bottlenecks, inventory sync issues, regional performance | W5 panels + regional table | ✅ |
| F3 | Resolution-time distribution | W5 histogram | ✅ |
| F4 | Theme extraction | `/api/analytics/themes/refresh`; theme list | ✅ |
| F5 | ≥3 tickets sharing supplier/pattern → product bug suggestion with tickets, supplier, frequency, period, evidence, action | `/api/analytics/bug-suggestions` (5 suggestions; top Accor ×3) | ✅ |
| F6 | Local record creation only, no claimed Jira integration | `product_bugs` row + explicit UI/notice text | ✅ |

## G. Module 6 — governance exports

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| G1 | Filters (date, agency, region, status, intent, priority) | `ExportStreamRequest` schema + W5 filter controls | ✅ |
| G2 | CSV + JSONL | both formats supported and exercised | ✅ |
| G3 | "Generate and Stream 50,000 Rows" through a real `StreamingResponse` | crawl + benchmark: 50,000 rows received | ✅ |
| G4 | Server-side iterator, batch 5,000, memory-efficient | `OPSDESK_EXPORT_BATCH_SIZE=5000`; peak 8.9–33.6 MB | ✅ |
| G5 | Real download | crawl downloaded a non-empty file with the bearer token | ✅ |
| G6 | Job tracking + progress + error handling | `export_jobs` table, live byte progress, FAILED status path | ✅ |
| G7 | Report rows / duration / size / throughput / memory | W5 job table columns | ✅ |
| G8 | Storage-architecture doc separated from implemented tier | `documentation/Storage_Architecture.md` | ✅ |

## H. Workspaces

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| H1 | Exactly six workspaces | `NAV_ITEMS` (6), routes `/w1…/w6` | ✅ |
| H2 | W1 Ops Queue & SLA Command Center | crawl screenshot `01_w1_ops_queue.png` | ✅ |
| H3 | W2 Unified Ticket & Booking Case Workspace (3-pane) | `02_w2_case_workspace.png` | ✅ |
| H4 | W3 Routing & Agent Capacity Studio | `07_w3_routing_studio.png` | ✅ |
| H5 | W4 Escalation Manager War Room | `09_w4_war_room.png`, `18_w4_escalation_manager.png` | ✅ |
| H6 | W5 Product Intelligence & Governance Hub | `10…14` screenshots | ✅ |
| H7 | W6 OpsDesk Live Simulation Lab | `15_w6_simulation_lab.png`, `16_w6_journey_a.png` | ✅ |
| H8 | No disconnected pages | every workspace hits live endpoints; 0 HTTP errors in the crawl | ✅ |

## I. Seeded journeys

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| I1 | Journey A — Wanderlust/MEA/TBOH-778899/refund | 7/7 steps | ✅ |
| I2 | Journey B — Apex/APAC/Ananya 1/8 and why-not-FIFO | 6/6 steps | ✅ |
| I3 | Journey C — EuroWings/Hilton/transfer recipients persist | 6/6 steps | ✅ |
| I4 | Journey D — LCD 55 min, check-in 90 min, escalate TCK-401 | 8/8 steps | ✅ |
| I5 | Journey E — 25+ tickets, themes, bug suggestion, 50k export | 7/7 steps | ✅ |

## J. Visualisations

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| J1 | 12 required visualisations | 14 implemented, table in `Testing_Report.md#6` | ✅ |
| J2 | From real DB records | every series comes from an API payload | ✅ |
| J3 | Tooltips | all charts use Recharts tooltips | ✅ |
| J4 | Filters / date range | W1 filters; W5 window selector (7/30/90/365 days) | ✅ |

## K. Presentations

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| K1 | `scripts/generate_presentations.py` produces both decks | script runs end-to-end | ✅ |
| K2 | Executive deck 10–12 slides ending on the required line | 12 slides, closing statement exact | ✅ |
| K3 | Technical deck 12–15 slides | 15 slides | ✅ |
| K4 | PDF via LibreOffice headless | both PDFs produced (`soffice --convert-to pdf`) | ✅ |
| K5 | 16:9, light, editable | 13.333×7.5 in, native shapes/text, no flattened text | ✅ |
| K6 | Authentic screenshots | `presentations/assets/` 16:9 crops of `screenshots/` | ✅ |
| K7 | No credentials in decks | scanned: no password or token text | ✅ |

## L. Videos

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| L1 | `scripts/run_Automated_Demo.py` records deterministically | Playwright + retries + networkidle | ✅ |
| L2 | Explainer 90–120 s, 7 scenes | `Explainer.mp4` = 104.96 s, 7 scenes | ✅ |
| L3 | Demo 3–5 min, 6 segments | `Product_Demo.mp4` = 207 s, 6 segments | ✅ |
| L4 | `Explainer.srt`, `Product_Demo.srt` | both written, cue times derived from the real cuts | ✅ |
| L5 | Storyboard, voiceover and demo scripts | 4 markdown files in `videos/` | ✅ |
| L6 | FFmpeg assembly | H.264 1440×900 25 fps validated with `ffprobe` | ✅ |
| L7 | Stable `data-testid` selectors | 60+ testids used by the recorder and the crawler | ✅ |

## M. Testing & security

| # | Requirement | How verified | Status |
| --- | --- | --- | --- |
| M1 | Full module + system tests | `pytest tests backend/tests -q` → 106 passed | ✅ |
| M2 | 7 mandatory routing unit tests | listed by name in `Testing_Report.md#1` | ✅ |
| M3 | Export validation (rows, headers, integrity, readability, duration, memory) | `Test` + benchmark + UI validation panel | ✅ |
| M4 | Testing report with Expected/Actual/Pass-Fail | `documentation/Testing_Report.md` | ✅ |
| M5 | Never marks unexecuted tests as passed | §7 "Not executed" table | ✅ |
| M6 | Password hashing | PBKDF2-SHA256, `services` hashing helpers | ✅ |
| M7 | Backend-enforced RBAC | `require_roles` on every router; crawl proves nav + API agreement | ✅ |
| M8 | Input validation | Pydantic schemas with length/format constraints; 422 covered by tests | ✅ |
| M9 | Env vars, transactions, immutable audits | `.env.example`, single-commit services, append-only audit tables | ✅ |
| M10 | No credentials in source | demo password is a synthetic seed value, overridable, documented in README | ⚠️ |

## N. Documentation

| # | Requirement | Status |
| --- | --- | --- |
| N1 | README | ✅ |
| N2 | Architecture | ✅ |
| N3 | API documentation (49 paths) | ✅ |
| N4 | Database schema (15 tables) | ✅ |
| N5 | Testing report | ✅ |
| N6 | Deployment guide | ✅ |
| N7 | Storage architecture | ✅ |
| N8 | Final summary with 10 items | ✅ (`documentation/Final_Summary.md`) |

## O. Not verified

| Item | Why | Status |
| --- | --- | --- |
| PostgreSQL deployment | no server available here | ❌ NOT RUN |
| DuckDB / ClickHouse warm tier | design only | ❌ NOT RUN |
| Production-scale load test | demo dataset only | ❌ NOT RUN |
| Firefox / WebKit | only Chromium installed | ❌ NOT RUN |
| Mobile viewports | desktop console target | ❌ NOT RUN |
| WCAG / screen-reader audit | no a11y tooling executed | ❌ NOT RUN |
| Real supplier APIs, email, Jira | out of scope by design | N/A |


---

## v2.1 additions (all executed on this build)

| # | Requirement | Evidence | Status |
| --- | --- | --- | --- |
| A-1 | More AI agents, genuinely wired to the product | 8 specialist agents in `backend/agents/`, exposed at `/api/agents/*` and in the W2 Agent mesh panel | ✅ |
| A-2 | Agents cannot fabricate or mutate | Read-only tool allow-list; `test_swarm_is_side_effect_free`; evidence-per-finding assertion | ✅ |
| A-3 | Agent work is auditable | `agent_runs` row per review with per-agent trace, tool calls, plan, actor, duration | ✅ |
| A-4 | Failures are contained | Forced agent exception → `ERROR` + `PARTIAL`, HTTP 200, other agents complete | ✅ |
| A-5 | Production probes and metrics | `/api/ready`, `/api/metrics` (Prometheus), request-id tracing, security headers | ✅ |
| A-6 | Abuse control | Auth rate limit 429 + `Retry-After`, verified in tests | ✅ |
| A-7 | Deployable artifact | `Dockerfile`, `docker-compose.yml` (SQLite + Postgres profile), `Makefile`, CI workflow, backup script | ✅ |
| A-8 | Documentation updated | `Agent_Architecture.md`, README agent section, Architecture §9–10, API §agents, Testing Report v2.1, Deployment Guide | ✅ |
| A-9 | Suite still green | `pytest tests backend/tests -q` → 121 passed | ✅ |
| A-10 | UI still verified in a sandboxed frame | Agent mesh run inside `sandbox="allow-scripts"` iframe: 8 cards, 5 plan actions, 0 console errors | ✅ |
