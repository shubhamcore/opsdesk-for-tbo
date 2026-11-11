"""Run all five journeys end-to-end and write a JSON + markdown report."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from simulation.engine import dump, pretty
from simulation.journeys import JOURNEY_TITLES, JOURNEYS

RESULTS_DIR = Path(__file__).resolve().parents[1] / "benchmark_results"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--only", default=None, help="A,B,C,D,E")
    parser.add_argument("--export-rows", type=int, default=50000)
    args = parser.parse_args()

    keys = [k.strip().upper() for k in args.only.split(",")] if args.only else list(JOURNEYS)
    results = []
    for key in keys:
        result = JOURNEYS[key](args.base_url) if key != "E" else JOURNEYS[key](args.base_url, args.export_rows)
        results.append(result)
        print(pretty(result))
        print()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "journeys": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r["passed"]),
            "steps_total": sum(r["steps_total"] for r in results),
            "steps_passed": sum(r["steps_passed"] for r in results),
        },
    }
    dump(payload, RESULTS_DIR / "journey_results.json")

    lines = ["# Five Judging Journeys — Execution Report", "",
             f"Generated: {payload['generated_at']}", "",
             f"**{payload['summary']['passed']}/{payload['summary']['total']} journeys passed** "
             f"({payload['summary']['steps_passed']}/{payload['summary']['steps_total']} steps)", "",
             "| Journey | Title | Steps passed | Result |", "|---|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r['journey']} | {r['title']} | {r['steps_passed']}/{r['steps_total']} | "
            f"{'PASS' if r['passed'] else 'FAIL'} |"
        )
    lines.append("")
    for r in results:
        lines.append(f"## Journey {r['journey']} — {r['title']}")
        lines.append("")
        lines.append("| Step | Expected | Actual | Result |")
        lines.append("|---|---|---|---|")
        for s in r["steps"]:
            expected = s["expected"].replace("|", "/")
            actual = s["actual"].replace("|", "/")[:180]
            lines.append(f"| {s['name']} | {expected} | {actual} | {'PASS' if s['passed'] else 'FAIL'} |")
        lines.append("")
    (RESULTS_DIR / "journey_report.md").write_text("\n".join(lines))

    print(f"Summary: {payload['summary']['passed']}/{payload['summary']['total']} journeys passed")
    print(f"Written: {RESULTS_DIR / 'journey_results.json'}")
    return 0 if payload["summary"]["passed"] == payload["summary"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
