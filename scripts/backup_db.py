"""Consistent SQLite backup using the online backup API.

    python -m scripts.backup_db --out backups/opsdesk-$(date +%F).db

WAL mode allows readers during the copy; ``sqlite3.Connection.backup`` produces a
single consistent file rather than three sidecars that could tear.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings


def backup(out: Path) -> dict:
    source_path = settings.database_url.replace("sqlite:///", "")
    source = Path(source_path)
    if not source.exists():
        raise SystemExit(f"database not found: {source}")
    out.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    try:
        src.backup(dst)
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        dst.close()
        src.close()
    size = out.stat().st_size
    return {
        "source": str(source),
        "out": str(out),
        "bytes": size,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Back up the OpsDesk SQLite database")
    parser.add_argument("--out", required=True, help="destination .db path")
    args = parser.parse_args()
    print(backup(Path(args.out)))
