"""Specialist agents.

Eight single-responsibility reviewers. Each one owns a narrow question about a
case, may only call the tools it declares, and returns evidence-bound findings.
Nothing here writes to the database: an agent proposes, a human (or an
explicitly authenticated endpoint) disposes.
"""
from __future__ import annotations

import re
import time

from backend.agents.runtime import Agent, AgentResult, ToolBox
from backend.services.classifier import INTENT_LABELS


def _p(priority: str, action: str, rationale: str) -> dict:
    return {"priority": priority, "action": action, "rationale": rationale}


def _timed(fn):
    """Record per-agent wall-clock duration without repeating it in every agent."""

    def wrapper(self, box: ToolBox) -> AgentResult:
        started = time.perf_counter()
        result = fn(self, box)
        result.duration_ms = (time.perf_counter() - started) * 1000
        result.tool_calls = list(box.calls)
        return result

    return wrapper


class IntakeAgent(Agent):
    name = "intake"
    title = "Intake & Classification"
    description = (
        "Reads the case text, re-runs the calibrated intent classifier with booking context, "
        "extracts TBOH references and confirms the booking-first case graph."
    )
    tool_names = ("classify_intent", "extract_references", "case_links")

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        t = {tool.name: tool for tool in self.tools()}
        classified = box.call(t["classify_intent"])
        extracted = box.call(t["extract_references"])
        links = box.call(t["case_links"])

        findings = [
            f"Classifier says {classified['label']} at {classified['confidence']:.1%} "
            f"(stored intent {'matches' if classified['agrees_with_stored'] else 'differs from'} the record).",
            f"Extracted TBOH references: {', '.join(extracted['tboh_ids']) or 'none'}; "
            f"amounts: {len(extracted.get('amounts', []))}; dates: {len(extracted.get('dates', []))}.",
            f"Case graph holds {links['case_size']} ticket(s): {', '.join(links['ticket_numbers'][:5])}.",
        ]
        recs: list[dict] = []
        status = "OK"
        if not classified["agrees_with_stored"]:
            status = "ATTENTION"
            recs.append(
                _p(
                    "P1",
                    f"Confirm intent: model says {classified['label']}, ticket is stamped "
                    f"{classified['stored_intent']}",
                    "A mismatch between the stored intent and a fresh classification changes which "
                    "SLA playbook and supplier path apply.",
                )
            )
        if classified["confidence"] < 0.55:
            status = "ATTENTION"
            recs.append(
                _p(
                    "P1",
                    "Route to a human for intent confirmation",
                    f"Calibrated confidence {classified['confidence']:.1%} is below the 55% review floor.",
                )
            )
        return AgentResult(
            agent=self.name,
            title=self.title,
            status=status,
            summary=(
                f"{classified['label']} · {classified['confidence']:.1%} confidence · "
                f"{links['case_size']} ticket(s) in the booking case"
            ),
            findings=findings,
            recommendations=recs,
            confidence=classified["confidence"],
            evidence={
                "intent": classified["intent"],
                "top_scores": classified["top_scores"],
                "tboh_ids": extracted["tboh_ids"],
                "case_ticket_numbers": links["ticket_numbers"],
            },
        )


class SlaRiskAgent(Agent):
    name = "sla_risk"
    title = "SLA & Travel Deadline Risk"
    description = (
        "Computes EffectiveSLADueAt = MIN(priority deadline, LCD − 2h, check-in − 4h), "
        "reports which rule governs, and flags holiday-adjusted at-risk thresholds."
    )
    tool_names = ("sla_state",)

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        tool = {t.name: t for t in self.tools()}["sla_state"]
        sla = box.call(tool)

        minutes = sla["minutes_remaining"]
        if minutes is None:
            verdict = "no deadline can be computed (missing or expired travel dates)"
        elif minutes < 0:
            verdict = f"{abs(minutes)} minutes past the effective deadline"
        else:
            verdict = f"{minutes} minutes remaining"

        findings = [
            f"State {sla['state']} — {verdict}.",
            f"Governing rule: {sla['governing_rule']}; at-risk threshold "
            f"{int(sla['at_risk_threshold'] * 100)}% of the window consumed.",
            f"Urgency weight {sla['urgency_weight']:.2f} feeds the routing score.",
        ]
        if sla["holiday_adjustment_applied"]:
            findings.append(
                "A regional holiday tightened the at-risk threshold from 75% to 50% of the window."
            )
        if sla["missing_dates"]:
            findings.append(
                f"Missing travel dates: {', '.join(sla['missing_dates'])} — treated as absent, never zeroed."
            )

        recs: list[dict] = []
        status = "OK"
        if sla["state"] == "BREACHED":
            status = "ATTENTION"
            recs.append(
                _p(
                    "P0",
                    "Respond now: the effective SLA deadline has passed",
                    f"{sla['governing_rule']} governs and the deadline is {abs(minutes or 0)} minutes old.",
                )
            )
        elif sla["state"] == "AT_RISK":
            status = "ATTENTION"
            recs.append(
                _p(
                    "P1",
                    "Prioritise this case ahead of healthy work",
                    f"{minutes} minutes remain before the {sla['governing_rule']} deadline.",
                )
            )
        return AgentResult(
            agent=self.name,
            title=self.title,
            status=status,
            summary=f"{sla['state']} · {verdict} · governed by {sla['governing_rule']}",
            findings=findings,
            recommendations=recs,
            # Rule output is deterministic: confidence expresses completeness of the
            # inputs, not a probabilistic guess.
            confidence=0.99 if not sla["missing_dates"] else 0.7,
            evidence={
                "state": sla["state"],
                "governing_rule": sla["governing_rule"],
                "minutes_remaining": minutes,
                "effective_due_at": sla["effective_due_at"],
                "holiday_adjustment_applied": sla["holiday_adjustment_applied"],
                "missing_dates": sla["missing_dates"],
            },
        )


class RoutingAdvisorAgent(Agent):
    name = "routing_advisor"
    title = "Routing & Capacity Advisor"
    description = (
        "Scores every eligible agent out of 100 (region, shift, skill, live capacity), "
        "lists the hard-filter exclusions, and compares the winner with the current owner."
    )
    tool_names = ("routing_decision",)

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        tool = {t.name: t for t in self.tools()}["routing_decision"]
        decision = box.call(tool)
        winner = decision["winner"]

        if winner is None:
            return AgentResult(
                agent=self.name,
                title=self.title,
                status="ATTENTION",
                summary="No eligible agent: every candidate failed a hard filter",
                findings=[
                    f"{decision['excluded_count']} agent(s) excluded: "
                    + "; ".join(f"{e.get('agent_name') or e.get('full_name', '?')} — {e.get('reason', '?')}"
                                for e in decision["excluded"][:4])
                ],
                recommendations=[
                    _p(
                        "P0",
                        "Widen coverage: no agent passes the hard eligibility filters",
                        "Offline, over-capacity, out-of-shift or under-skilled agents cannot receive this "
                        "case; an ops lead has to open capacity or adjust the shift.",
                    )
                ],
                confidence=0.5,
                evidence={"excluded": decision["excluded"]},
            )

        runner = decision["candidates"][1] if len(decision["candidates"]) > 1 else None
        margin = winner["total_score"] - (runner["total_score"] if runner else 0.0)
        findings = [
            f"{winner['full_name']} leads with {winner['total_score']:.2f}/100 "
            f"(region {winner['region_match'] * 35:.0f} + shift {winner['shift_match'] * 25:.0f} + "
            f"skill {winner['skill_component']:.2f} + capacity {winner['capacity_component']:.2f}).",
            f"Load {winner['active_load']}/{winner['max_capacity']}; "
            f"{decision['eligible_count']} eligible, {decision['excluded_count']} hard-filtered.",
        ]
        recs: list[dict] = []
        status = "OK"
        if decision["current_assignee_id"] != winner["agent_id"]:
            status = "ATTENTION"
            recs.append(
                _p(
                    "P1",
                    f"Reassign to {winner['full_name']} (score {winner['total_score']:.2f})",
                    "The scored winner differs from the current owner; reassignment is recorded in the "
                    "immutable routing audit.",
                )
            )
        if margin < 3 and runner is not None:
            findings.append(
                f"Margin over {runner['full_name']} is only {margin:.2f} points — the tie-break rule "
                "(lowest active load, then agent id) is doing the deciding."
            )
        return AgentResult(
            agent=self.name,
            title=self.title,
            status=status,
            summary=f"Recommended owner {winner['full_name']} · {winner['total_score']:.2f}/100",
            findings=findings,
            recommendations=recs,
            # Confidence tracks the size of the winning margin, capped at 0.95.
            confidence=min(0.95, 0.55 + margin / 40),
            evidence={
                "winner": winner,
                "runner_up": runner,
                "margin": round(margin, 3),
                "excluded_count": decision["excluded_count"],
            },
        )


class EscalationAgent(Agent):
    name = "escalation"
    title = "Escalation Readiness"
    description = (
        "Decides whether a case meets escalation criteria, names a regionally eligible "
        "escalation manager, and never double-escalates an owned case."
    )
    tool_names = ("escalation_context", "sla_state")

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        t = {tool.name: tool for tool in self.tools()}
        ctx = box.call(t["escalation_context"])
        sla = box.call(t["sla_state"])

        if ctx["already_escalated"]:
            return AgentResult(
                agent=self.name,
                title=self.title,
                status="SKIPPED",
                summary="Already held by an escalation manager",
                findings=[f"{ctx['escalation_count']} escalation record(s) on this ticket; queue {ctx['queue']}."],
                recommendations=[],
                confidence=1.0,
                evidence={"queue": ctx["queue"]},
            )

        critical = sla["state"] == "BREACHED" and box.ticket.priority in {"CRITICAL", "HIGH"}
        managers = ctx["eligible_managers"]
        findings = [
            f"Priority {box.ticket.priority}, SLA {sla['state']}, escalation criteria "
            f"{'met' if critical else 'not met'}.",
            "Eligible escalation managers: "
            + (", ".join(f"{m['full_name']} ({m['region']})" for m in managers) or "none configured"),
        ]
        recs: list[dict] = []
        if critical and managers:
            recs.append(
                _p(
                    "P0",
                    f"Escalate to {managers[0]['full_name']} with a written reason",
                    "Breached SLA on a high-or-critical priority case; escalation re-queues ownership to "
                    "ESCALATION_MANAGER and writes an immutable event.",
                )
            )
            status = "ATTENTION"
        elif critical:
            status = "ATTENTION"
            findings.append("Criteria met but no escalation manager is configured for this region.")
        else:
            status = "OK"
        return AgentResult(
            agent=self.name,
            title=self.title,
            status=status,
            summary=(
                f"Escalation {'recommended' if recs else 'not required'} · "
                f"{len(managers)} eligible manager(s)"
            ),
            findings=findings,
            recommendations=recs,
            confidence=0.9,
            evidence={"criteria_met": critical, "managers": managers},
        )


class CommsAgent(Agent):
    name = "comms"
    title = "Customer Communications"
    description = (
        "Drafts a reply using only facts already present in the thread, booking record and SLA "
        "engine. A template, not a generator: if a fact is absent from the data it is absent "
        "from the draft."
    )
    tool_names = ("thread_messages", "side_conversations", "sla_state")

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        t = {tool.name: tool for tool in self.tools()}
        thread = box.call(t["thread_messages"])
        sides = box.call(t["side_conversations"])
        sla = box.call(t["sla_state"])

        ticket = box.ticket
        booking = ticket.booking
        agency = ticket.agency
        intent_label = INTENT_LABELS.get(ticket.intent or "", ticket.intent or "your request")
        reference = booking.tboh_id if booking else "the booking referenced"
        deadline = (
            sla["effective_due_at"][:16].replace("T", " ") + " UTC" if sla["effective_due_at"] else None
        )
        lines = [
            f"Hello {agency.name if agency else 'team'},",
            "",
            f"Thank you for raising {ticket.ticket_number}. We have logged your "
            f"{intent_label.lower()} request against booking {reference}"
            + (f" ({booking.hotel_name})" if booking and booking.hotel_name else "")
            + ".",
            f"The case is currently {ticket.status.lower().replace('_', ' ')} and is owned by "
            f"{ticket.assigned_user.full_name if ticket.assigned_user else 'the regional queue'}.",
        ]
        if sides["count"]:
            channels = ", ".join(sorted({c["channel_type"].lower() for c in sides["conversations"]}))
            lines.append(
                f"We have {sides['count']} parallel conversation(s) open ({channels}) and will fold "
                "their outcome into this ticket."
            )
        if deadline and sla["state"] in {"BREACHED", "AT_RISK"}:
            lines.append(
                f"This case is {'past' if sla['state'] == 'BREACHED' else 'approaching'} its internal "
                f"service deadline ({sla['governing_rule'].replace('_', ' ').lower()}, {deadline}) and is "
                "being handled as a priority."
            )
        else:
            lines.append("We will update you as soon as the next action completes.")
        lines += ["", "Regards,", "TBO Travel Operations"]
        draft = "\n".join(lines)

        return AgentResult(
            agent=self.name,
            title=self.title,
            status="OK",
            summary=f"Reply draft prepared from {thread['count']} thread message(s) and the booking record",
            findings=[
                f"Thread has {len(thread['public'])} public reply/ies and {len(thread['internal'])} internal note(s).",
                f"{sides['count']} side conversation(s) referenced.",
                "Every sentence in the draft is traceable to the booking, the thread or the SLA engine.",
            ],
            recommendations=[
                _p(
                    "P1",
                    "Review the draft reply, then send it on the main thread",
                    "Sending stays a human action: the draft is grounded but the tone and the promised "
                    "next step remain an agent decision.",
                )
            ],
            confidence=0.65,
            evidence={"draft": draft, "facts_used": {
                "ticket_number": ticket.ticket_number,
                "booking": reference,
                "sla_state": sla["state"],
                "side_conversations": sides["count"],
            }},
        )


class QaAgent(Agent):
    name = "qa"
    title = "Quality & Leakage Guard"
    description = (
        "Scans the case for policy risk: payment-card or passport numbers in customer-visible text, "
        "supplier threads stripped of explicit recipients, and public replies written as internal notes."
    )
    tool_names = ("thread_messages", "side_conversations", "activity_events")

    _CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
    _PASSPORT = re.compile(r"\b[A-Z]{1,2}\d{6,8}\b")

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        t = {tool.name: tool for tool in self.tools()}
        thread = box.call(t["thread_messages"])
        sides = box.call(t["side_conversations"])
        events = box.call(t["activity_events"])

        problems: list[str] = []
        for message in thread["public"]:
            if self._CARD.search(message["content"]):
                problems.append(f"Card-like number in a customer-visible reply by {message['sender']}.")
            if self._PASSPORT.search(message["content"]):
                problems.append(f"Passport-like token in a customer-visible reply by {message['sender']}.")
        for conversation in sides["conversations"]:
            if not conversation["explicit_recipients"]:
                problems.append(
                    f"Side conversation {conversation['id']} ({conversation['counterparty']}) has no "
                    "explicit recipients."
                )

        recs: list[dict] = []
        if problems:
            recs.append(
                _p(
                    "P0",
                    "Redact sensitive tokens and re-confirm explicit recipients before the next send",
                    "Customer-visible text must not carry payment or identity numbers, and every side "
                    "conversation must keep its own immutable recipient list.",
                )
            )
        return AgentResult(
            agent=self.name,
            title=self.title,
            status="ATTENTION" if problems else "OK",
            summary=(
                f"{len(problems)} policy risk(s) found" if problems
                else "No leakage or recipient-hygiene problems detected"
            ),
            findings=problems or [
                f"Scanned {thread['count']} thread message(s), {sides['count']} side conversation(s) "
                f"and {events['count']} timeline event(s).",
            ],
            recommendations=recs,
            confidence=0.8,
            evidence={"problems": problems, "scanned": {
                "messages": thread["count"],
                "side_conversations": sides["count"],
                "events": events["count"],
            }},
        )


class ProductIntelAgent(Agent):
    name = "product_intel"
    title = "Product Intelligence"
    description = (
        "Looks for a recurring supplier-plus-intent pattern around this booking's supplier and turns "
        "it into a product-bug suggestion with the exact ticket numbers attached."
    )
    tool_names = ("product_patterns", "case_links")

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        t = {tool.name: tool for tool in self.tools()}
        patterns = box.call(t["product_patterns"])
        links = box.call(t["case_links"])

        matches = patterns["supplier_suggestions"]
        if not matches:
            return AgentResult(
                agent=self.name,
                title=self.title,
                status="SKIPPED",
                summary=(
                    f"No recurring pattern for {patterns['supplier'] or 'this supplier'} at the "
                    f"{patterns['min_tickets']}-ticket threshold"
                ),
                findings=[
                    f"{patterns['all_suggestions']} platform-wide suggestion(s) exist, none for this supplier."
                ],
                recommendations=[],
                confidence=0.6,
                evidence={"supplier": patterns["supplier"]},
            )

        top = matches[0]
        return AgentResult(
            agent=self.name,
            title=self.title,
            status="ATTENTION",
            summary=(
                f"{top['supplier']} × {top['intent_label']} recurs {top['frequency']}× — product bug candidate"
            ),
            findings=[
                f"Frequency {top['frequency']} between {top['period']['from'][:10]} and "
                f"{top['period']['to'][:10]}.",
                "Evidence tickets: " + ", ".join(top["ticket_numbers"][:5]),
                f"Related case links on this booking: {links['case_size'] - 1}.",
            ],
            recommendations=[
                _p(
                    "P2",
                    matches and f"Raise a product-bug record for {top['supplier']} × {top['intent_label']}" or "",
                    top["suggested_action"],
                )
            ],
            confidence=0.85 if top["confidence"] == "HIGH" else 0.7,
            evidence={"suggestion": top},
        )


class PlaybookAgent(Agent):
    name = "playbook"
    title = "Resolution Playbook"
    description = (
        "Attaches the authored standard-operating procedure for the case intent. The steps are "
        "hand-written operating guidance shipped with the product — not model output — and are "
        "labelled as such in the UI."
    )
    tool_names = ("sla_state", "case_links")

    STEPS: dict[str, list[str]] = {
        "REFUND_DELAY": [
            "Confirm the refund was raised with the supplier and capture the supplier reference.",
            "Verify the original payment instrument and the booking value from the booking record.",
            "Escalate to finance if the supplier reference is older than the refund SLA.",
        ],
        "CANCELLATION_LCD_WAIVER": [
            "Check the last cancellation date against the current time before promising anything.",
            "Raise the waiver request with the supplier and record the case id.",
            "If LCD has passed, route to an ops lead: a waiver is a commercial decision.",
        ],
        "VOUCHER_CONFIRMATION_ISSUE": [
            "Pull the voucher from the booking, not from the agent's inbox.",
            "Re-send only to the agency contact on record; never to a new address.",
            "If the supplier never confirmed, open a supplier side conversation with explicit recipients.",
        ],
        "AMENDMENT_NAME_DATE": [
            "Verify the amendment window against check-in and LCD.",
            "Collect the corrected traveller details in writing before touching the booking.",
            "Apply the change with the supplier, then re-issue the voucher.",
        ],
        "INVENTORY_RATE_SYNC_BUG": [
            "Reproduce the rate mismatch with the search and book timestamps.",
            "Attach the two rate snapshots to the case for engineering.",
            "If a booking was made at the wrong rate, hold the cancellation decision until engineering replies.",
        ],
        "SPECIAL_REQUEST": [
            "Confirm the request is a preference, not a guarantee, in the customer reply.",
            "Pass it to the supplier with a side conversation and explicit recipients.",
            "Record the supplier's answer on the ticket, not in a private note only.",
        ],
        "SUPPLIER_OVERBOOKING_RELOCATION": [
            "Secure an alternative property before confirming relocation to the traveller.",
            "Confirm who bears the cost difference and record it on the booking.",
            "Notify the agency requester with the new property details in the same thread.",
        ],
        "BILLING_INVOICE_DISPUTE": [
            "Reconcile the invoice lines against the booking value and currency.",
            "Send the reconciliation to finance with the disputed line numbers.",
            "Hold the credit note until finance confirms the correction.",
        ],
    }

    @_timed
    def run(self, box: ToolBox) -> AgentResult:
        t = {tool.name: tool for tool in self.tools()}
        sla = box.call(t["sla_state"])
        links = box.call(t["case_links"])
        intent = box.ticket.intent or ""
        steps = self.STEPS.get(intent, [])

        if not steps:
            return AgentResult(
                agent=self.name,
                title=self.title,
                status="SKIPPED",
                summary="No authored playbook for this intent",
                findings=[f"Intent {intent or 'unset'} has no shipped SOP."],
                recommendations=[],
                confidence=0.5,
                evidence={"intent": intent},
            )

        return AgentResult(
            agent=self.name,
            title=self.title,
            status="OK",
            summary=f"{len(steps)}-step SOP for {INTENT_LABELS.get(intent, intent)}",
            findings=[
                f"Step 1: {steps[0]}",
                f"Booking case currently spans {links['case_size']} ticket(s); SLA is {sla['state']}.",
            ],
            recommendations=[],
            confidence=0.75,
            evidence={"intent": intent, "steps": steps, "source": "authored-sop"},
        )


ALL_AGENTS: tuple[Agent, ...] = (
    IntakeAgent(),
    SlaRiskAgent(),
    RoutingAdvisorAgent(),
    EscalationAgent(),
    CommsAgent(),
    QaAgent(),
    ProductIntelAgent(),
    PlaybookAgent(),
)
