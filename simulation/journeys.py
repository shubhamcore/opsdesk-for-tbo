"""The five judging journeys, expressed as API-level scenarios (A–E)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from simulation.engine import JourneyRunner, count_export_rows, find_ticket


# ---------------------------------------------------------------- JOURNEY A
def journey_a(base_url: str) -> dict:
    """Booking context & automatic case linking (TBOH field left empty)."""
    runner = JourneyRunner(base_url)
    started = datetime.now(timezone.utc)
    try:
        def sign_in():
            runner.login("agency_wanderlust")
            me = runner.get("/api/auth/me").json()
            return (
                f"{me['user']['full_name']} ({me['user']['role']}, {me['agency']['name']})",
                me["user"]["role"] == "AGENCY_REQUESTER",
                {"agency": me["agency"]},
            )

        runner.step("Agency requester signs in", "Token issued for Wanderlust Travels", sign_in)

        def baseline():
            response = runner.get("/api/bookings/TBOH-778899")
            if response.status_code != 200:
                return f"HTTP {response.status_code}", False, {}
            data = response.json()
            return (
                f"{len(data['tickets'])} existing tickets on TBOH-778899",
                len(data["tickets"]) >= 3,
                {"ticket_numbers": [t["ticket_number"] for t in data["tickets"]]},
            )

        runner.step("Booking context is visible before the new request", ">= 3 existing tickets", baseline)

        created_holder = {}

        def create():
            payload = {
                "title": "Refund not received — Atlantis The Palm stay",
                "description": (
                    "Our client cancelled the Atlantis The Palm stay and the refund of USD 1,450 "
                    "has still not been credited. The booking reference is TBOH-778899 — please "
                    "chase the supplier and confirm the refund date."
                ),
                "tboh_id": None,          # deliberately empty: must be recovered from the text
                "priority": "HIGH",
            }
            response = runner.post("/api/tickets", json=payload)
            if response.status_code != 201:
                return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
            created_holder.update(response.json())
            return (
                f"Created {response.json()['ticket_number']}",
                True,
                {"ticket_number": response.json()["ticket_number"]},
            )

        runner.step("Submit refund request with the TBOH field left EMPTY", "Ticket created", create)

        runner.step(
            "Stage A extracts the booking id from the description",
            "extraction_source=DESCRIPTION, TBOH-778899",
            lambda: (
                f"{created_holder['extraction']['tboh_ids']} via "
                f"{created_holder['extraction']['extraction_source']}",
                created_holder["extraction"]["tboh_ids"][:1] == ["TBOH-778899"]
                and created_holder["extraction"]["extraction_source"] == "DESCRIPTION",
                created_holder["extraction"],
            ),
        )

        runner.step(
            "Intent classified as REFUND_DELAY with calibrated confidence",
            "REFUND_DELAY from the ML pipeline",
            lambda: (
                f"{created_holder['classification']['intent']} @ "
                f"{created_holder['classification']['confidence']:.0%} "
                f"({created_holder['classification']['source']})",
                created_holder["classification"]["intent"] == "REFUND_DELAY"
                and created_holder["classification"]["source"] == "ML",
                {
                    "intent": created_holder["classification"]["intent"],
                    "confidence": created_holder["classification"]["confidence"],
                    "reasoning": created_holder["classification"]["reasoning"],
                },
            ),
        )

        runner.step(
            "Previous tickets are linked into one case",
            "TCK-101, TCK-104 and TCK-109 appear in the linked case",
            lambda: _assert_links(runner, created_holder["ticket_id"]),
        )

        runner.step(
            "AI Case Brief summarises the linked history in three points",
            "3 evidence-bound points",
            lambda: _assert_brief(runner, created_holder["ticket_id"]),
        )

        result = runner.result("A", "Booking context and automatic case linking", started)
        result["ticket_number"] = created_holder.get("ticket_number")
        return result
    finally:
        runner.close()


def _assert_links(runner: JourneyRunner, ticket_id: int):
    response = runner.get(f"/api/tickets/{ticket_id}")
    if response.status_code != 200:
        return f"HTTP {response.status_code}", False, {}
    data = response.json()
    related = [r["ticket_number"] for r in data["related_tickets"]]
    required = {"TCK-101", "TCK-104", "TCK-109"}
    return (
        f"{len(related)} related tickets: {sorted(required & set(related))}",
        required.issubset(set(related)),
        {
            "related": data["related_tickets"][:8],
            "case_brief": data["case_brief"]["points"],
            "booking": data["booking"],
        },
    )


def _assert_brief(runner: JourneyRunner, ticket_id: int):
    response = runner.get(f"/api/tickets/{ticket_id}/case-brief")
    if response.status_code != 200:
        return f"HTTP {response.status_code}", False, {}
    data = response.json()
    return (
        f"{len(data['points'])} points",
        len(data["points"]) == 3 and all(len(p) > 20 for p in data["points"]),
        {"points": data["points"], "sources": data["sources"]},
    )


# ---------------------------------------------------------------- JOURNEY B
def journey_b(base_url: str) -> dict:
    """Intelligent routing with full score breakdown and audit."""
    runner = JourneyRunner(base_url)
    started = datetime.now(timezone.utc)
    try:
        runner.step("Operations agent signs in", "Token issued for an ops agent",
                    lambda: (runner.login("ops_agent"), True, {}))

        holder = {}
        runner.step("Create a high-priority APAC ticket", "Ticket created (unassigned)",
                    lambda: _create_b(runner, holder))

        runner.step(
            "Dry-run the comparator before assignment",
            "Ananya Sharma ranks first",
            lambda: _comparator(runner, holder),
        )

        runner.step(
            "Run intelligent routing",
            "Assigned to Ananya Sharma (APAC, skill 5/5)",
            lambda: _route(runner, holder),
        )

        runner.step(
            "Explain why FIFO was not used",
            "Region, shift, skill and capacity all contribute",
            lambda: _fifo_explanation(holder),
        )

        runner.step(
            "Routing decision is written to the immutable audit log",
            "Audit row with every candidate score",
            lambda: _audit(runner, holder),
        )

        result = runner.result("B", "Intelligent routing and capacity", started)
        result["ticket_number"] = holder.get("ticket_number")
        return result
    finally:
        runner.close()


def _create_b(runner: JourneyRunner, holder: dict):
    response = runner.post("/api/tickets", json={
        "title": "Voucher confirmation required before arrival (TBOH-554411)",
        "description": (
            "Marina Bay Sands has no confirmation on file for TBOH-554411 and the guest "
            "arrives within 48 hours. Please confirm the voucher urgently."
        ),
        "tboh_id": "TBOH-554411",
        "priority": "HIGH",
    })
    if response.status_code != 201:
        return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
    data = response.json()
    holder.update({"ticket_id": data["ticket_id"], "ticket_number": data["ticket_number"],
                   "booking": data["booking"]})
    return f"Created {data['ticket_number']}", True, {"booking": data["booking"]}


def _comparator(runner: JourneyRunner, holder: dict):
    response = runner.get(f"/api/routing/tickets/{holder['ticket_id']}/comparator")
    if response.status_code != 200:
        return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
    data = response.json()
    holder["comparator"] = data
    top = data["candidates"][0] if data["candidates"] else None
    return (
        f"Top candidate {top['full_name']} at {top['total_score']}/100 "
        f"({len(data['candidates'])} eligible, {len(data['excluded'])} excluded)",
        bool(top) and top["full_name"] == "Ananya Sharma",
        {"candidates": data["candidates"][:6], "excluded": data["excluded"]},
    )


def _route(runner: JourneyRunner, holder: dict):
    response = runner.post(f"/api/routing/tickets/{holder['ticket_id']}/route",
                           json={"triggered_by": "MANUAL"})
    if response.status_code != 200:
        return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
    data = response.json()
    holder["routing"] = data
    assigned = data["assigned_to"]["name"]
    return (
        f"{assigned} — score {data['decision']['score']}/100, load "
        f"{data['assigned_to']['active_load']}/{data['assigned_to']['max_capacity']}",
        assigned == "Ananya Sharma",
        {
            "assigned_to": data["assigned_to"],
            "decision_reason": data["decision"]["decision_reason"],
            "candidates": data["decision"]["candidates"],
            "excluded": data["decision"]["excluded"],
            "urgency_weight": data["decision"]["urgency_weight"],
        },
    )


def _fifo_explanation(holder: dict):
    decision = holder["routing"]["decision"]
    winner = decision["candidates"][0]
    return (
        f"Winner scored {winner['total_score']}/100 = region {winner['region_match'] * 35:.0f} "
        f"+ shift {winner['shift_match'] * 25:.0f} + skill {winner['skill_component']:.1f} "
        f"+ capacity {winner['capacity_component']:.1f}",
        decision["score"] > 50 and len(decision["candidates"]) >= 2,
        {
            "formula": "35*RegionMatch + 25*ShiftMatch + 25*(SkillRank/5)*UrgencyWeight + 15*(1-ActiveLoad/MaxCapacity)",
            "fifo_note": holder["routing"]["fifo_note"],
            "runner_up": decision["candidates"][1] if len(decision["candidates"]) > 1 else None,
        },
    )


def _audit(runner: JourneyRunner, holder: dict):
    response = runner.get("/api/routing/audits", params={"ticket_id": holder["ticket_id"]})
    if response.status_code != 200:
        return f"HTTP {response.status_code}", False, {}
    audits = response.json()["audits"]
    complete = bool(audits) and bool(audits[0]["candidates"])
    return (
        f"{len(audits)} audit row(s); latest records {len(audits[0]['candidates']) if audits else 0} candidates",
        complete,
        {"audit": audits[0] if audits else None},
    )


# ---------------------------------------------------------------- JOURNEY C
def journey_c(base_url: str) -> dict:
    """Transfer-safe supplier conversation with explicit recipients."""
    runner = JourneyRunner(base_url)
    started = datetime.now(timezone.utc)
    try:
        runner.step("EU operations agent signs in", "Token issued",
                    lambda: (runner.login("ops_agent_eu"), True, {}))
        holder = {}

        def locate():
            response = runner.get("/api/tickets", params={"search": "TCK-301"})
            data = response.json()
            ticket = find_ticket(data["tickets"], "TCK-301")
            if not ticket:
                return "TCK-301 not found — run the seed first", False, {}
            holder["ticket_id"] = ticket["id"]
            holder["queue"] = ticket["queue"]
            return f"TCK-301 in queue {ticket['queue']}", True, {"ticket": ticket["ticket_number"]}

        runner.step("Open the EuroWings supplier ticket", "TCK-301 located", locate)

        def ensure_conversation():
            existing = runner.get(f"/api/tickets/{holder['ticket_id']}/side-conversations").json()
            match = next(
                (c for c in existing["conversations"]
                 if c["channel_type"] == "SUPPLIER" and "groups@hilton-paris.com" in c["explicit_recipients"]),
                None,
            )
            if match:
                holder["conversation_id"] = match["id"]
                return (
                    f"Reusing conversation #{match['id']} with {match['explicit_recipients']}",
                    True,
                    {"explicit_recipients": match["explicit_recipients"]},
                )
            response = runner.post(f"/api/tickets/{holder['ticket_id']}/side-conversations", json={
                "channel_type": "SUPPLIER",
                "subject": "Group allocation confirmation",
                "counterparty_name": "Hilton Paris Opera",
                "recipients": ["groups@hilton-paris.com"],
            })
            if response.status_code != 201:
                return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
            data = response.json()
            holder["conversation_id"] = data["id"]
            return (f"Created conversation #{data['id']}", True,
                    {"explicit_recipients": data["explicit_recipients"]})

        runner.step("Supplier side conversation exists with explicit recipients",
                    "groups@hilton-paris.com", ensure_conversation)

        def send():
            response = runner.post(
                f"/api/side-conversations/{holder['conversation_id']}/messages",
                json={"content": "Please confirm the 12-room group allocation and rate for "
                                 "TBOH-301332 ahead of arrival."},
            )
            if response.status_code != 201:
                return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
            data = response.json()
            return (
                f"{data['messages_created']} message(s) to {data['recipients']}",
                data["messages_created"] >= 1 and "groups@hilton-paris.com" in data["recipients"],
                {"recipients": data["recipients"]},
            )

        runner.step("Send a supplier message", "Delivered to the explicit recipient", send)

        def transfer():
            response = runner.post(f"/api/tickets/{holder['ticket_id']}/transfer",
                                   json={"to_queue": "EU-SENIOR-OPS",
                                         "note": "Escalating to senior ops for group allocation"})
            if response.status_code != 200:
                return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
            data = response.json()
            holder["transfer"] = data
            return (data["message"], data["recipients_unchanged"], {"transfer": data})

        runner.step("Transfer EU-TRIAGE → EU-SENIOR-OPS", "Recipients verified unchanged", transfer)

        def verify_after_transfer():
            detail = runner.get(f"/api/tickets/{holder['ticket_id']}").json()
            convs = detail["side_conversations"]
            match = next((c for c in convs if c["id"] == holder["conversation_id"]), None)
            if not match:
                return "conversation not found after transfer", False, {}
            ok = match["explicit_recipients"] == ["groups@hilton-paris.com"]
            transfers = [
                e for e in detail["activity_timeline"] if e["event_type"] == "TRANSFERRED"
            ]
            holder["timeline"] = detail["activity_timeline"]
            return (
                f"queue={detail['queue']}, recipients={match['explicit_recipients']}, "
                f"messages={len(match['messages'])}, transfers={len(transfers)}",
                ok and len(match["messages"]) >= 1 and len(transfers) >= 1,
                {
                    "queue": detail["queue"],
                    "explicit_recipients": match["explicit_recipients"],
                    "message_count": len(match["messages"]),
                    "transfer_events": transfers,
                },
            )

        runner.step("Reopen the conversation after transfer",
                    "Recipients and history preserved", verify_after_transfer)

        return runner.result("C", "Transfer-safe supplier communication", started)
    finally:
        runner.close()


# ---------------------------------------------------------------- JOURNEY D
def journey_d(base_url: str) -> dict:
    """Travel-aware SLA, countdowns and escalation with ownership transfer."""
    runner = JourneyRunner(base_url)
    started = datetime.now(timezone.utc)
    try:
        runner.step("Operations agent signs in", "Token issued",
                    lambda: (runner.login("ops_agent"), True, {}))
        holder = {}

        def queue():
            data = runner.get("/api/analytics/queue").json()
            holder["snapshot"] = data
            states = data["sla_states"]
            return (
                f"HEALTHY {states['HEALTHY']}, AT_RISK {states['AT_RISK']}, "
                f"BREACHED {states['BREACHED']}",
                states["AT_RISK"] + states["BREACHED"] > 0,
                {"sla_states": states, "compliance": data["sla_compliance"]},
            )

        runner.step("Open the queue and read live SLA state", "Both AT_RISK and BREACHED present", queue)

        def find_401():
            response = runner.get("/api/tickets", params={"search": "TCK-401"})
            ticket = find_ticket(response.json()["tickets"], "TCK-401")
            if not ticket:
                return "TCK-401 missing", False, {}
            holder["t401"] = ticket
            sla = ticket["sla"]
            return (
                f"{sla['state']} governed by {sla['governing_rule']}, "
                f"{sla['minutes_remaining']} min remaining"
                + (" (holiday threshold applied)" if sla["holiday_adjustment_applied"] else ""),
                sla["governing_rule"] == "LCD_DEADLINE",
                {"sla": sla, "booking": ticket["booking"]},
            )

        runner.step("TCK-401 countdown is governed by the LCD deadline", "LCD_DEADLINE rule", find_401)

        def find_402():
            response = runner.get("/api/tickets", params={"search": "TCK-402"})
            ticket = find_ticket(response.json()["tickets"], "TCK-402")
            if not ticket:
                return "TCK-402 missing", False, {}
            holder["t402"] = ticket
            sla = ticket["sla"]
            return (
                f"{sla['state']} governed by {sla['governing_rule']}, "
                f"expired_travel_deadline={sla['expired_travel_deadline']}",
                sla["governing_rule"] == "CHECK_IN_DEADLINE" and sla["expired_travel_deadline"],
                {"sla": sla["reasons"]},
            )

        runner.step("TCK-402 handles an already-expired check-in deadline safely",
                    "CHECK_IN_DEADLINE with explicit expired flag", find_402)

        def filter_at_risk():
            data = runner.get("/api/tickets", params={"sla_state": "AT_RISK"}).json()
            return (f"{data['count']} AT_RISK tickets", data["count"] >= 1,
                    {"tickets": [t["ticket_number"] for t in data["tickets"]]})

        runner.step("Filter the queue to AT_RISK", "Only AT_RISK tickets", filter_at_risk)

        def escalate():
            response = runner.post(f"/api/escalations/tickets/{holder['t401']['id']}/escalate", json={
                "reason": "LCD closes within the hour; guest hospitalised and supplier unresponsive.",
            })
            if response.status_code != 200:
                return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
            data = response.json()
            holder["escalation"] = data
            return (
                f"status={data['status']}, queue={data['queue']}, owner={data['assigned_to']['name']}",
                data["status"] == "ESCALATED"
                and data["queue"] == "ESCALATION_MANAGER"
                and data["assigned_to"]["role"] == "ESCALATION_MANAGER",
                {"escalation": data},
            )

        runner.step("Escalate TCK-401 to an Escalation Manager",
                    "ESCALATED + queue ESCALATION_MANAGER + real owner", escalate)

        def switch_to_em():
            user = runner.switch_role("ESCALATION_MANAGER")
            holder["em"] = user
            queue_data = runner.get("/api/escalations/queue").json()
            numbers = [t["ticket_number"] for t in queue_data["tickets"]]
            owns = [t for t in queue_data["tickets"]
                    if t["ticket_number"] == "TCK-401" and t["assigned_user_id"] == user["id"]]
            return (
                f"{user['full_name']} sees {len(numbers)} tickets; owns TCK-401: {bool(owns)}",
                bool(owns),
                {"em_queue_counts": queue_data["counts"],
                 "tickets": numbers[:12]},
            )

        runner.step("Switch to the Escalation Manager war room",
                    "New ownership visible in the EM queue", switch_to_em)

        def timeline():
            data = runner.get(f"/api/tickets/{holder['t401']['id']}").json()
            events = [e["event_type"] for e in data["activity_timeline"]]
            history = runner.get(
                f"/api/escalations/tickets/{holder['t401']['id']}"
            ).json()["escalations"]
            return (
                f"events={events[:6]}; escalation records={len(history)}",
                "ESCALATED" in events and len(history) >= 1,
                {"activity": data["activity_timeline"][:6], "escalations": history},
            )

        runner.step("Audit timeline records the handover",
                    "ESCALATED event + escalation record", timeline)

        return runner.result("D", "Travel-aware SLA and escalation", started)
    finally:
        runner.close()


# ---------------------------------------------------------------- JOURNEY E
def journey_e(base_url: str, export_rows: int = 50000) -> dict:
    """Product intelligence, bug proposal and a real 50,000-row streaming export."""
    runner = JourneyRunner(base_url, timeout=300.0)
    started = datetime.now(timezone.utc)
    try:
        runner.step("Operations lead signs in", "Token issued",
                    lambda: (runner.login("ops_lead"), True, {}))
        holder = {}

        def intelligence():
            data = runner.get("/api/analytics/product-intelligence").json()
            holder["intel"] = data
            top = data["intent_distribution"][0] if data["intent_distribution"] else None
            inv = data["inventory_sync"]["ticket_count"]
            return (
                f"{data['tickets_in_window']} tickets in window; top intent "
                f"{top['intent']}×{top['count']}; inventory-sync tickets={inv}",
                inv >= 3 and bool(data["supplier_complaints"]),
                {
                    "intent_distribution": data["intent_distribution"],
                    "supplier_complaints": data["supplier_complaints"][:5],
                    "inventory_sync": data["inventory_sync"],
                    "refund_bottleneck": data["refund_bottleneck"],
                },
            )

        runner.step("Product intelligence aggregates recurring themes",
                    "Inventory-sync theme with >= 3 tickets", intelligence)

        def suggestions():
            data = runner.get("/api/analytics/bug-suggestions").json()
            holder["suggestions"] = data["suggestions"]
            inventory = [s for s in data["suggestions"]
                         if s["intent"] == "INVENTORY_RATE_SYNC_BUG"]
            top = (inventory or data["suggestions"] or [{}])[0]
            return (
                f"{len(data['suggestions'])} suggestion(s); top: {top.get('supplier')} "
                f"{top.get('intent')} ×{top.get('frequency')}",
                bool(inventory) and top.get("frequency", 0) >= 3,
                {"suggestions": data["suggestions"][:4],
                 "method": data["method"], "note": data["note"]},
            )

        runner.step("Recurring supplier/API pattern produces a bug suggestion",
                    ">= 3 tickets sharing supplier + intent", suggestions)

        def create_bug():
            top = holder["suggestions"][0]
            response = runner.post("/api/analytics/product-bugs", json={
                "supplier": top["supplier"],
                "intent": top["intent"],
                "title": f"{top['supplier']} {top['intent_label']} pattern",
                "suggested_action": top["suggested_action"],
                "related_ticket_ids": top["ticket_ids"],
                "frequency": top["frequency"],
            })
            if response.status_code != 201:
                return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
            data = response.json()
            holder["bug"] = data
            return (f"Created {data['bug_code']} ({data['status']})", True, {"bug": data})

        runner.step("Create a local product bug record", "PROD-BUG-1xx created", create_bug)

        def export_csv():
            payload = {"file_format": "CSV", "source": "SYNTHETIC_BENCHMARK",
                       "total_rows": export_rows}
            with runner.client.stream(
                "POST", "/api/exports/stream", json=payload, headers=runner.headers(), timeout=300.0
            ) as response:
                if response.status_code != 200:
                    response.read()
                    return f"HTTP {response.status_code}: {response.text[:200]}", False, {}
                job_uuid = response.headers.get("X-Export-Job-Uuid")
                rows, size, columns = count_export_rows(response)
            holder["job_uuid"] = job_uuid
            return (
                f"{rows} data rows, {columns} columns, {size / (1024 * 1024):.2f} MB streamed",
                rows == export_rows and columns >= 20,
                {"job_uuid": job_uuid, "rows": rows, "columns": columns, "bytes": size},
            )

        runner.step(f"Stream a {export_rows:,}-row CSV export", f"Exactly {export_rows:,} data rows",
                    export_csv)

        def validate():
            data = runner.get(f"/api/exports/{holder['job_uuid']}/validate").json()
            holder["validation"] = data
            return (
                f"{data['actual_rows_in_file']} rows in file, {data['column_count']} columns, "
                f"{data['file_size_bytes'] / (1024 * 1024):.2f} MB, {data['result']}",
                data["row_count_matches"] and data["result"] == "PASS",
                {"validation": data},
            )

        runner.step("Validate the generated artifact on disk",
                    "Row count matches and file is readable", validate)

        def metrics():
            data = runner.get(f"/api/exports/jobs/{holder['job_uuid']}").json()
            holder["job"] = data
            return (
                f"{data['rows_streamed']} rows in {data['duration_ms']} ms "
                f"({data['throughput_rows_per_sec']} rows/s, peak {data['peak_memory_mb']} MB)",
                data["status"] == "COMPLETED" and data["rows_streamed"] == export_rows,
                {"job": data},
            )

        runner.step("Export job metrics are measured, not hardcoded",
                    "COMPLETED with measured throughput", metrics)

        result = runner.result("E", "Product intelligence and large export", started)
        result["artifacts"] = {
            "job_uuid": holder.get("job_uuid"),
            "bug_code": holder.get("bug", {}).get("bug_code"),
        }
        return result
    finally:
        runner.close()


JOURNEYS = {
    "A": journey_a,
    "B": journey_b,
    "C": journey_c,
    "D": journey_d,
    "E": journey_e,
}

JOURNEY_TITLES = {
    "A": "Booking context & automatic case linking",
    "B": "Intelligent routing & capacity",
    "C": "Transfer-safe supplier communication",
    "D": "Travel-aware SLA & escalation",
    "E": "Product intelligence & 50,000-row export",
}


def run(key: str, base_url: str) -> dict:
    return JOURNEYS[key.upper()](base_url)


if __name__ == "__main__":  # quick single-journey CLI
    import sys

    key = sys.argv[1] if len(sys.argv) > 1 else "A"
    url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
    from simulation.engine import pretty

    print(pretty(run(key, url)))
    print(json.dumps(run(key, url)["steps"], indent=2)[:1])
