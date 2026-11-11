"""Module tests — travel-aware dynamic SLA."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.sla import (
    AT_RISK,
    BREACHED,
    DEFAULT_AT_RISK_THRESHOLD,
    HEALTHY,
    HOLIDAY_AT_RISK_THRESHOLD,
    RESOLVED,
    compute_sla,
    urgency_weight,
)

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def test_priority_sla_applies_when_no_travel_dates():
    result = compute_sla(created_at=NOW - timedelta(minutes=30), priority="CRITICAL", now=NOW)
    assert result.governing_rule == "PRIORITY_SLA"
    assert result.effective_due_at == NOW - timedelta(minutes=30) + timedelta(hours=1)
    assert result.state == HEALTHY
    assert set(result.missing_dates) == {"lcd", "check_in"}


def test_lcd_deadline_overrides_priority():
    created = NOW - timedelta(minutes=150)
    lcd = NOW + timedelta(minutes=175)  # LCD-2h = +55 min
    result = compute_sla(created_at=created, priority="HIGH", lcd=lcd, now=NOW)
    assert result.governing_rule == "LCD_DEADLINE"
    assert result.effective_due_at == lcd - timedelta(hours=2)
    # priority due (+90 min) is later than the LCD deadline (+55 min) → LCD wins
    assert result.priority_due_at > result.effective_due_at


def test_checkin_deadline_overrides_priority():
    created = NOW - timedelta(minutes=30)
    check_in = NOW + timedelta(hours=3)
    result = compute_sla(created_at=created, priority="HIGH", check_in=check_in, now=NOW)
    assert result.governing_rule == "CHECK_IN_DEADLINE"
    assert result.effective_due_at == check_in - timedelta(hours=4)


def test_minimum_of_all_candidates_is_used():
    created = NOW - timedelta(hours=2)
    lcd = NOW + timedelta(hours=6)          # deadline +4h
    check_in = NOW + timedelta(hours=5)     # deadline +1h  ← smallest
    result = compute_sla(created_at=created, priority="HIGH", lcd=lcd, check_in=check_in, now=NOW)
    assert result.governing_rule == "CHECK_IN_DEADLINE"
    assert result.effective_due_at == min(result.priority_due_at, result.lcd_deadline,
                                          result.checkin_deadline)


def test_missing_dates_are_skipped_not_zeroed():
    """A missing LCD must not produce an epoch timestamp."""
    result = compute_sla(created_at=NOW - timedelta(hours=1), priority="MEDIUM",
                         lcd=None, check_in=None, now=NOW)
    assert result.lcd_deadline is None
    assert result.checkin_deadline is None
    assert result.effective_due_at > NOW
    assert "lcd" in result.missing_dates


def test_expired_travel_deadline_is_reported_not_ignored():
    result = compute_sla(
        created_at=NOW - timedelta(hours=2), priority="CRITICAL",
        check_in=NOW + timedelta(minutes=90), now=NOW,
    )
    assert result.governing_rule == "CHECK_IN_DEADLINE"
    assert result.expired_travel_deadline is True
    assert result.state == BREACHED
    assert any("already in the past" in reason for reason in result.reasons)


def test_breached_when_deadline_passed():
    result = compute_sla(created_at=NOW - timedelta(hours=5), priority="HIGH", now=NOW)
    assert result.state == BREACHED
    assert result.seconds_remaining < 0


def test_at_risk_threshold_default_75_percent():
    created = NOW - timedelta(hours=3)
    result = compute_sla(created_at=created, priority="HIGH", now=NOW)  # 3h of 4h = 75%
    assert result.at_risk_threshold == DEFAULT_AT_RISK_THRESHOLD
    assert result.state == AT_RISK


def test_regional_holiday_lowers_threshold_to_50_percent():
    created = NOW - timedelta(hours=2, minutes=30)  # 62.5% of a 4h SLA
    normal = compute_sla(created_at=created, priority="HIGH", now=NOW)
    holiday = compute_sla(created_at=created, priority="HIGH", regional_holiday_flag=True, now=NOW)

    assert normal.at_risk_threshold == 0.75
    assert holiday.at_risk_threshold == HOLIDAY_AT_RISK_THRESHOLD == 0.50
    assert normal.state == HEALTHY
    assert holiday.state == AT_RISK
    assert holiday.holiday_adjustment_applied is True
    assert any("holiday" in reason.lower() for reason in holiday.reasons)


def test_resolved_status_wins_over_clock():
    result = compute_sla(created_at=NOW - timedelta(days=3), priority="LOW",
                         now=NOW, status="RESOLVED")
    assert result.state == RESOLVED


def test_timezone_awareness_enforced():
    naive = datetime(2026, 11, 9, 12, 0)  # no tzinfo
    with pytest.raises(ValueError):
        compute_sla(created_at=naive, priority="HIGH", now=NOW)


def test_urgency_weight_behaviour():
    fresh_critical = compute_sla(created_at=NOW, priority="CRITICAL", now=NOW)
    assert urgency_weight(fresh_critical, "CRITICAL") == 1.0
    fresh_low = compute_sla(created_at=NOW, priority="LOW", now=NOW)
    assert urgency_weight(fresh_low, "LOW") == pytest.approx(0.4)  # capped by proximity
    at_risk = compute_sla(created_at=NOW - timedelta(hours=11), priority="MEDIUM", now=NOW)
    assert at_risk.state == AT_RISK
    assert urgency_weight(at_risk, "MEDIUM") == 1.0


# ---------------------------------------------------------------- API level


def test_tck_401_governed_by_lcd(client, auth):
    response = client.get("/api/tickets", headers=auth("agent"), params={"search": "TCK-401"})
    ticket = next(t for t in response.json()["tickets"] if t["ticket_number"] == "TCK-401")
    sla = ticket["sla"]
    assert sla["governing_rule"] == "LCD_DEADLINE"
    assert sla["state"] in ("AT_RISK", "BREACHED")
    assert sla["holiday_adjustment_applied"] is True
    assert sla["at_risk_threshold"] == 0.5


def test_tck_402_reports_expired_checkin_deadline(client, auth):
    response = client.get("/api/tickets", headers=auth("agent"), params={"search": "TCK-402"})
    ticket = next(t for t in response.json()["tickets"] if t["ticket_number"] == "TCK-402")
    assert ticket["sla"]["governing_rule"] == "CHECK_IN_DEADLINE"
    assert ticket["sla"]["expired_travel_deadline"] is True


def test_sla_matrix_endpoint(client, auth):
    response = client.get("/api/sla/matrix", headers=auth("agent"))
    assert response.status_code == 200
    matrix = response.json()
    assert matrix["priority_hours"] == {"CRITICAL": 1, "HIGH": 4, "MEDIUM": 12, "LOW": 24}
    assert matrix["lcd_buffer_hours"] == 2
    assert matrix["checkin_buffer_hours"] == 4
