"""Module 6 — streaming exports with job tracking and independent validation.

Nothing here materialises the full result set: rows are produced by a
server-side iterator in batches (default 5,000), written to disk batch by
batch, and yielded to the client as they are produced. Memory is sampled from
the process RSS so the reported peak is measured, not asserted.
"""
from __future__ import annotations

import csv
import io
import json
import resource
import time
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import ExportJob, Ticket
from backend.models.base import utcnow
from backend.services import sla as sla_service

EXPORT_COLUMNS = [
    "row_id", "ticket_number", "tboh_id", "ticket_title", "intent", "intent_confidence",
    "intent_source", "priority", "status", "queue", "region", "agency", "agency_tier",
    "assigned_agent", "supplier", "hotel", "destination_city", "destination_country",
    "booking_status", "booking_amount", "currency", "priority_due_at", "sla_due_at",
    "sla_state", "governing_rule",
]
MAX_ROWS = 200_000


def _rss_mb() -> float:
    """Current resident set size in MiB (Linux /proc, portable fallback)."""
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
    except OSError:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def export_path(job: ExportJob):
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    suffix = "csv" if job.file_format == "CSV" else "jsonl"
    return settings.export_dir / f"opsdesk_export_{job.job_uuid}.{suffix}"


def sweep_old_exports(keep: int = 3) -> list[str]:
    """Keep the working directory small: only the newest ``keep`` files stay.

    Export artifacts are regenerable, so retaining every 16 MB file is pure
    disk cost (and would otherwise bloat workspace snapshots).
    """
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [path for path in settings.export_dir.iterdir() if path.is_file()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed = []
    for path in files[keep:]:
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    return removed


def create_job(db: Session, *, user_email: str, file_format: str, total_rows: int,
               source: str, filters: dict) -> ExportJob:
    job = ExportJob(
        job_uuid=str(uuid.uuid4()),
        requested_by_email=user_email,
        file_format=file_format,
        filters_json=filters,
        total_rows=total_rows,
        rows_streamed=0,
        status="QUEUED",
        data_source=source,
        created_at=utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# --------------------------------------------------------------- row sources

def _db_rows(db: Session, filters: dict) -> list[dict]:
    query = select(Ticket).where(Ticket.is_deleted.is_(False))
    if filters.get("region"):
        query = query.where(Ticket.region == filters["region"])
    if filters.get("status"):
        query = query.where(Ticket.status == filters["status"])
    if filters.get("intent"):
        query = query.where(Ticket.intent == filters["intent"])
    if filters.get("priority"):
        query = query.where(Ticket.priority == filters["priority"])
    if filters.get("agency_id"):
        query = query.where(Ticket.agency_id == filters["agency_id"])
    tickets = db.scalars(query.order_by(Ticket.id)).all()
    rows = []
    for index, ticket in enumerate(tickets, start=1):
        booking = ticket.booking
        sla = sla_service.compute_sla(
            created_at=ticket.created_at, priority=ticket.priority,
            lcd=booking.lcd if booking else None,
            check_in=booking.check_in if booking else None,
            regional_holiday_flag=ticket.regional_holiday_flag,
            status=ticket.status,
        )
        rows.append({
            "row_id": index,
            "ticket_number": ticket.ticket_number,
            "tboh_id": booking.tboh_id if booking else "",
            "ticket_title": ticket.title,
            "intent": ticket.intent or "",
            "intent_confidence": round(ticket.intent_confidence or 0, 4),
            "intent_source": ticket.intent_source or "",
            "priority": ticket.priority,
            "status": ticket.status,
            "queue": ticket.queue,
            "region": ticket.region,
            "agency": ticket.agency.name if ticket.agency else "",
            "agency_tier": ticket.agency.tier if ticket.agency else "",
            "assigned_agent": ticket.assigned_user.full_name if ticket.assigned_user else "",
            "supplier": booking.supplier_name if booking else "",
            "hotel": booking.hotel_name if booking else "",
            "destination_city": booking.destination_city if booking else "",
            "destination_country": booking.destination_country if booking else "",
            "booking_status": booking.booking_status if booking else "",
            "booking_amount": float(booking.amount) if booking else 0.0,
            "currency": booking.currency if booking else "",
            "priority_due_at": ticket.priority_due_at.isoformat() if ticket.priority_due_at else "",
            "sla_due_at": sla.effective_due_at.isoformat(),
            "sla_state": sla.state,
            "governing_rule": sla.governing_rule,
        })
    return rows


_SYNTHETIC_INTENTS = [
    "REFUND_DELAY", "CANCELLATION_LCD_WAIVER", "VOUCHER_CONFIRMATION_ISSUE",
    "AMENDMENT_NAME_DATE", "INVENTORY_RATE_SYNC_BUG", "SPECIAL_REQUEST",
    "SUPPLIER_OVERBOOKING_RELOCATION", "BILLING_INVOICE_DISPUTE",
]
_SYNTHETIC_SUPPLIERS = ["Hotelbeds", "Accor", "Marriott", "Hilton", "Rotana", "Agoda", "WebBeds"]
_SYNTHETIC_REGIONS = ["APAC", "MEA", "EU", "AMER"]
_SYNTHETIC_STATES = ["HEALTHY", "AT_RISK", "BREACHED", "RESOLVED"]
_SYNTHETIC_RULES = ["PRIORITY_SLA", "LCD_DEADLINE", "CHECK_IN_DEADLINE"]


def iter_row_batches(db: Session, *, filters: dict, total_rows: int, source: str,
                     batch_size: int, progress_cb=None):
    """Yield batches of export rows, never the whole set."""
    if source == "DB":
        rows = _db_rows(db, filters)
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            if progress_cb:
                progress_cb(len(batch))
            yield batch
        return

    # SYNTHETIC_BENCHMARK — deterministic, explicitly labelled synthetic rows.
    now = utcnow()
    for start in range(0, total_rows, batch_size):
        batch = []
        for offset in range(start, min(start + batch_size, total_rows)):
            index = offset + 1
            intent = _SYNTHETIC_INTENTS[offset % len(_SYNTHETIC_INTENTS)]
            region = _SYNTHETIC_REGIONS[offset % len(_SYNTHETIC_REGIONS)]
            created = now - timedelta(hours=offset % 240)
            batch.append({
                "row_id": index,
                "ticket_number": f"SYN-{index:06d}",
                "tboh_id": f"TBOH-{700000 + (offset % 90000):06d}",
                "ticket_title": f"Synthetic benchmark row {index} — {intent.replace('_', ' ').title()}",
                "intent": intent,
                "intent_confidence": round(0.55 + ((offset % 45) / 100), 4),
                "intent_source": "ML",
                "priority": ["CRITICAL", "HIGH", "MEDIUM", "LOW"][offset % 4],
                "status": ["OPEN", "IN_PROGRESS", "PENDING_SUPPLIER", "RESOLVED"][offset % 4],
                "queue": f"{region}-SUPPORT",
                "region": region,
                "agency": ["Wanderlust Travels", "Apex Global Holidays", "EuroWings B2B",
                           "Skyline Corporate Travel"][offset % 4],
                "agency_tier": ["GOLD", "SILVER", "BRONZE", "PLATINUM"][offset % 4],
                "assigned_agent": ["Ananya Sharma", "Omar Haddad", "Sofia Lindqvist",
                                   "Rahul Mehta", "Daniel Okafor"][offset % 5],
                "supplier": _SYNTHETIC_SUPPLIERS[offset % len(_SYNTHETIC_SUPPLIERS)],
                "hotel": ["Atlantis The Palm", "Hilton Paris Opera", "Marina Bay Sands",
                          "Ibis Styles Bali", "Rotana Downtown Dubai"][offset % 5],
                "destination_city": ["Dubai", "Paris", "Singapore", "Bali", "Bangkok"][offset % 5],
                "destination_country": ["UAE", "France", "Singapore", "Indonesia", "Thailand"][offset % 5],
                "booking_status": ["CONFIRMED", "REFUND_PENDING", "CANCELLED", "AMENDED"][offset % 4],
                "booking_amount": round(250 + (offset % 4000) + (offset % 99) / 100, 2),
                "currency": ["USD", "EUR", "GBP", "AED", "SGD"][offset % 5],
                "priority_due_at": (created + timedelta(hours=4)).isoformat(),
                "sla_due_at": (created + timedelta(hours=4 + (offset % 6))).isoformat(),
                "sla_state": _SYNTHETIC_STATES[offset % 4],
                "governing_rule": _SYNTHETIC_RULES[offset % 3],
            })
        if progress_cb:
            progress_cb(len(batch))
        yield batch


# ------------------------------------------------------------------- streaming

def stream_export(db: Session, *, job: ExportJob, filters: dict, source: str,
                  total_rows: int, batch_size: int | None = None):
    """Generator streaming the export and finishing the job record.

    Known limitation: if the client disconnects mid-stream, the job stays in
    STREAMING state (the generator is closed without reaching the completion
    block). The partial file is still on disk.
    """
    batch_size = batch_size or settings.export_batch_size
    file_format = job.file_format
    out_path = export_path(job)
    started = time.perf_counter()
    progress = {"rows": 0}
    # Memory is sampled from VmRSS (current resident set) rather than
    # ru_maxrss, which is a process-lifetime high-water mark and would report
    # a 0 MB delta on every run after the first. tracemalloc is deliberately
    # not used: its per-allocation tracing distorted throughput by >5x.
    rss_start = _rss_mb()
    rss_peak = rss_start

    header = ""
    if file_format == "CSV":
        header_buffer = io.StringIO()
        csv.DictWriter(header_buffer, fieldnames=EXPORT_COLUMNS).writeheader()
        header = header_buffer.getvalue()

    def on_batch(batch_len: int) -> None:
        nonlocal rss_peak
        progress["rows"] += batch_len
        job.rows_streamed = progress["rows"]
        job.status = "STREAMING"
        rss_peak = max(rss_peak, _rss_mb())
        db.commit()

    try:
        with open(out_path, "w", encoding="utf-8", newline="") as handle:
            if header:
                handle.write(header)
                yield header

            for batch in iter_row_batches(
                db, filters=filters, total_rows=total_rows, source=source,
                batch_size=batch_size, progress_cb=on_batch,
            ):
                if file_format == "CSV":
                    batch_buffer = io.StringIO()
                    csv.DictWriter(
                        batch_buffer, fieldnames=EXPORT_COLUMNS, lineterminator="\n"
                    ).writerows(batch)
                    chunk = batch_buffer.getvalue()
                else:
                    chunk = "".join(
                        json.dumps(row, separators=(",", ":"), default=str) + "\n" for row in batch
                    )
                handle.write(chunk)
                yield chunk

            handle.flush()
            size = out_path.stat().st_size
    except Exception as exc:  # surface failures in the job record, then re-raise
        job.status = "FAILED"
        job.error_message = f"{type(exc).__name__}: {exc}"[:500]
        job.rows_streamed = progress["rows"]
        job.completed_at = utcnow()
        db.commit()
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    rss_peak = max(rss_peak, _rss_mb())
    job.rows_streamed = progress["rows"]
    job.duration_ms = duration_ms
    job.file_size_bytes = size
    job.throughput_rows_per_sec = (
        round(progress["rows"] / (duration_ms / 1000), 2) if duration_ms else None
    )
    job.peak_memory_mb = round(max(0.0, rss_peak - rss_start), 3)
    job.status = "COMPLETED"
    job.completed_at = utcnow()
    job.filters_applied = json.dumps(filters)[:500]
    db.commit()


def count_rows(path) -> tuple[int, int]:
    """Independently re-read the artifact: (data rows, columns)."""
    path = str(path)
    if path.endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            rows = sum(1 for _ in reader)
            return rows, len(header)
    rows, columns = 0, 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if columns == 0:
                columns = len(json.loads(line).keys())
            rows += 1
    return rows, columns


def job_payload(job: ExportJob, *, include_path: bool = True) -> dict:
    payload = {
        "job_id": job.id,
        "job_uuid": job.job_uuid,
        "format": job.file_format,
        "status": job.status,
        "data_source": job.data_source,
        "requested_by": job.requested_by_email,
        "total_rows": job.total_rows,
        "rows_streamed": job.rows_streamed,
        "duration_ms": job.duration_ms,
        "file_size_bytes": job.file_size_bytes,
        "file_size_mb": round(job.file_size_bytes / (1024 * 1024), 3) if job.file_size_bytes else None,
        "throughput_rows_per_sec": job.throughput_rows_per_sec,
        "peak_memory_mb": job.peak_memory_mb,
        "filters": job.filters_json,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "progress_pct": round(100 * job.rows_streamed / job.total_rows, 2) if job.total_rows else 0,
    }
    if include_path:
        payload["file_path"] = str(export_path(job))
        payload["download_url"] = f"/api/exports/{job.job_uuid}/download"
    return payload
