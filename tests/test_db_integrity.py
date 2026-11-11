"""Database integrity tests — schema, constraints, indexes and pragmas."""
from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from backend.database import engine
from backend.models import Booking, Ticket, TicketLink

REQUIRED_TABLES = {
    "agencies", "bookings", "users", "tickets", "ticket_links", "messages",
    "side_conversations", "side_messages", "activity_timeline", "product_bugs",
    "theme_tags", "routing_audits", "escalation_records", "export_jobs",
}


def test_all_required_tables_exist(seeded_db):
    tables = set(inspect(engine).get_table_names())
    missing = REQUIRED_TABLES - tables
    assert not missing, f"missing tables: {missing}"


def test_sqlite_pragmas_are_enforced(seeded_db):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_unique_constraints_present(seeded_db):
    inspector = inspect(engine)
    booking_uniques = {c["name"] for c in inspector.get_unique_constraints("bookings")}
    ticket_uniques = {c["name"] for c in inspector.get_unique_constraints("tickets")}
    assert booking_uniques
    assert ticket_uniques

    with pytest.raises(IntegrityError):
        from backend.database import SessionLocal

        db = SessionLocal()
        try:
            existing = db.scalar(select(Booking))
            db.add(Ticket(
                ticket_number=existing.tboh_id,  # violates unique ticket_number? use dup below
                booking_id=existing.id, agency_id=existing.agency_id, region=existing.region,
                title="duplicate number test", description="dup", priority="LOW", status="OPEN",
                queue="TEST",
            ))
            other = db.scalar(select(Ticket))
            db.add(Ticket(
                ticket_number=other.ticket_number,
                booking_id=existing.id, agency_id=existing.agency_id, region=existing.region,
                title="duplicate ticket number", description="dup", priority="LOW",
                status="OPEN", queue="TEST",
            ))
            db.commit()
        finally:
            db.rollback()
            db.close()


def test_foreign_keys_are_enforced(seeded_db):
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        db.add(Ticket(
            ticket_number="TCK-BADFK", booking_id=999999, agency_id=999999, region="APAC",
            title="bad fk", description="bad fk", priority="LOW", status="OPEN", queue="X",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_indexes_exist_on_hot_paths(seeded_db):
    inspector = inspect(engine)
    ticket_indexes = {i["name"] for i in inspector.get_indexes("tickets")}
    assert any("status" in name for name in ticket_indexes)
    assert any("booking" in name for name in ticket_indexes)
    assert any("created_at" in name for name in ticket_indexes)

    message_indexes = {i["name"] for i in inspector.get_indexes("messages")}
    assert message_indexes


def test_soft_delete_columns_present(seeded_db):
    inspector = inspect(engine)
    for table in ("tickets", "bookings", "agencies", "users"):
        columns = {c["name"] for c in inspector.get_columns(table)}
        assert "is_deleted" in columns, table


def test_ticket_dates_are_timezone_aware(seeded_db):
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        ticket = db.scalar(select(Ticket))
        assert ticket.created_at.tzinfo is not None
        booking = db.scalar(select(Booking))
        assert booking.check_in.tzinfo is not None
        assert booking.lcd.tzinfo is not None
    finally:
        db.close()


def test_ticket_links_are_unique_per_triple(seeded_db):
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        link = db.scalar(select(TicketLink))
        assert link is not None
        db.add(TicketLink(
            source_ticket_id=link.source_ticket_id,
            target_ticket_id=link.target_ticket_id,
            link_type=link.link_type,
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()
