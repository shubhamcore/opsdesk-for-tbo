"""Pydantic request models — validation happens before any business logic."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Intent = Literal[
    "REFUND_DELAY", "CANCELLATION_LCD_WAIVER", "VOUCHER_CONFIRMATION_ISSUE",
    "AMENDMENT_NAME_DATE", "INVENTORY_RATE_SYNC_BUG", "SPECIAL_REQUEST",
    "SUPPLIER_OVERBOOKING_RELOCATION", "BILLING_INVOICE_DISPUTE",
]
Priority = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
Status = Literal["OPEN", "IN_PROGRESS", "PENDING_SUPPLIER", "ESCALATED", "RESOLVED"]
Role = Literal["AGENCY_REQUESTER", "OPS_AGENT", "ESCALATION_MANAGER", "OPS_LEAD"]


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class RoleSwitchRequest(BaseModel):
    role: Role
    agency_code: str | None = None
    email: str | None = None


class DemoLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=8000)
    tboh_id: str | None = Field(default=None, max_length=32)
    priority: Priority = "MEDIUM"
    agency_id: int | None = None
    regional_holiday_flag: bool = False

    @field_validator("title", "description")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    message_type: Literal["PUBLIC_REPLY", "INTERNAL_NOTE"] = "PUBLIC_REPLY"

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class IntentOverrideRequest(BaseModel):
    intent: Intent
    note: str | None = Field(default=None, max_length=500)


class StatusUpdateRequest(BaseModel):
    status: Status


class RouteRequest(BaseModel):
    triggered_by: Literal["MANUAL", "AUTO"] = "MANUAL"


class ReassignRequest(BaseModel):
    agent_id: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)


class EscalateRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=2000)


class SideConversationCreate(BaseModel):
    channel_type: Literal["SUPPLIER", "FINANCE", "AGENCY", "INTERNAL"] = "SUPPLIER"
    subject: str = Field(min_length=3, max_length=200)
    counterparty_name: str = Field(min_length=2, max_length=160)
    recipients: list[str] = Field(min_length=1, max_length=20)


class SideMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class TransferRequest(BaseModel):
    to_queue: str = Field(min_length=2, max_length=48)
    note: str | None = Field(default=None, max_length=500)
    to_user_id: int | None = None


class ExportStreamRequest(BaseModel):
    file_format: Literal["CSV", "JSONL"] = "CSV"
    source: Literal["DB", "SYNTHETIC_BENCHMARK"] = "SYNTHETIC_BENCHMARK"
    total_rows: int = Field(default=50000, ge=1, le=200000)
    agency_id: int | None = None
    region: str | None = None
    status: Status | None = None
    intent: Intent | None = None
    priority: Priority | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class ProductBugCreate(BaseModel):
    supplier: str = Field(min_length=2, max_length=120)
    intent: Intent | None = None
    title: str = Field(min_length=4, max_length=200)
    suggested_action: str = Field(min_length=10, max_length=2000)
    related_ticket_ids: list[int] = Field(default_factory=list, max_length=200)
    frequency: int = Field(default=0, ge=0)


class AgentRunRequest(BaseModel):
    """Optional objective label for a case review run."""

    objective: str = Field(default="CASE_REVIEW", min_length=3, max_length=64)
