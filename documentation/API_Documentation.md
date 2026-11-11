# OpsDesk — API Documentation

Base URL: `http://localhost:8000` · OpenAPI: `GET /docs`, `GET /openapi.json`

Authentication: `Authorization: Bearer <access_token>` on every endpoint except `/api/health`,
`/api/auth/login`, `/api/auth/demo-login` and `/api/auth/identities`.

Errors are FastAPI-standard: `{"detail": "..."}` with 400/401/403/404/409/422/503 as appropriate.
`422` bodies from Pydantic requests contain the field path in `detail[].loc`.

**56 paths** are exposed; all are listed below.

| Role | Code |
| --- | --- |
| Agency requester | `AGENCY_REQUESTER` |
| Ops agent | `OPS_AGENT` |
| Escalation manager | `ESCALATION_MANAGER` |
| Ops lead | `OPS_LEAD` |

---

### Agent mesh (v2.1)

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| GET | `/api/agents/registry` | OPS_AGENT, ESCALATION_MANAGER, OPS_LEAD | Agent catalogue with each agent's tool allow-list; `external_model: null` |
| POST | `/api/agents/cases/{ticket_ref}/run` | OPS_AGENT, ESCALATION_MANAGER, OPS_LEAD | Run the eight-agent review; 409 if the case is resolved; persists to `agent_runs` |
| GET | `/api/agents/runs` | OPS roles | Review history, optional `ticket_id`, `limit` (1–100) |
| GET | `/api/agents/runs/{run_uuid}` | OPS roles | One archived trace (agent results + plan) |
| GET | `/api/agents/telemetry` | OPS roles | Per-agent runs, success rate, average duration, tool-call counts |

`POST …/run` response shape (abridged):

```json
{
  "run_uuid": "AGT-B8ECF70F4A2C",
  "status": "COMPLETED",
  "agent_count": 8,
  "overall_confidence": 0.8132,
  "plan": [{"priority": "P0", "action": "Escalate to Vikram Rao with a written reason",
            "rationale": "…", "source_agent": "escalation"}],
  "agents": [{"agent": "sla_risk", "status": "ATTENTION", "summary": "…",
              "tool_calls": [{"tool": "sla_state", "ok": true, "duration_ms": 0.4}],
              "evidence": {"state": "BREACHED", "governing_rule": "PRIORITY_SLA"}}],
  "duration_ms": 56.03
}
```

### Operations (v2.1)

| Method | Path | Roles | Purpose |
| --- | --- | --- | --- |
| GET | `/api/ready` | anonymous | Readiness: DB round-trip, classifier mode, export directory. 200 `ready` / 503 `degraded` |
| GET | `/api/metrics` | anonymous | Prometheus exposition format: counters per route and status class, latency quantiles, rate-limit counter, live entity gauges |

Every response also carries `X-Request-ID` and `X-Response-Time-Ms`; the same request id appears
in the JSON access log line.


## 1. Platform

### `GET /api/health` — public
```json
{
  "status": "ok", "version": "2.0.0", "database": "ok",
  "counts": {"tickets": 49, "bookings": 12, "users": 16},
  "classifier": {"mode": "ML", "trained_at": "2026-11-09T18:27:46Z", "error": null},
  "data_notice": "All operational data in this environment is synthetic."
}
```

### `GET /` — SPA
Serves `backend/static/index.html`. When the build is absent it returns **503** with
`{"detail": "...", "fix": "cd frontend && npm run build"}`.

## 2. Auth

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/login` | — | `{email, password}` → `{access_token, token_type, user, agency}` |
| POST | `/api/auth/demo-login` | — | `{email}`; one-click demo sign-in, only while `OPSDESK_ENABLE_ROLE_SWITCH=true` |
| POST | `/api/auth/switch-role` | any | `{role, agency_code?}`; server-side identity switch for demos |
| GET | `/api/auth/me` | any | `{user, agency}` |
| GET | `/api/auth/identities` | — | `{identities[], agencies[], demo_password_hint}` |

`user` = `{id, email, full_name, role, region, timezone, skill_rank, max_capacity, is_online, shift, agency_id}`.

## 3. Tickets

### `GET /api/tickets`
Query: `search` (ticket number, TBOH id, title, agency), `region`, `priority`, `intent`, `status`,
`sla_state`, `agency_id`, `limit` (default 200).

Response: `{count, tickets[], sla_matrix}` — each ticket is a **row**:

```json
{
  "id": 1, "ticket_number": "TCK-101", "title": "...", "description": "...",
  "intent": "REFUND_DELAY", "intent_label": "Refund Delay", "intent_confidence": 0.9319,
  "intent_source": "ML", "priority": "HIGH", "status": "IN_PROGRESS", "queue": "MEA-SUPPORT",
  "region": "MEA", "assigned_to": "Omar Haddad", "assigned_user_id": 10,
  "agency": "Wanderlust Travels", "agency_id": 1,
  "booking": {"tboh_id": "TBOH-778899", "hotel_name": "Atlantis The Palm", "supplier_name": "Hotelbeds",
              "lcd_local": "06 Nov 2026 22:33 UTC+04:00", "check_in_local": "14 Nov 2026 22:33 UTC+04:00",
              "timezone": "Asia/Dubai", "display_timezone": "Asia/Dubai", "...": "..."},
  "sla": {"state": "BREACHED", "governing_rule": "PRIORITY_SLA", "effective_due_at": "...",
          "minutes_remaining": -28563, "holiday_adjustment_applied": false,
          "expired_travel_deadline": false, "missing_dates": [], "reasons": ["..."],
          "at_risk_threshold": 0.75, "urgency_weight": 1.0},
  "escalated": false, "regional_holiday_flag": false,
  "created_at": "...", "updated_at": "...", "resolved_at": null
}
```

### `POST /api/tickets` — 201
Any role. Body: `{title, description, tboh_id?, priority?, agency_id?, regional_holiday_flag?}`.
`tboh_id: null` triggers Stage A extraction from `description`.

```json
{
  "ticket_id": 50, "ticket_number": "TCK-625", "status": "OPEN", "queue": "MEA-SUPPORT",
  "priority": "HIGH", "intent": "REFUND_DELAY",
  "extraction": {"tboh_ids": ["TBOH-778899"], "extraction_source": "DESCRIPTION", "...": "..."},
  "classification": {"intent": "REFUND_DELAY", "confidence": 0.87, "source": "ML",
                     "reasoning": ["..."], "scores": {"...": 0.0}},
  "booking": {"tboh_id": "TBOH-778899", "...": "..."},
  "sla": {"state": "HEALTHY", "governing_rule": "PRIORITY_SLA", "effective_due_at": "..."}
}
```

### `GET /api/tickets/{ticket_id}`
`{ticket_id}` accepts the numeric id **or** the ticket number (`TCK-101`). Returns the row plus:

```json
{
  "classification": {"intent": "...", "label": "...", "confidence": 0.93, "reasoning": ["..."],
                     "scores": {"REFUND_DELAY": 0.93, "...": 0.01}, "source": "ML"},
  "messages": [{"id": 1, "sender_name": "...", "sender_role": "OPS_AGENT",
                "message_type": "PUBLIC_REPLY", "content": "...", "created_at": "..."}],
  "side_conversations": [{"id": 1, "channel_type": "SUPPLIER", "subject": "...",
                          "counterparty_name": "Hilton Paris Opera",
                          "explicit_recipients": ["groups@hilton-paris.com"],
                          "created_by_group": "EU-TRIAGE", "status": "OPEN", "messages": []}],
  "routing_audits": [], "activity_timeline": [{"event_type": "ESCALATED", "actor_name": "...", "description": "..."}],
  "transfers": [], "escalations": [{"assigned_em": "...", "reason": "...", "escalated_at": "..."}],
  "case_brief": {"method": "...", "tickets_in_case": 4, "points": ["...", "...", "..."],
                 "sources": {"ticket_ids": [], "booking_id": "TBOH-778899", "message_count": 3,
                             "side_conversation_count": 1}},
  "related_tickets": [{"ticket_number": "TCK-104", "link_type": "SAME_BOOKING", "confidence": 1.0, "reason": "..."}]
}
```

### Other ticket endpoints

| Method | Path | Roles | Body / effect |
| --- | --- | --- | --- |
| POST | `/api/tickets/{id}/messages` | any | `{content, message_type: PUBLIC_REPLY \| INTERNAL_NOTE}` → 201 message |
| POST | `/api/tickets/{id}/status` | ops | `{status}` — writes a timeline event |
| POST | `/api/tickets/{id}/reclassify` | ops | re-runs Stage B on the stored text |
| POST | `/api/tickets/{id}/intent-override` | ops | `{intent, note?}` — audited override |
| GET | `/api/tickets/{id}/case-brief` | any with access | the 3-point brief only |
| GET | `/api/tickets/{id}/side-conversations` | any with access | `{conversations: [...]}` |
| POST | `/api/tickets/{id}/side-conversations` | any with access | `{channel_type, subject, counterparty_name, recipients[]}` → 201 |
| POST | `/api/tickets/{id}/transfer` | ops | `{to_queue, note?, to_user_id?}` → see §5 |
| GET | `/api/bookings/{tboh_id}` | any | booking + its tickets |
| GET | `/api/extract?text=` | any | Stage A result only |
| GET | `/api/agencies` | any | `{agencies: [...]}` |
| GET | `/api/sla/matrix` | any | priority hours, buffers, thresholds |

## 4. Routing

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| GET | `/api/routing/board` | ops | `{agents[], count, eligible_now, at_capacity}`; each agent has `active_load`, `max_capacity`, `skill_rank`, `shift`, `shift_match_now`, `eligible_generic`, `utilization_pct`, `reference_score` |
| GET | `/api/routing/performance` | ops | same board with resolved counts and mean resolution hours |
| GET | `/api/routing/formula` | ops | `{formula, max_score, weights, variables, hard_filters[], tie_break}` |
| GET | `/api/routing/tickets/{id}/comparator` | ops | `{ticket_number, ticket_region, sla_state, urgency_weight, candidates[], excluded[], winner, tie_break_applied}` |
| POST | `/api/routing/tickets/{id}/route` | ops | `{triggered_by: "MANUAL"\|"AUTO"}` → outcome below |
| POST | `/api/routing/tickets/{id}/reassign` | ops | `{agent_id, note?}` — manager override, new audit row |
| GET | `/api/routing/audits?ticket_id=&limit=` | ops | `{audits[], count}` |

Candidate shape: `{agent_id, full_name, region, skill_rank, active_load, max_capacity, region_match,
shift_match, skill_component, capacity_component, total_score}`.
Excluded shape: `{agent_id, full_name, region, reasons[]}`.

Route response:

```json
{
  "ticket_id": 4, "ticket_number": "TCK-201",
  "assigned_to": {"id": 5, "name": "Ananya Sharma", "region": "APAC", "skill_rank": 5,
                  "active_load": 1, "max_capacity": 8},
  "decision": {"score": 98.13, "decision_reason": "...", "assigned_agent_id": 5,
               "candidates": [], "excluded": [], "urgency_weight": 1.0, "winner": {}},
  "audit_id": 12,
  "fifo_note": "FIFO would have picked ..."
}
```

## 5. Side conversations and transfers

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| GET | `/api/side-conversations/{id}` | any with access | conversation + messages |
| POST | `/api/side-conversations/{id}/messages` | any with access | `{content}` → `{messages_created, recipients[]}` |

Transfer response:

```json
{
  "ticket_id": 6, "ticket_number": "TCK-301",
  "from_queue": "EU-TRIAGE", "to_queue": "EU-SENIOR-OPS",
  "preserved_side_conversations": 1,
  "recipients_unchanged": true,
  "message": "Ticket moved to EU-SENIOR-OPS. Original recipients unchanged (1 conversation(s), 1 recipient(s)).",
  "transfer_id": 1, "note": null
}
```

## 6. Escalations

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| GET | `/api/escalations/queue` | ops | `{counts{escalated, at_risk, breached, healthy}, managers[], tickets[], viewer}` |
| GET | `/api/escalations/managers` | ops | `{managers[]}` with `active_escalations` |
| GET | `/api/escalations/trend` | ops | `{by_week[{week,count}], total, window_weeks}` |
| GET | `/api/escalations/deadlines` | ops | `{deadlines[{ticket_number, title, due_at, state, governing_rule}]}` |
| GET | `/api/escalations/tickets/{id}` | ops | `{ticket_number, escalations[]}` |
| POST | `/api/escalations/tickets/{id}/escalate` | ops | `{reason}` (min 8 chars) → `{status: "ESCALATED", queue: "ESCALATION_MANAGER", assigned_to: {name, role}, escalation}` |

## 7. Analytics

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| GET | `/api/analytics/queue` | agent, EM, lead | totals, `sla_states`, `sla_compliance`, by_region/intent/priority, weekly_volume, agent_workload, next_travel, tickets[] |
| GET | `/api/analytics/product-intelligence?window_days=` | EM, lead | intent distribution, suppliers, weekly trends, resolution distribution, refund bottleneck, regional performance, inventory sync, themes, `data_notice` |
| POST | `/api/analytics/themes/refresh` | EM, lead | re-extract theme tags → `{themes[], count}` |
| GET | `/api/analytics/bug-suggestions?window_days=&min_tickets=` | EM, lead | `{suggestions[], method, note}` — each suggestion: `{supplier, intent, frequency, ticket_ids, ticket_numbers, evidence[], period, confidence, suggested_action}` |
| GET | `/api/analytics/product-bugs` | EM, lead | `{bugs[], count}` |
| POST | `/api/analytics/product-bugs` | EM, lead | `{supplier, intent?, title, suggested_action, related_ticket_ids[], frequency}` → 201 `{bug_code, status}` |

## 8. Exports

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| POST | `/api/exports/stream` | lead, EM | see below |
| GET | `/api/exports/jobs` | lead, EM | `{jobs[], count}` |
| GET | `/api/exports/jobs/{uuid}` | lead, EM | one job |
| GET | `/api/exports/{uuid}/validate` | lead, EM | file re-read: `{result, expected_rows, actual_rows_in_file, row_count_matches, column_count, readable, duration_ms, throughput_rows_per_sec, peak_memory_mb}` |
| GET | `/api/exports/{uuid}/download` | lead, EM | the written file with `Content-Disposition` |

`POST /api/exports/stream` body:

```json
{"file_format": "CSV", "source": "SYNTHETIC_BENCHMARK", "total_rows": 50000,
 "region": null, "status": null, "intent": null, "priority": null, "agency_id": null,
 "date_from": null, "date_to": null}
```

Response: `text/csv` (or `application/x-ndjson`) stream with headers
`X-Export-Job-Uuid`, `X-Export-Rows`, `Content-Disposition`. Rows are produced by a generator in batches
of 5,000; the browser counts bytes and newlines to show real progress.

## 9. Simulation

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| GET | `/api/simulation/status` | any authenticated | database counts, classifier mode, journey catalogue |
| POST | `/api/simulation/seed` | lead | reseed the synthetic dataset |
| POST | `/api/simulation/reset` | lead | reset + reseed, returns deleted counts |
| POST | `/api/simulation/journeys/{A..E}/run?reseed=true&export_rows=50000` | lead, EM | runs one journey against the live API and merges into `benchmark_results/journey_results.json` |
| GET | `/api/simulation/journeys/results` | lead, EM | `{available, generated_at, journeys[]}` |

Journey result: `{journey, title, started_at, finished_at, steps_total, steps_passed, passed,
steps[{name, expected, actual, passed, evidence{}, duration_ms, error}], meta, console}`.

## 10. Client contract notes

- Ticket detail paths accept `TCK-101` or `1`; routing audits take the numeric id.
- `POST /api/exports/stream` cannot be triggered with a plain `<a href>` — the bearer token must be sent,
  so the client fetches and saves a blob (`lib/api.ts::downloadExport`).
- SLA countdowns are computed from `sla.effective_due_at` (absolute) plus `seconds_remaining`; the client
  never recomputes the policy itself.
- Role capability map used by the UI mirrors the backend matrix in `README`/`Architecture`.
