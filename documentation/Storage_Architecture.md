# OpsDesk — Storage Architecture

This document separates two things clearly:

1. **What this MVP implements** — a single SQLite database on one node.
2. **The reference tiering design** for production scale — hot / warm / cold storage.

Nothing in the reference design is claimed as built. The mapping between them is stated at the end.

---

## 1. Implemented in this MVP

| Aspect | Implementation |
| --- | --- |
| Engine | SQLite 3, WAL journal mode, `database/opsdesk.db` (+ `-wal` / `-shm`) |
| Schema | 15 tables declared with SQLAlchemy 2.x (`backend/models/entities.py`) |
| Volume | 49 tickets · 12 bookings · 4 agencies · 16 users · 348 ticket links (seeded) |
| Writes | Transactional; mutating services commit once per operation |
| Concurrency | One process; SQLite serialises writers, WAL allows concurrent readers |
| Backups | File copy or `sqlite3 .backup`; no replication |
| Exports | CSV/JSONL written to `exports/` and pruned by `sweep_old_exports(keep=n)` |
| Analytics | Computed on demand with SQL aggregates over the same tables |
| Timezone | Aware UTC storage (`TZDateTime`), conversion at the API boundary |

**Why SQLite for the demo.** Zero operational overhead, identical SQL semantics for the queries used,
and the models are written with portable types so the move to PostgreSQL is a URL change plus index
review. The trade-off — single writer, no horizontal scale — is acceptable for a demo dataset and is
called out rather than hidden.

**Postgres compatibility notes.** `JSON` columns map to `JSONB`; `NUMERIC(12,2)` maps directly;
`DATETIME` maps to `TIMESTAMPTZ`; no SQLite-specific SQL is used in the services (no `strftime`,
no `ATTACH`). The untested part is the migration itself — see *Not executed* in `Testing_Report.md#7`.

---

## 2. Reference tiering (production design)

### Hot tier — 0 to 90 days · PostgreSQL

- Row-per-ticket transactional store; the source of truth for every mutation.
- Holds: tickets, messages, side conversations, routing audits, escalation records, transfers,
  activity timeline, users, agencies, bookings.
- Key indexes: `(region, status)`, `(assigned_user_id, status)`, `(booking_id)`, `(effective_sla_due_at)`,
  `(intent, created_at)`, `(supplier_name, intent)`.
- Writes are short transactions; audit rows are append-only.
- Retention: rows older than 90 days are moved to the warm tier by a scheduled job (tickets keep a stub
  reference so links never dangle).

### Warm tier — 90 days to 2 years · DuckDB or ClickHouse (columnar)

- Analytics store fed by an incremental job (daily or hourly) from the hot tier.
- Optimised for the queries Module 5 actually issues: group-by intent, supplier, region, ISO week;
  percentile resolution times; supplier × intent frequency for bug suggestions.
- DuckDB fits single-node analytics with Parquet on local/object storage; ClickHouse fits a multi-tenant
  cluster with high ingest.
- Immutable snapshots: analytics are recomputed from source rows, never edited in place.

### Cold tier — 2 to 7 years · Parquet on S3 / MinIO

- Monthly partition per entity, e.g. `s3://opsdesk-cold/tickets/year=2026/month=11/*.parquet`.
- Compression ~5–10× versus row storage; queried on demand through DuckDB or Athena-style engines.
- Satisfies long-retention requirements (audit, dispute handling) without paying hot-tier costs.
- Object lifecycle rules move partitions to infrequent-access storage after 12 months.

```
                  ┌────────────────────────┐
 writes ─────────►│  HOT  PostgreSQL 0–90d │
                  └───────────┬────────────┘
                              │ nightly rollup / CDC
                  ┌───────────▼────────────┐
 analytics ──────►│  WARM  DuckDB / ClickHouse 90d–2y │
                  └───────────┬────────────┘
                              │ archive (monthly)
                  ┌───────────▼────────────┐
 on-demand ──────►│  COLD  Parquet on S3/MinIO 2–7y   │
                  └────────────────────────┘
```

### Export path at scale

Exports must not be generated inside an API worker once row counts pass a few million:

1. The API validates the request and enqueues a job (same `export_jobs` contract as today).
2. A worker streams from the appropriate tier (hot for recent, warm/cold for historical).
3. Rows are written to object storage in Parquet or CSV parts; a manifest records row count and checksum.
4. A signed URL is returned; validation re-reads the manifest and file footer.

This MVP implements the same job contract and validation semantics in-process, which is why the API and
UI already expose `rows_streamed`, `duration_ms`, `file_size`, `throughput` and `peak_memory` — those
fields are what a queued implementation would report too.

---

## 3. What is built vs designed

| Capability | Reference design | This MVP | Evidence |
| --- | --- | --- | --- |
| Transactional store | PostgreSQL | SQLite (WAL) | `backend/database.py`, `database/opsdesk.db` |
| Analytics engine | DuckDB / ClickHouse | SQL aggregates on SQLite | `backend/services/analytics.py` |
| Cold archive | Parquet on S3/MinIO | not implemented | — |
| Export worker | Queue + object storage | in-process `StreamingResponse` | `backend/services/exports.py` |
| Retention jobs | Scheduled tiering | not implemented | — |
| Backups | PITR / replicas | file copy | this document |

`duckdb` is listed in `requirements.txt` as an optional analytics dependency. It is **not** imported on any
request path in this build, and no warm-tier query runs today.
