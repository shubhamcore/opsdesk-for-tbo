# OpsDesk — Database Schema

Engine: **SQLite 3, WAL mode** (`database/opsdesk.db`). The models are plain SQLAlchemy 2.x declarations
with portable column types, so the same DDL maps to PostgreSQL by changing `OPSDESK_DATABASE_URL`.

**15 tables.** All timestamps are stored as **aware UTC** through `backend/models/base.py::TZDateTime`,
which raises on a naive datetime instead of guessing. Display conversion to the booking's IANA timezone
happens in the API serialiser.

```
agencies ──< bookings ──< tickets ──< messages
                │            ├────────< ticket_links (source/target)
                │            ├────────< activity_timeline
                │            ├────────< side_conversations ──< side_messages
                │            ├────────< routing_audits
                │            ├────────< escalation_records
                │            └────────< ticket_transfers
users ──────────┘  (agency_id, assigned_user_id, created_by_id, escalated_by_id, from/to_user_id)

theme_tags      (derived)          export_jobs     (runtime)        product_bugs (local records)
```

---

## 1. `agencies` — 4 rows
| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| code | VARCHAR(32) | `AG-WLT`, `AG-AGH`, `AG-EWB`, `AG-SKY` unique |
| name | VARCHAR(160) | Wanderlust Travels, Apex Global Holidays, EuroWings B2B, Skyline Corporate Travel |
| tier | VARCHAR(16) | `GOLD` / `SILVER` / `PLATINUM` |
| region | VARCHAR(16) | `MEA` / `APAC` / `EU` / `AMER` |
| contact_email | VARCHAR(160) | |
| created_at, is_deleted | DATETIME, BOOLEAN | soft delete |

## 2. `users` — 16 rows
| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| email | VARCHAR(160) | unique, lowercase |
| full_name | VARCHAR(120) | |
| hashed_password | VARCHAR(255) | `pbkdf2_sha256$<iterations>$<salt>$<hash>` — no plaintext anywhere |
| role | VARCHAR(32) | `AGENCY_REQUESTER` · `OPS_AGENT` · `ESCALATION_MANAGER` · `OPS_LEAD` |
| region | VARCHAR(16) | routing + SLA scoping |
| shift_start / shift_end | VARCHAR(5) | `HH:MM` local to `timezone`; 24 h shift is `00:00-23:59` |
| timezone | VARCHAR(48) | IANA |
| skill_rank | INTEGER | 1–5; ≥ 4 required for CRITICAL/AT_RISK/BREACHED tickets |
| max_capacity | INTEGER | concurrent ticket limit |
| is_online | BOOLEAN | offline agents are filtered out of routing |
| agency_id | INTEGER FK → agencies | only for requesters |
| is_deleted, created_at | | |

## 3. `bookings` — 12 rows · the operational context
| Column | Type | Notes |
| --- | --- | --- |
| id | INTEGER PK | |
| tboh_id | VARCHAR(32) | `TBOH-######` — the join key across the whole product |
| agency_id | FK → agencies | |
| supplier_name / supplier_email | VARCHAR | Hotelbeds, Hilton, Accor, Marriott, Rotana, Agoda, WebBeds |
| hotel_name, destination_city, destination_country | VARCHAR | |
| region | VARCHAR(16) | |
| timezone | VARCHAR(48) | used for local display of `check_in` / `lcd` |
| check_in, check_out, lcd | DATETIME NULL | nullable on purpose — missing dates must not become "now" |
| booking_status | VARCHAR(24) | `CONFIRMED`, `REFUND_PENDING`, `CANCELLED`, … |
| amount, currency | NUMERIC(12,2), VARCHAR(3) | |
| passenger_name | VARCHAR(120) | |

## 4. `tickets` — 49 seeded rows (24 named + 25 background)
| Column | Type | Notes |
| --- | --- | --- |
| id, ticket_number | INTEGER PK, VARCHAR(16) | `TCK-###`, unique, sequential |
| booking_id | FK → bookings, nullable | a ticket may exist without a booking |
| agency_id, assigned_user_id | FK | |
| region | VARCHAR(16) | drives routing eligibility and SLA region |
| title, description | VARCHAR / TEXT | description is the classifier input |
| intent | VARCHAR(48) | one of the 8 canonical intents |
| intent_confidence | FLOAT | calibrated probability, `NULL` when rules were used |
| intent_reasoning, intent_scores | JSON | evidence lines and per-class scores |
| intent_source | VARCHAR(16) | `ML` or `RULES` |
| extracted_tboh, extraction_source | VARCHAR | `DESCRIPTION`, `FIELD`, `NONE` |
| priority | VARCHAR(16) | CRITICAL / HIGH / MEDIUM / LOW |
| status | VARCHAR(24) | `OPEN`, `IN_PROGRESS`, `ESCALATED`, `RESOLVED`, `CLOSED` |
| queue | VARCHAR(48) | regional queue or `ESCALATION_MANAGER` |
| regional_holiday_flag | BOOLEAN | lowers the at-risk threshold to 50 % |
| priority_due_at, effective_sla_due_at | DATETIME | computed and stored at creation |
| sla_rule | VARCHAR(48) | `PRIORITY_SLA`, `LCD_DEADLINE`, `CHECKIN_DEADLINE` |
| at_risk_threshold | FLOAT | 0.75 or 0.50 |
| escalated, escalated_at, escalated_by_id | | mirror of the escalation record for fast filtering |
| created_by_id, created_at, updated_at, resolved_at, is_deleted | | |

## 5. `ticket_links` — case graph
`id, source_ticket_id, target_ticket_id, link_type, confidence_score, reason, created_at`

`link_type` = `SAME_BOOKING` (1.0) — every ticket sharing a booking is linked both ways; the graph panel
in W2 renders exactly these rows. Links are written inside the ticket-creation transaction.

## 6. `messages` — main thread
`id, ticket_id, sender_id, sender_name, sender_role, message_type, content, created_at`

`message_type` = `PUBLIC_REPLY` (agency-visible) | `INTERNAL_NOTE` (stripped from requester payloads).

## 7. `side_conversations` + `side_messages` — independent threads
`side_conversations`: `id, ticket_id, channel_type, subject, counterparty_name, explicit_recipients (JSON),
created_by_group, status, created_at`

`side_messages`: `id, side_conversation_id, sender_email, recipient_email, content, direction, status,
created_at`

`explicit_recipients` is a JSON array **per conversation**; it is never derived from the ticket's queue, so
a transfer cannot leak the destination group's addresses into an existing supplier thread.

## 8. `ticket_transfers` — transfer safety
`id, ticket_id, from_queue, to_queue, from_user_id, to_user_id, note, preserved_side_conversations,
preserved_recipients (JSON), transferred_by_id, created_at`

`preserved_recipients` stores a snapshot of `{conversation_id, recipients[]}` taken **before** the move; the
service compares it to the state after the move and returns `recipients_unchanged`.

## 9. `routing_audits` — immutable decision record
`id, ticket_id, candidate_scores_json, excluded_json, eligible_count, selected_agent_id, selected_score,
decision_reason, tie_break_applied, triggered_by, created_at`

`candidate_scores_json` holds, for every candidate, the four components and the total — enough to
reproduce a decision months later. Rows are append-only; an override adds a row.

## 10. `escalation_records`
`id, ticket_id, escalated_by_id, assigned_em_id, previous_owner_id, previous_status, previous_queue,
reason, escalated_at`

There is deliberately **no** `resolved_by` column: escalation is a handover event, and resolution is tracked
on the ticket (`resolved_at`) plus the timeline.

## 11. `activity_timeline`
`id, ticket_id, event_type, actor_name, description, metadata_json, created_at`

`event_type` examples: `CREATED`, `CLASSIFIED`, `ROUTED`, `MESSAGE`, `STATUS_CHANGED`, `TRANSFERRED`,
`ESCALATED`, `INTENT_OVERRIDDEN`. Immutable.

## 12. `theme_tags` — derived, refreshable
`id, name, category, intent, occurrence_count, distinct_suppliers, last_seen`

## 13. `product_bugs` — local records only
`id, bug_code, title, supplier_name, intent, frequency, status, suggested_action, supporting_evidence,
related_ticket_ids (JSON), window_start, window_end, created_at`

`bug_code` = `PROD-BUG-###`. No external tracker reference exists because no integration is implemented.

## 14. `export_jobs`
`id, job_uuid, requested_by_email, file_format, filters_json, total_rows, rows_streamed, duration_ms,
file_size_bytes, throughput_rows_per_sec, peak_memory_mb, status, error_message, filters_applied,
data_source, created_at, completed_at`

`data_source` = `DB` (live rows) or `SYNTHETIC_BENCHMARK` (generated scale rows). Every metric column is
measured at runtime.

---

## Indexes and constraints

- Unique: `users.email`, `agencies.code`, `bookings.tboh_id`, `tickets.ticket_number`,
  `export_jobs.job_uuid`, `product_bugs.bug_code`.
- Non-unique hot paths: `tickets(region, status)`, `tickets(assigned_user_id)`, `tickets(booking_id)`,
  `messages(ticket_id)`, `routing_audits(ticket_id)`, `side_conversations(ticket_id)`.
- Foreign keys are declared on the models and enforced by SQLite (`PRAGMA foreign_keys=ON`).
- Soft delete (`is_deleted`) is used for agencies, users, bookings and tickets so history survives.

## Seeded fixture guarantees

The journey layer depends on these exact properties, and `tests/test_db_integrity.py` asserts them:

| Fixture | Guarantee |
| --- | --- |
| Journey A | `TBOH-778899` has at least 3 tickets (`TCK-101/104/109`) |
| Journey B | `TCK-201` is APAC + HIGH, Ananya Sharma (APAC, skill 5) has **1/8** load and Omar Haddad is at capacity |
| Journey C | `TCK-301` sits in `EU-TRIAGE` with supplier conversation to `groups@hilton-paris.com` |
| Journey D | `TCK-401` LCD ≈ 55 min out, `TCK-402` check-in ≈ 90 min out, `TCK-403/404` already escalated |
| Journey E | ≥ 25 background tickets so pattern detection and the export both have volume |

## Reseeding

```bash
python -m database.seed_data.seed            # seed if empty
python -c "from database.seed_data.seed import seed_database; seed_database(reset=True)"
```

`reset=True` deletes runtime rows (messages, links, audits, escalations, transfers, jobs, bugs, tickets,
bookings, users, agencies) and rebuilds the dataset relative to `now`, so SLA countdowns are always
realistic. The seed is deterministic for a given `now`.


## v2.1 — `agent_runs` and hot-path indexes

```
agent_runs
├── id                  INTEGER PK
├── run_uuid            VARCHAR(32) UNIQUE NOT NULL   -- AGT-XXXXXXXXXXXX (indexed)
├── ticket_id           FK tickets.id NOT NULL        -- indexed with created_at
├── objective           VARCHAR(64)  DEFAULT 'CASE_REVIEW'
├── status              VARCHAR(16)  COMPLETED | PARTIAL | FAILED
├── agent_count         INTEGER
├── overall_confidence  FLOAT
├── summary             TEXT
├── agents_json         JSON    -- full per-agent trace: findings, evidence, tool_calls
├── plan_json           JSON    -- prioritised actions with source_agent
├── duration_ms         FLOAT
├── created_by_id       FK users.id
└── created_at          DATETIME (UTC, indexed)
```

One row per multi-agent review. The table is append-only in practice: nothing updates or
deletes a run, which is what makes an agent-assisted decision reconstructable later.

Indexes applied idempotently at startup (`backend/database.py::_ensure_hot_indexes`), because
`create_all` never alters an existing table:

| Index | Columns | Serves |
| --- | --- | --- |
| `ix_tickets_status_queue` | `tickets(status, queue)` | Queue listing and SLA command centre |
| `ix_tickets_assigned` | `tickets(assigned_user_id, status)` | Agent load / capacity maths |
| `ix_tickets_created` | `tickets(created_at)` | Weekly trends, export windows |
| `ix_messages_ticket_created` | `messages(ticket_id, created_at)` | Case thread |
| `ix_agent_runs_ticket` | `agent_runs(ticket_id, created_at)` | Agent review history |
| `ix_side_messages_conversation` | `side_messages(conversation_id, created_at)` | Side conversation thread |
