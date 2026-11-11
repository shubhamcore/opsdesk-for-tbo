"""Database engine, session factory and SQLite pragmas (WAL + foreign keys)."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings
from backend.models.base import Base

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
    """Enable WAL, enforce FK constraints, use a busy timeout for concurrency."""
    if not settings.database_url.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts / simulations / services."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. In production this is replaced by Alembic migrations
    (see database/migrations/); for the self-contained MVP we create-if-absent."""
    import backend.models.entities  # noqa: F401  (register mappers)

    settings.database_url  # touch to keep settings imported
    from backend.config import settings as _s

    _s.export_dir.mkdir(parents=True, exist_ok=True)
    (_s.database_url.split("///")[-1].rsplit("/", 1)[0]) if "///" in _s.database_url else ""
    Base.metadata.create_all(bind=engine)
    _ensure_hot_indexes()


HOT_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_tickets_status_queue ON tickets (status, queue)",
    "CREATE INDEX IF NOT EXISTS ix_tickets_assigned ON tickets (assigned_user_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_tickets_created ON tickets (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_messages_ticket_created ON messages (ticket_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_agent_runs_ticket ON agent_runs (ticket_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_side_messages_conversation ON side_messages (conversation_id, created_at)",
)


def _ensure_hot_indexes() -> None:
    """Create the indexes that matter for queue, thread and agent-run reads.

    ``create_all`` never alters an existing table, so indexes are applied
    separately and idempotently. In a Postgres deployment the same statements run
    through Alembic (see ``database/migrations/``).
    """
    with engine.begin() as connection:
        for statement in HOT_INDEXES:
            try:
                connection.execute(text(statement))
            except Exception:  # pragma: no cover - non-SQLite dialects differ
                continue
