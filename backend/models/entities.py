"""ORM entities — the booking-centric operational model.

A booking is the operational context; a ticket is one interaction associated
with that booking. Every mutable decision (routing, escalation, transfer) also
writes an append-only record so history cannot be rewritten.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import Base, TZDateTime, utcnow


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False, default="SILVER")
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    bookings: Mapped[list["Booking"]] = relationship(back_populates="agency")
    users: Mapped[list["User"]] = relationship(back_populates="agency")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str | None] = mapped_column(String(16))
    shift_start: Mapped[str] = mapped_column(String(5), default="00:00", nullable=False)
    shift_end: Mapped[str] = mapped_column(String(5), default="23:59", nullable=False)
    timezone: Mapped[str] = mapped_column(String(48), default="UTC", nullable=False)
    skill_rank: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_capacity: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    agency_id: Mapped[int | None] = mapped_column(ForeignKey("agencies.id"))
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)

    agency: Mapped[Agency | None] = relationship(back_populates="users")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (Index("ix_bookings_agency", "agency_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tboh_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(120), nullable=False)
    supplier_email: Mapped[str | None] = mapped_column(String(160))
    hotel_name: Mapped[str] = mapped_column(String(160), nullable=False)
    destination_country: Mapped[str] = mapped_column(String(64), nullable=False)
    destination_city: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    timezone: Mapped[str] = mapped_column(String(48), nullable=False)
    check_in: Mapped[object | None] = mapped_column(TZDateTime)
    check_out: Mapped[object | None] = mapped_column(TZDateTime)
    lcd: Mapped[object | None] = mapped_column(TZDateTime)
    booking_status: Mapped[str] = mapped_column(String(24), default="CONFIRMED", nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    passenger_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    agency: Mapped[Agency] = relationship(back_populates="bookings")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="booking")


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_booking", "booking_id"),
        Index("ix_tickets_created_at", "created_at"),
        Index("ix_tickets_queue", "queue"),
        Index("ix_tickets_intent", "intent"),
        Index("ix_tickets_assigned_user", "assigned_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("bookings.id"))
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"), nullable=False)
    assigned_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    region: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(48))
    intent_confidence: Mapped[float | None] = mapped_column(Float)
    intent_reasoning: Mapped[list | None] = mapped_column(JSON)
    intent_scores: Mapped[dict | None] = mapped_column(JSON)
    intent_source: Mapped[str | None] = mapped_column(String(16))
    extracted_tboh: Mapped[str | None] = mapped_column(String(32))
    extraction_source: Mapped[str | None] = mapped_column(String(24))
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", nullable=False)
    queue: Mapped[str] = mapped_column(String(48), default="UNASSIGNED", nullable=False)
    regional_holiday_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority_due_at: Mapped[object | None] = mapped_column(TZDateTime)
    effective_sla_due_at: Mapped[object | None] = mapped_column(TZDateTime)
    sla_rule: Mapped[str | None] = mapped_column(String(64))
    at_risk_threshold: Mapped[float] = mapped_column(Float, default=0.75, nullable=False)
    escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalated_at: Mapped[object | None] = mapped_column(TZDateTime)
    escalated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)
    resolved_at: Mapped[object | None] = mapped_column(TZDateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    booking: Mapped[Booking | None] = relationship(back_populates="tickets")
    agency: Mapped[Agency] = relationship()
    assigned_user: Mapped[User | None] = relationship(foreign_keys=[assigned_user_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    messages: Mapped[list["Message"]] = relationship(
        back_populates="ticket", order_by="Message.created_at"
    )
    side_conversations: Mapped[list["SideConversation"]] = relationship(
        back_populates="ticket", order_by="SideConversation.created_at"
    )


class TicketLink(Base):
    __tablename__ = "ticket_links"
    __table_args__ = (
        UniqueConstraint("source_ticket_id", "target_ticket_id", "link_type", name="uq_ticket_link_triple"),
        Index("ix_ticket_links_source", "source_ticket_id"),
        Index("ix_ticket_links_target", "target_ticket_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    target_ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sender_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(32), nullable=False)
    message_type: Mapped[str] = mapped_column(String(24), default="PUBLIC_REPLY", nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="messages")


class SideConversation(Base):
    __tablename__ = "side_conversations"
    __table_args__ = (Index("ix_side_conversations_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(24), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(160), nullable=False)
    explicit_recipients: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by_group: Mapped[str | None] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="side_conversations")
    messages: Mapped[list["SideMessage"]] = relationship(
        back_populates="conversation", order_by="SideMessage.created_at"
    )


class SideMessage(Base):
    __tablename__ = "side_messages"
    __table_args__ = (Index("ix_side_messages_conversation", "side_conversation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    side_conversation_id: Mapped[int] = mapped_column(
        ForeignKey("side_conversations.id"), nullable=False
    )
    sender_email: Mapped[str] = mapped_column(String(160), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), default="OUTBOUND", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="SENT", nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)

    conversation: Mapped[SideConversation] = relationship(back_populates="messages")


class ActivityTimeline(Base):
    __tablename__ = "activity_timeline"
    __table_args__ = (Index("ix_activity_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"))
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)


class RoutingAudit(Base):
    __tablename__ = "routing_audits"
    __table_args__ = (Index("ix_routing_audits_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    candidate_scores_json: Mapped[list] = mapped_column(JSON, nullable=False)
    excluded_json: Mapped[list | None] = mapped_column(JSON)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    selected_score: Mapped[float | None] = mapped_column(Float)
    decision_reason: Mapped[str] = mapped_column(String(500), nullable=False)
    tie_break_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(24), default="AUTO", nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)


class EscalationRecord(Base):
    __tablename__ = "escalation_records"
    __table_args__ = (Index("ix_escalation_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    escalated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_em_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    previous_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_queue: Mapped[str] = mapped_column(String(48), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    escalated_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)


class TicketTransfer(Base):
    __tablename__ = "ticket_transfers"
    __table_args__ = (Index("ix_transfers_ticket", "ticket_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    from_queue: Mapped[str] = mapped_column(String(48), nullable=False)
    to_queue: Mapped[str] = mapped_column(String(48), nullable=False)
    from_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    to_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    preserved_side_conversations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preserved_recipients: Mapped[list | None] = mapped_column(JSON)
    transferred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)


class ProductBug(Base):
    __tablename__ = "product_bugs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    supplier_name: Mapped[str] = mapped_column(String(120), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(48))
    frequency: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="PROPOSED", nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    related_ticket_ids: Mapped[list | None] = mapped_column(JSON)
    window_start: Mapped[object | None] = mapped_column(TZDateTime)
    window_end: Mapped[object | None] = mapped_column(TZDateTime)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)


class ThemeTag(Base):
    __tablename__ = "theme_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(48))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    distinct_suppliers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen: Mapped[object | None] = mapped_column(TZDateTime)


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    requested_by_email: Mapped[str] = mapped_column(String(160), nullable=False)
    file_format: Mapped[str] = mapped_column(String(8), default="CSV", nullable=False)
    filters_json: Mapped[dict | None] = mapped_column(JSON)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_streamed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    throughput_rows_per_sec: Mapped[float | None] = mapped_column(Float)
    peak_memory_mb: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24), default="QUEUED", nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(500))
    filters_applied: Mapped[str | None] = mapped_column(String(500))
    data_source: Mapped[str] = mapped_column(String(24), default="SYNTHETIC_BENCHMARK", nullable=False)
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow)
    completed_at: Mapped[object | None] = mapped_column(TZDateTime)


class AgentRun(Base):
    """One persisted multi-agent case review.

    The per-agent trace is stored as JSON so a run can be audited long after the
    fact without replaying it, and the plan is stored separately because that is
    what operators actually act on.
    """

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_uuid: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)
    objective: Mapped[str] = mapped_column(String(64), nullable=False, default="CASE_REVIEW")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="COMPLETED")
    agent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    agents_json: Mapped[list] = mapped_column(JSON, default=list)
    plan_json: Mapped[list] = mapped_column(JSON, default=list)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[object] = mapped_column(TZDateTime, default=utcnow, index=True)
