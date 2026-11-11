"""Module 6 — streaming exports, job tracking, independent validation, download."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.schemas import ExportStreamRequest
from backend.database import get_db
from backend.models import ExportJob, User
from backend.security import require_roles
from backend.services.exports import (
    EXPORT_COLUMNS,
    count_rows,
    create_job,
    export_path,
    job_payload,
    stream_export,
    sweep_old_exports,
)

router = APIRouter(prefix="/api/exports", tags=["exports"])

EXPORT_ROLES = ("OPS_LEAD", "ESCALATION_MANAGER")


@router.post("/stream")
def stream(
    payload: ExportStreamRequest,
    user: User = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    filters = {
        "agency_id": payload.agency_id,
        "region": payload.region,
        "status": payload.status,
        "intent": payload.intent,
        "priority": payload.priority,
        "date_from": payload.date_from.isoformat() if payload.date_from else None,
        "date_to": payload.date_to.isoformat() if payload.date_to else None,
    }
    job = create_job(
        db,
        user_email=user.email,
        file_format=payload.file_format,
        total_rows=payload.total_rows,
        source=payload.source,
        filters=filters,
    )
    sweep_old_exports(keep=3)

    media_type = "text/csv" if payload.file_format == "CSV" else "application/x-ndjson"
    suffix = "csv" if payload.file_format == "CSV" else "jsonl"
    filename = f"opsdesk_export_{job.job_uuid}.{suffix}"

    return StreamingResponse(
        stream_export(
            db,
            job=job,
            filters=filters,
            source=payload.source,
            total_rows=payload.total_rows,
        ),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Job-Uuid": job.job_uuid,
            "X-Export-Rows": str(payload.total_rows),
            "X-Export-Columns": str(len(EXPORT_COLUMNS)),
            "Cache-Control": "no-store",
        },
    )


@router.get("/jobs")
def jobs(
    limit: int = 25,
    user: User = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(select(ExportJob).order_by(ExportJob.created_at.desc()).limit(limit)).all()
    return {"jobs": [job_payload(row, include_path=False) for row in rows], "count": len(rows)}


@router.get("/jobs/{job_uuid}")
def job(
    job_uuid: str,
    user: User = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(select(ExportJob).where(ExportJob.job_uuid == job_uuid))
    if row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Export job not found")
    return job_payload(row)


@router.get("/{job_uuid}/validate")
def validate(
    job_uuid: str,
    user: User = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(select(ExportJob).where(ExportJob.job_uuid == job_uuid))
    if row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Export job not found")
    path = export_path(row)
    if not path.exists():
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Export file is not available on disk")
    rows, columns = count_rows(path)
    size = path.stat().st_size
    matches = rows == row.rows_streamed
    return {
        "job_uuid": job_uuid,
        "result": "PASS" if matches and rows > 0 else "FAIL",
        "expected_rows": row.rows_streamed,
        "actual_rows_in_file": rows,
        "row_count_matches": matches,
        "column_count": columns,
        "file_size_bytes": size,
        "file_format": row.file_format,
        "readable": True,
        "duration_ms": row.duration_ms,
        "throughput_rows_per_sec": row.throughput_rows_per_sec,
        "peak_memory_mb": row.peak_memory_mb,
        "note": (
            "Row count and column count are re-read from the file on disk, independent of the "
            "numbers reported while streaming."
        ),
    }


@router.get("/{job_uuid}/download")
def download(
    job_uuid: str,
    user: User = Depends(require_roles(*EXPORT_ROLES)),
    db: Session = Depends(get_db),
) -> FileResponse:
    row = db.scalar(select(ExportJob).where(ExportJob.job_uuid == job_uuid))
    if row is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Export job not found")
    path = export_path(row)
    if not path.exists():
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Export file is not available on disk yet")
    return FileResponse(
        path,
        media_type="text/csv" if row.file_format == "CSV" else "application/x-ndjson",
        filename=path.name,
    )
