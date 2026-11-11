"""Headless verification of all six workspaces — screenshots, console + HTTP error capture.

Runs against the live server on http://127.0.0.1:8000. Every interaction here is
a real click against the running SPA; results land in screenshots/ and a JSON
report is written to /tmp/ui_report.json.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path("/home/user/OpsDesk/screenshots")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    problems: list[str] = []
    shots: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1560, "height": 1000}, accept_downloads=True)
        page = context.new_page()

        errors: list[str] = []
        page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
        page.on("pageerror", lambda err: errors.append(f"pageerror: {err}"))
        page.on(
            "response",
            lambda response: errors.append(f"http {response.status}: {response.url}")
            if response.status >= 400
            else None,
        )

        def shot(name: str, wait_selector: str | None = None, pause: float = 2.0) -> None:
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=25000)
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{name}: missing {wait_selector} ({exc.__class__.__name__})")
            time.sleep(pause)
            path = OUT / f"{name}.png"
            page.screenshot(path=str(path))
            shots.append(str(path))

        # ------------------------------------------------------------------ login
        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.wait_for_selector("[data-testid=login-email]", timeout=20000)
        shot("00_login", None, 1.0)
        page.fill("[data-testid=login-email]", "nisha.verma@tbo.com")
        page.fill("[data-testid=login-password]", "OpsDesk#2026")
        page.click("[data-testid=login-submit]")
        page.wait_for_url("**/w1", timeout=25000)
        page.wait_for_selector("[data-testid=kpi-compliance]", timeout=25000)
        time.sleep(1.5)

        # --------------------------------------------------------------------- W1
        shot("01_w1_ops_queue", "[data-testid=ticket-row-TCK-101]")
        for tid in (
            "kpi-active", "kpi-at-risk", "kpi-breached", "kpi-compliance", "kpi-escalated",
            "chart-sla-mix", "chart-weekly-volume", "chart-region-sla", "chart-intent-volume",
            "filter-region", "filter-priority", "filter-sla", "filter-intent",
        ):
            if page.locator(f"[data-testid={tid}]").count() == 0:
                problems.append(f"w1: missing {tid}")

        # --------------------------------------------------------------------- W2
        page.click("[data-testid=nav-w2]")
        page.wait_for_selector("[data-testid=case-search]", timeout=25000)
        page.fill("[data-testid=case-search]", "TBOH-778899")
        time.sleep(1.5)
        page.click("[data-testid=case-list-TCK-101]")
        shot("02_w2_case_workspace", "[data-testid=case-brief-card]")
        for tid in (
            "classification-card", "case-brief-card", "ticket-thread", "booking-context",
            "sla-panel", "side-conversations", "graph-panel", "transfer-button",
        ):
            if page.locator(f"[data-testid={tid}]").count() == 0:
                problems.append(f"w2: missing {tid}")

        # main thread: post an internal note
        page.fill("[data-testid=thread-input]", "Escalating with the supplier finance contact; no credit note yet.")
        page.click("[data-testid=thread-send]")
        time.sleep(2.0)

        # supplier conversation ticket
        page.fill("[data-testid=case-search]", "TCK-301")
        time.sleep(1.5)
        page.click("[data-testid=case-list-TCK-301]")
        shot("03_w2_side_conversations", "[data-testid=side-conversations]", 2.5)
        if page.locator("[data-testid=recipients-1]").count() == 0:
            problems.append("w2: missing explicit recipient chips for the supplier conversation")

        # transfer modal + verification
        page.click("[data-testid=transfer-button]")
        shot("04_w2_transfer_modal", "[data-testid=transfer-modal]", 1.0)
        page.click("[data-testid=transfer-modal] button:has-text('Transfer')")
        page.wait_for_selector("[data-testid=transfer-verification]", timeout=20000)
        shot("05_w2_transfer_verification", "[data-testid=transfer-verification]", 1.5)

        # escalation modal (on the LCD ticket)
        page.fill("[data-testid=case-search]", "TCK-402")
        time.sleep(1.5)
        page.click("[data-testid=case-list-TCK-402]")
        page.wait_for_selector("[data-testid=escalate-button]", timeout=20000)
        page.click("[data-testid=escalate-button]")
        page.fill(
            "[data-testid=escalate-reason]",
            "Check-in is within 90 minutes and the supplier has not confirmed the relocation.",
        )
        shot("06_w2_escalate_modal", "[data-testid=escalate-modal]", 0.8)
        page.click("[data-testid=escalate-submit]")
        time.sleep(2.5)

        # --------------------------------------------------------------------- W3
        page.click("[data-testid=nav-w3]")
        shot("07_w3_routing_studio", "[data-testid=agent-board]")
        for tid in ("agent-board", "formula-card", "comparator-card", "excluded-list", "audit-table"):
            if page.locator(f"[data-testid={tid}]").count() == 0:
                problems.append(f"w3: missing {tid}")
        page.click("[data-testid=comparator-route]")
        time.sleep(3.0)
        shot("08_w3_comparator", "[data-testid=comparator-card]", 1.5)

        # --------------------------------------------------------------------- W4
        page.click("[data-testid=nav-w4]")
        shot("09_w4_war_room", "[data-testid^=em-ticket-]", 2.0)

        # --------------------------------------------------------------------- W5
        page.click("[data-testid=nav-w5]")
        shot("10_w5_insights", "[data-testid=chart-intent-distribution]", 3.0)
        page.click("[data-testid=intel-tabs-bugs]")
        shot("11_w5_bug_suggestions", "[data-testid^=bug-suggestion-]", 2.0)
        page.click("[data-testid=intel-tabs-exports]")
        shot("12_w5_exports_idle", "[data-testid=export-start]", 1.0)

        # real 50,000-row streamed export
        page.fill("[data-testid=export-rows]", "50000")
        page.click("[data-testid=export-start]")
        page.wait_for_selector("[data-testid=export-validation]", timeout=180000)
        shot("13_w5_export_result", "[data-testid=export-validation]", 2.0)
        with page.expect_download(timeout=60000) as download_info:
            page.click("[data-testid=export-download]")
        download = download_info.value
        download_path = download.path()
        size = download_path.stat().st_size if download_path else 0
        if size <= 0:
            problems.append("w5: downloaded export file is empty")
        shot("14_w5_export_jobs", "[data-testid=export-jobs]", 1.0)

        # --------------------------------------------------------------------- W6
        page.click("[data-testid=nav-w6]")
        shot("15_w6_simulation_lab", "[data-testid=journey-card-A]", 2.0)
        page.click("[data-testid=journey-run-A]")
        page.wait_for_selector("[data-testid=lab-console]", timeout=25000)
        time.sleep(8)
        shot("16_w6_journey_a", "[data-testid=lab-console]", 1.5)

        # ------------------------------------------- RBAC: agency requester view
        page.click("[data-testid=role-switcher]")
        time.sleep(0.8)
        page.click('[data-testid="identity-maya.requester@wanderlust-travels.com"]')
        time.sleep(3.5)
        shot("17_w2_agency_requester", "[data-testid=case-search]", 1.5)
        if page.locator("[data-testid=nav-w3]").count() != 0:
            problems.append("rbac: agency requester can still see the routing workspace")

        # ------------------------------------------------- EM view of the war room
        page.click("[data-testid=role-switcher]")
        time.sleep(0.8)
        page.click('[data-testid="identity-elena.rossi@tbo.com"]')
        time.sleep(3.5)
        shot("18_w4_escalation_manager", "[data-testid^=em-ticket-]", 2.0)

        context.close()
        browser.close()

    report = {"shots": shots, "problems": problems, "console_errors": errors}
    Path("/tmp/ui_report.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                "shots": len(shots),
                "problems": problems,
                "error_count": len(errors),
                "errors": errors[:10],
            },
            indent=2,
        )
    )
    return 0 if not problems and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
