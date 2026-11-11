"""Module 4 — travel-aware dynamic SLA.

EffectiveSLADueAt = MIN(PriorityDeadline, LCD − 2h, CheckIn − 4h)

Missing travel dates are skipped, never coerced to zero/epoch. A travel
deadline that is already in the past is reported explicitly
(``expired_travel_deadline``) instead of being silently ignored.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

HEALTHY = "HEALTHY"
AT_RISK = "AT_RISK"
BREACHED = "BREACHED"
RESOLVED = "RESOLVED"

PRIORITY_SLA_HOURS = {"CRITICAL": 1, "HIGH": 4, "MEDIUM": 12, "LOW": 24}
LCD_BUFFER_HOURS = 2
CHECKIN_BUFFER_HOURS = 4
DEFAULT_AT_RISK_THRESHOLD = 0.75
HOLIDAY_AT_RISK_THRESHOLD = 0.50

PRIORITY_URGENCY = {"CRITICAL": 1.0, "HIGH": 0.85, "MEDIUM": 0.70, "LOW": 0.40}

TRAVEL_DEADLINE_RULES = ("LCD_DEADLINE", "CHECK_IN_DEADLINE")


@dataclass
class SLAResult:
    state: str
    governing_rule: str
    effective_due_at: datetime
    priority_due_at: datetime
    lcd_deadline: datetime | None
    checkin_deadline: datetime | None
    at_risk_threshold: float
    elapsed_ratio: float
    seconds_remaining: float
    minutes_remaining: float
    holiday_adjustment_applied: bool
    expired_travel_deadline: bool
    missing_dates: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "effective_due_at": self.effective_due_at,
            "priority_due_at": self.priority_due_at,
            "lcd_deadline": self.lcd_deadline,
            "checkin_deadline": self.checkin_deadline,
            "governing_rule": self.governing_rule,
            "at_risk_threshold": self.at_risk_threshold,
            "elapsed_ratio": round(self.elapsed_ratio, 4),
            "seconds_remaining": int(self.seconds_remaining),
            "minutes_remaining": int(self.minutes_remaining),
            "holiday_adjustment_applied": self.holiday_adjustment_applied,
            "expired_travel_deadline": self.expired_travel_deadline,
            "missing_dates": self.missing_dates,
            "reasons": self.reasons,
        }


def _aware(value: datetime | None, label: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware (UTC storage)")
    return value.astimezone(timezone.utc)


def compute_sla(
    *,
    created_at: datetime,
    priority: str,
    lcd: datetime | None = None,
    check_in: datetime | None = None,
    regional_holiday_flag: bool = False,
    now: datetime | None = None,
    status: str | None = None,
) -> SLAResult:
    created_at = _aware(created_at, "created_at")
    lcd = _aware(lcd, "lcd")
    check_in = _aware(check_in, "check_in")
    now = _aware(now, "now") or datetime.now(timezone.utc)

    priority = (priority or "MEDIUM").upper()
    sla_hours = PRIORITY_SLA_HOURS.get(priority, PRIORITY_SLA_HOURS["MEDIUM"])
    priority_due_at = created_at + timedelta(hours=sla_hours)

    reasons: list[str] = [f"Priority SLA governs: {priority} = {sla_hours}h from creation"]
    missing: list[str] = []

    lcd_deadline = None
    if lcd is not None:
        lcd_deadline = lcd - timedelta(hours=LCD_BUFFER_HOURS)
    else:
        missing.append("lcd")

    checkin_deadline = None
    if check_in is not None:
        checkin_deadline = check_in - timedelta(hours=CHECKIN_BUFFER_HOURS)
    else:
        missing.append("check_in")

    candidates: list[tuple[datetime, str]] = [(priority_due_at, "PRIORITY_SLA")]
    if lcd_deadline is not None:
        candidates.append((lcd_deadline, "LCD_DEADLINE"))
    if checkin_deadline is not None:
        candidates.append((checkin_deadline, "CHECK_IN_DEADLINE"))

    effective_due_at, governing_rule = min(candidates, key=lambda item: item[0])

    expired_travel_deadline = False
    if governing_rule == "LCD_DEADLINE":
        reasons = [
            f"Last Cancellation Date governs: LCD {lcd.isoformat()} minus "
            f"{LCD_BUFFER_HOURS}h buffer"
        ]
    elif governing_rule == "CHECK_IN_DEADLINE":
        reasons = [
            f"Check-in governs: {check_in.isoformat()} minus {CHECKIN_BUFFER_HOURS}h buffer"
        ]
    if governing_rule in TRAVEL_DEADLINE_RULES and effective_due_at <= now:
        expired_travel_deadline = True
        reasons.append(
            "A travel deadline (LCD/check-in buffer) is already in the past for this booking"
        )
    if missing:
        reasons.append(
            "Travel dates missing ("
            + ", ".join(missing)
            + ") — skipped, not defaulted to zero"
        )

    threshold = DEFAULT_AT_RISK_THRESHOLD
    holiday_applied = False
    if regional_holiday_flag:
        threshold = HOLIDAY_AT_RISK_THRESHOLD
        holiday_applied = True
        reasons.append(
            "Regional holiday: AT_RISK warning threshold lowered from 75% to 50% elapsed"
        )

    total = (effective_due_at - created_at).total_seconds()
    remaining = (effective_due_at - now).total_seconds()
    elapsed_ratio = 1.0 if total <= 0 else (now - created_at).total_seconds() / total

    if status == "RESOLVED":
        state = RESOLVED
    elif remaining < 0:
        state = BREACHED
    elif elapsed_ratio >= threshold:
        state = AT_RISK
    else:
        state = HEALTHY

    return SLAResult(
        state=state,
        governing_rule=governing_rule,
        effective_due_at=effective_due_at,
        priority_due_at=priority_due_at,
        lcd_deadline=lcd_deadline,
        checkin_deadline=checkin_deadline,
        at_risk_threshold=threshold,
        elapsed_ratio=elapsed_ratio,
        seconds_remaining=remaining,
        minutes_remaining=remaining / 60.0,
        holiday_adjustment_applied=holiday_applied,
        expired_travel_deadline=expired_travel_deadline,
        missing_dates=missing,
        reasons=reasons,
    )


def urgency_weight(sla: SLAResult, priority: str) -> float:
    """Urgency multiplier used by routing.

    AT_RISK and BREACHED saturate to 1.0; otherwise the priority baseline is
    lifted by how much of the window has already elapsed.
    """
    if sla.state in (AT_RISK, BREACHED):
        return 1.0
    if sla.state == RESOLVED:
        return 0.0
    baseline = PRIORITY_URGENCY.get((priority or "MEDIUM").upper(), 0.70)
    return round(min(1.0, max(baseline, sla.elapsed_ratio)), 4)
