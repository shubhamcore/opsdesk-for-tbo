"""Declarative base, timezone-aware datetime type and shared helpers."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Timezone-aware UTC now — the only clock the application uses."""
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """Store naive UTC in the database, always hand back aware UTC datetimes.

    SQLite has no native timezone support, so the conversion happens in the
    type decorator: naive values written are interpreted as UTC, and every
    value read is returned with ``tzinfo=UTC``. This keeps ``ValueError``
    checks in the SLA service meaningful (a naive datetime passed by a caller
    is still rejected there).
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("TZDateTime requires a timezone-aware datetime")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass
