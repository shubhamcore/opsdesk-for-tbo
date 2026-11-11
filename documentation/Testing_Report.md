# OpsDesk — Testing Report

Environment: Python 3.13.16 · Node 20.20.2 · SQLite 3 (WAL) · Chromium (Playwright 1248) ·
Linux 6.1 · 2 vCPU / 1.9 GiB.

Everything below was **executed on this build**. Checks that were not run are listed in
[§7 Not executed](#7-not-executed) and are *not* marked as passing anywhere.

---

## 1. Automated test suite

Command: `python -m pytest tests backend/tests -q`
Result: **121 passed, 0 failed** (deprecation warnings only, no product impact).

| Module | Tests | What it proves | Result |
| --- | --- | --- | --- |
| `tests/test_sla.py` | 15 | Matrix, `MIN(priority, LCD−2h, check-in−4h)`, holiday threshold, missing/expired dates, UTC handling, countdown states | PASS |
| `tests/test_routing.py` | 14 | The 7 mandatory routing cases + scoring arithmetic, exclusions, eligibility, tie-break | PASS |
| `tests/test_extraction.py` | 11 | `TBOH-\d+` extraction, field-vs-description precedence, ambiguity, classification fallback | PASS |
| `tests/test_case_graph.py` | 17 | Booking-first linking, case brief (exactly 3 points + sources), detail payload, overrides | PASS |
| `tests/test_side_conversations.py` | 7 | Explicit recipients, isolation from the main thread, transfer preservation, recipient validation | PASS |
| `tests/test_escalation.py` | 8 | Reason validation, manager selection, status/queue/ownership change, immutable event, history | PASS |
| `tests/test_analytics_exports.py` | 12 | Analytics aggregates, bug suggestions, export streaming, job metrics, file validation | PASS |
| `tests/test_api_auth.py` | 12 | Login, token expiry, RBAC per role, cross-agency access denial, validation errors | PASS |
| `tests/test_db_integrity.py` | 8 | Seed fixture guarantees the journeys depend on, FK integrity, aware datetimes | PASS |
| `tests/test_agents.py` | 8 | Agent registry (8 agents, 17 tool bindings), grounded plan, evidence-per-finding, side-effect-free runs, RBAC, resolved-case 409, telemetry, failure containment | PASS |
| `tests/test_production_hardening.py` | 7 | `/api/ready`, Prometheus metrics match the DB, request-id tracing, security headers, 429 + `Retry-After`, limiter scoped to auth paths, hot indexes present | PASS |
| `backend/tests/test_backend_smoke.py` | 2 | OpenAPI surface (56 paths), `/api/health` contract | PASS |

### The seven mandatory routing tests

| # | Test | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| 1 | `test_qualified_region_matched_agent_scores_higher` | region-matched qualified agent outranks a non-matched one | matched agent scores strictly higher | PASS |
| 2 | `test_offline_agent_is_excluded` | offline agent never appears in candidates | excluded with reason "offline" | PASS |
| 3 | `test_agent_at_max_capacity_is_excluded` | agent at `active_load == max_capacity` is excluded | excluded with "at capacity" | PASS |
| 4 | `test_critical_tickets_require_senior_agents` | CRITICAL requires SkillRank ≥ 4 | skill 3 excluded with the threshold reason | PASS |
| 5 | `test_regional_eligibility_restriction` | only eligible regions are scored | APAC ticket excludes non-eligible regions | PASS |
| 6 | `test_tie_break_prefers_lower_load_then_id` | equal score → lower load → lower id | deterministic winner | PASS |
| 7 | `test_ineligible_agent_never_receives_ticket_even_with_high_score` | filters precede scoring | high-scoring but ineligible agent is not assigned | PASS |

## 2. Module-level verification (direct assertions)

| Check | Expected | Actual | Result |
| --- | --- | --- | --- |
| Extraction when the booking field is empty | `TBOH-778899` from the description, source `DESCRIPTION` | same | PASS |
| Classification of a refund complaint | `REFUND_DELAY`, source `ML`, calibrated confidence | `REFUND_DELAY` @ 0.87 (ML) | PASS |
| Case brief | exactly 3 points with `sources` | 3 points, sources list tickets/messages/conversations | PASS |
| Routing decision payload | score + all four components + exclusions + audit id | present for every route call | PASS |
| Candidate pool | `OPS_AGENT` only | management roles never scored | PASS |
| Transfer verification | `recipients_unchanged: true`, conversation count preserved | true, 1 conversation / 1 recipient | PASS |
| Escalation | status `ESCALATED`, queue `ESCALATION_MANAGER`, EM owner, reason, timestamp | all present, atomic | PASS |
| Export validation | row count in file equals requested | 50,000 = 50,000 | PASS |
| Model load | `joblib` artefact loads; `mode: ML` | ML, trained 2026-11-09T18:27:46Z | PASS |
| Model fallback | removing the artefact yields rule mode, no crash | `RULES` mode returned | PASS |

## 3. End-to-end journeys (live API)

Command: `python -m simulation.run_all`
Result: **5/5 journeys passed · 34/34 steps** → `benchmark_results/journey_results.json`

| Journey | Scenario | Steps | Result |
| --- | --- | --- | --- |
| A | Wanderlust (MEA) refund on `TBOH-778899`, booking field empty → extraction → `REFUND_DELAY` → 3 related tickets → 3-point brief | 7/7 | PASS |
| B | Apex (APAC) voucher ticket → comparator 5 eligible / 4 excluded → Ananya Sharma 94.375/100, load 1/8 → audit row → why-not-FIFO explanation | 6/6 | PASS |
| C | EuroWings (EU) supplier thread to `groups@hilton-paris.com`, transfer `EU-TRIAGE → EU-SENIOR-OPS`, recipients verified unchanged | 6/6 | PASS |
| D | LCD 55 min / check-in 90 min tickets, holiday-adjusted at-risk, escalate `TCK-401` to the EU manager, escalation queue | 8/8 | PASS |
| E | 25+ background tickets → themes → bug suggestion (Accor `INVENTORY_RATE_SYNC_BUG` ×3) → 50,000-row export → validation | 7/7 | PASS |

## 4. Export integrity

Requested 50,000 rows, CSV, `source: SYNTHETIC_BENCHMARK`.

| Check | Expected | Actual | Result |
| --- | --- | --- | --- |
| Row count in file | 50,000 | 50,000 | PASS |
| Header / column count | 25 columns | 25 | PASS |
| File size | consistent with rows | 16.31 MB | PASS |
| Readability | file parses end-to-end | parsed with pandas, no truncation | PASS |
| Server duration | measured | ≈1.2–1.3 s | PASS |
| Throughput | measured | ≈38,000–42,000 rows/s | PASS |
| Peak memory | flat, not proportional to rows | 8.9–33.6 MB sampled across runs | PASS |
| Client-side progress | reflects received bytes | 50,000/50,000 with live byte counter | PASS |
| Download | file served from disk with the bearer token | downloaded, size > 0 | PASS |
| Interrupted export | job marked FAILED with the error | covered by `test_analytics_exports.py` | PASS |

## 5. Browser verification

Command: `python scripts/ui_crawl.py` (real Chromium against the built SPA)
Result: **19 screenshots · 0 console errors · 0 HTTP ≥ 400 · 0 missing test ids**.

| Workspace | Screen checked | Assertions | Result |
| --- | --- | --- | --- |
| Login | identity list + form sign-in | lands on `/w1` with an Ops Lead session | PASS |
| W1 | queue, KPIs, four charts, filters | `kpi-*`, `chart-*`, ticket rows, SLA cells render | PASS |
| W2 | three-pane case workspace | classification, case brief, thread, booking context, SLA panel, side conversations, case graph | PASS |
| W2 | main thread | internal note posted, appears in the thread | PASS |
| W2 | supplier conversation + transfer | `recipients-1` chips present; transfer shows `recipients_unchanged` verification | PASS |
| W2 | escalation modal | reason validated, submit enabled only past the minimum length | PASS |
| W3 | routing studio | agent board, formula, comparator, excluded list, audit table; route writes an audit row | PASS |
| W4 | war room | `em-ticket-*` rows, managers on duty, trend and deadline charts | PASS |
| W5 | insights | 4 charts + regional table + themes from live aggregates | PASS |
| W5 | bug suggestions | suggestions with evidence | PASS |
| W5 | export | 50,000 rows streamed, validated, downloaded | PASS |
| W6 | simulation lab | journey cards, run A from the UI | PASS |
| RBAC | agency requester | routing workspace disappears from navigation | PASS |
| RBAC | escalation manager | war room renders with manager identity | PASS |

Probes used (stable selectors, no pixel matching): `data-testid` attributes on every interactive element,
`wait_for_load_state("networkidle")` plus explicit selector waits, and a 3-attempt retry wrapper in the
video recorder.

## 6. Visualisation audit (12 required, all DB-backed)

| # | Visualisation | Workspace | Source | Result |
| --- | --- | --- | --- | --- |
| 1 | SLA state mix (donut) | W1 | `/api/analytics/queue` | PASS |
| 2 | Weekly ticket volume (line) | W1 | `weekly_volume` | PASS |
| 3 | SLA state by region (stacked bars) | W1 | queue snapshot | PASS |
| 4 | Tickets by intent (horizontal bars) | W1 | `by_intent` | PASS |
| 5 | Calibrated class scores (bars) | W2 | ticket `classification.scores` | PASS |
| 6 | Reference score by agent (ranked bars) | W3 | `/api/routing/board` | PASS |
| 7 | Load vs score (bubble scatter) | W3 | board + skill rank | PASS |
| 8 | Escalations per week (line) | W4 | `/api/escalations/trend` | PASS |
| 9 | SLA state by region (stacked) | W4 | escalation queue | PASS |
| 10 | Deadline pressure (hours to due) | W4 | `/api/escalations/deadlines` | PASS |
| 11 | Intent distribution (donut) | W5 | `/api/analytics/product-intelligence` | PASS |
| 12 | Supplier complaint volume (bars) | W5 | same | PASS |
| 13 | Weekly trend (line) | W5 | same | PASS |
| 14 | Resolution-time distribution (histogram) | W5 | same | PASS |

All charts have hover tooltips; W1/W5 expose date-range (window) and category filters that re-query the API.

### v2.1 — agent mesh and production hardening (executed)

| # | Expected | Actual | Pass/Fail |
| --- | --- | --- | --- |
| AG1 | Registry advertises every agent with a non-empty tool allow-list and no external model | 8 agents, 17 tool bindings, `external_model: null` on all | **PASS** |
| AG2 | A review produces a prioritised plan grounded in API numbers | `TCK-101` → 5 actions; `sla_risk.evidence.state` == `/api/tickets` SLA state; `intake.evidence.intent` == stored intent | **PASS** |
| AG3 | A review never mutates the case | Message count, assignee, status, queue and escalation flag unchanged after a run | **PASS** |
| AG4 | A broken agent is contained | `qa` forced to raise → that entry `ERROR`, run `PARTIAL`, other 7 complete, HTTP 200 | **PASS** |
| AG5 | Requesters cannot invoke the swarm | `AGENCY_REQUESTER` → 403 | **PASS** |
| AG6 | Review latency is usable interactively | 24–56 ms per eight-agent review on the seeded dataset | **PASS** |
| OP1 | Readiness reflects real dependencies | `/api/ready` → `ready`, DB `ok`, classifier `ML`, export dir present | **PASS** |
| OP2 | Metrics are measured, not hardcoded | `opsdesk_tickets_total` equals the `/api/tickets` count in the same process | **PASS** |
| OP3 | Tracing propagates and generates ids | Inbound `X-Request-ID` echoed; absent one generated (16 hex) | **PASS** |
| OP4 | Auth limiter engages and is scoped | 2 auth calls allowed, 3rd → 429 with `Retry-After`; ordinary API calls unaffected | **PASS** |
| OP5 | Hot indexes exist | `ix_tickets_status_queue`, `ix_tickets_assigned`, `ix_agent_runs_ticket`, `ix_messages_ticket_created` in `sqlite_master` | **PASS** |
| OP5b | Security headers do not break embedding | CSP present without `frame-ancestors`; app boots and signs in inside a `sandbox="allow-scripts"` iframe (0 console errors) | **PASS** |

## 7. Not executed

These were **not** run, and no claim is made that they pass:

| Area | Why not run | Status |
| --- | --- | --- |
| PostgreSQL migration test | No Postgres server in this environment; DDL is portable but unproven here | NOT RUN |
| DuckDB warm-tier analytics | Declared dependency only; no warm tier implemented | NOT RUN |
| Load test at production scale (10k+ tickets, concurrent users) | Single-node demo dataset of 49 tickets | NOT RUN |
| Cross-browser (Firefox/WebKit) | Only Chromium is installed | NOT RUN |
| Mobile/responsive breakpoints below 1280 px | Desktop ops console is the target; layouts are fluid but unverified on phones | NOT RUN |
| Accessibility audit (WCAG/screen reader) | No automated a11y tooling run; semantic HTML and labels only | NOT RUN |
| Real supplier API / email delivery | Not implemented by design | N/A |
| Jira or other tracker integration | Not implemented by design | N/A |

### Sandboxed-iframe boot (executed 2026-11-09, after the fix below)

| # | Expected | Actual | Pass/Fail |
| --- | --- | --- | --- |
| S1 | App mounts inside `sandbox="allow-scripts"` iframe | Before fix: `SecurityError: Failed to read the 'localStorage' property` and an empty `#root`. After the `readKey`/`writeKey` shim: `#root` renders 18,858 chars, 0 console errors | **PASS** (after fix) |
| S2 | One-click demo sign-in works in that frame | `demo-login-OPS_LEAD` → `/w1`, then W1–W6 all render (42 queue rows, 49 cases, charts on W1/W3/W4/W5) | **PASS** |
| S3 | No API or console failures in the frame | 0 HTTP ≥ 400 on `/api/*`, 0 console errors across W1–W6 | **PASS** |

Known trade-off, not a defect: inside a sandboxed frame the bearer token lives in memory, so a hard
reload returns to the login screen instead of restoring the session.

## 8. How to reproduce

```bash
python -m pytest tests backend/tests -q
python -m simulation.run_all
python -m scripts.run_benchmark
python scripts/ui_crawl.py            # needs the server on :8000 and Playwright chromium
```

Artifacts: `benchmark_results/journey_results.json`, `benchmark_results/benchmark_report.{json,md}`,
`screenshots/*.png`, `/tmp/ui_report.json` (crawl log for the current session).
