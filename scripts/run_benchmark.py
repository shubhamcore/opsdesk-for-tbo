"""Measured benchmark for OpsDesk.

Every number in the output comes from this run on this machine — nothing is
copied from a spec. Re-run with the API up:

    python -m scripts.run_benchmark
"""
from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "benchmark_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEMO_PASSWORD = "OpsDesk#2026"


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarise(label: str, samples: list[float]) -> dict:
    return {
        "operation": label,
        "samples": len(samples),
        "min_ms": round(min(samples), 2),
        "median_ms": round(statistics.median(samples), 2),
        "p95_ms": round(percentile(samples, 95), 2),
        "max_ms": round(max(samples), 2),
        "mean_ms": round(statistics.fmean(samples), 2),
    }


def login(client: httpx.Client) -> str:
    response = client.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "nisha.verma@tbo.com", "password": DEMO_PASSWORD},
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> int:
    results: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor_count": platform.os.cpu_count() if hasattr(platform, "os") else None,
        },
        "sections": {},
    }

    with httpx.Client(timeout=120.0) as client:
        token = login(client)
        headers = {"Authorization": f"Bearer {token}"}

        health = client.get(f"{BASE_URL}/api/health").json()
        results["dataset"] = health.get("counts")
        results["classifier_mode"] = health.get("classifier", {}).get("mode")

        # ---------------------------------------------------------- API latency
        endpoints = [
            ("GET /api/tickets (queue list)", "/api/tickets"),
            ("GET /api/analytics/queue", "/api/analytics/queue"),
            ("GET /api/analytics/product-intelligence", "/api/analytics/product-intelligence"),
            ("GET /api/analytics/bug-suggestions", "/api/analytics/bug-suggestions"),
            ("GET /api/routing/board", "/api/routing/board"),
            ("GET /api/escalations/queue", "/api/escalations/queue"),
        ]
        latency = []
        for label, path in endpoints:
            samples = []
            for _ in range(7):
                started = time.perf_counter()
                response = client.get(f"{BASE_URL}{path}", headers=headers)
                response.raise_for_status()
                samples.append((time.perf_counter() - started) * 1000)
            latency.append(summarise(label, samples))
        results["sections"]["api_latency"] = latency

        # ------------------------------------------------- routing over tickets
        tickets = client.get(f"{BASE_URL}/api/tickets", headers=headers).json()["tickets"]
        open_tickets = [t for t in tickets if t["status"] not in {"RESOLVED", "CLOSED"}][:12]
        comparator_samples = []
        scored_rows = 0
        for ticket in open_tickets:
            started = time.perf_counter()
            response = client.get(
                f"{BASE_URL}/api/routing/tickets/{ticket['ticket_number']}/comparator", headers=headers
            )
            response.raise_for_status()
            comparator_samples.append((time.perf_counter() - started) * 1000)
            scored_rows += len(response.json().get("candidates", []) or [])
        results["sections"]["routing_comparator"] = {
            **summarise("GET /api/routing/tickets/{id}/comparator", comparator_samples),
            "candidates_scored": scored_rows,
            "candidates_per_call": round(scored_rows / max(1, len(open_tickets)), 2),
        }

        # ------------------------------------------------------- classification
        descriptions = [t["description"] for t in tickets if t.get("description")][:40]
        classify_samples = []
        for description in descriptions:
            started = time.perf_counter()
            response = client.get(f"{BASE_URL}/api/extract", headers=headers, params={"text": description})
            response.raise_for_status()
            classify_samples.append((time.perf_counter() - started) * 1000)
        results["sections"]["extraction_stage_a"] = summarise("GET /api/extract", classify_samples)

        # -------------------------------------------------------------- export
        export_started = time.perf_counter()
        rows = 0
        columns = 0
        with client.stream(
            "POST",
            f"{BASE_URL}/api/exports/stream",
            headers={**headers, "Content-Type": "application/json"},
            json={"file_format": "CSV", "source": "SYNTHETIC_BENCHMARK", "total_rows": 50000},
        ) as response:
            response.raise_for_status()
            job_uuid = response.headers.get("X-Export-Job-Uuid")
            for chunk in response.iter_lines():
                if chunk:
                    rows += 1
                    if columns == 0:
                        columns = len(chunk.split(","))
        client_seconds = time.perf_counter() - export_started
        job = client.get(f"{BASE_URL}/api/exports/jobs/{job_uuid}", headers=headers).json()
        job = job.get("job", job)
        results["sections"]["export_stream"] = {
            "rows_requested": 50000,
            "rows_received_incl_header": rows,
            "columns": columns,
            "client_elapsed_ms": round(client_seconds * 1000, 2),
            "client_rows_per_sec": round(rows / max(0.001, client_seconds), 2),
            "server_duration_ms": job.get("duration_ms"),
            "server_rows_per_sec": job.get("throughput_rows_per_sec"),
            "file_size_mb": job.get("file_size_mb"),
            "peak_memory_mb": job.get("peak_memory_mb"),
            "job_uuid": job_uuid,
        }

        validation = client.get(f"{BASE_URL}/api/exports/{job_uuid}/validate", headers=headers).json()
        results["sections"]["export_validation"] = validation

    metrics_path = ROOT / "ai_models" / "evaluation" / "metrics.json"
    if metrics_path.exists():
        results["sections"]["classifier_evaluation"] = json.loads(metrics_path.read_text())

    (OUT_DIR / "benchmark_report.json").write_text(json.dumps(results, indent=2))

    # --------------------------------------------------------------- markdown
    lines = [
        "# OpsDesk — Measured Benchmark",
        "",
        f"Generated: {results['generated_at']}",
        f"Environment: Python {results['environment']['python']} on {results['environment']['platform']}",
        f"Dataset: {results.get('dataset')} · classifier mode: {results.get('classifier_mode')}",
        "",
        "Every figure below was measured in this run against the live API. No values are estimates.",
        "",
        "## API latency (7 sequential calls each)",
        "",
        "| Operation | n | min ms | median ms | p95 ms | max ms |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in results["sections"]["api_latency"]:
        lines.append(
            f"| {row['operation']} | {row['samples']} | {row['min_ms']} | {row['median_ms']} | {row['p95_ms']} | {row['max_ms']} |"
        )

    routing = results["sections"]["routing_comparator"]
    lines += [
        "",
        "## Routing comparator",
        "",
        f"- Calls: {routing['samples']} · median {routing['median_ms']} ms · p95 {routing['p95_ms']} ms",
        f"- Candidates scored per call: {routing['candidates_per_call']} (total {routing['candidates_scored']})",
        "",
        "## Extraction + classification (Stage A/B over live ticket text)",
        "",
        f"- Calls: {results['sections']['extraction_stage_a']['samples']} · "
        f"median {results['sections']['extraction_stage_a']['median_ms']} ms · "
        f"p95 {results['sections']['extraction_stage_a']['p95_ms']} ms",
        "",
        "## Export stream (50,000 rows)",
        "",
    ]
    export = results["sections"]["export_stream"]
    lines += [
        f"- Rows received by the client (incl. header): {export['rows_received_incl_header']:,}",
        f"- Columns: {export['columns']}",
        f"- Client elapsed: {export['client_elapsed_ms']:,} ms · {export['client_rows_per_sec']:,} rows/s",
        f"- Server-measured: {export['server_duration_ms']} ms · {export['server_rows_per_sec']:,} rows/s · "
        f"{export['file_size_mb']} MB · peak {export['peak_memory_mb']} MB",
        f"- Validation: {results['sections']['export_validation'].get('result')} "
        f"({results['sections']['export_validation'].get('actual_rows_in_file'):,} rows in file)",
        "",
    ]

    evaluation = results["sections"].get("classifier_evaluation")
    if evaluation:
        lines += [
            "## Classifier evaluation (template-disjoint holdout, ai_models/evaluation/metrics.json)",
            "",
            f"- Train rows: {evaluation.get('train_samples')} · holdout rows: {evaluation.get('holdout_samples')} · "
            f"split: {evaluation.get('split')}",
            f"- Holdout accuracy: {evaluation.get('holdout_accuracy')} · macro F1: {evaluation.get('holdout_macro_f1')}",
            f"- Dataset: {evaluation.get('dataset')}",
            "",
            "| Intent | Precision | Recall | F1 | Support |",
            "| --- | --- | --- | --- | --- |",
        ]
        for intent, row in (evaluation.get("per_class") or {}).items():
            lines.append(
                f"| {intent} | {row['precision']} | {row['recall']} | {row['f1']} | {row['support']} |"
            )
        lines.append("")

    (OUT_DIR / "benchmark_report.md").write_text("\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
