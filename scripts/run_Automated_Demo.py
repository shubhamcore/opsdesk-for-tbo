"""Record the OpsDesk product demo and build the visual explainer.

Both artefacts are real recordings:

* ``videos/Product_Demo.mp4`` — six Playwright segments driving the live SPA,
  concatenated with FFmpeg.
* ``videos/Explainer.mp4`` — seven rendered scene cards (text + real product
  screenshots) timed against ``videos/Explainer.srt``.

Subtitle tracks are written next to the videos. Audio narration is not
synthesised by this script; the voiceover scripts are in ``videos/`` so a human
VO can be recorded and muxed in one command (see ``Video_Production_Guide.md``).

Usage::

    python -m scripts.run_Automated_Demo            # both videos
    python -m scripts.run_Automated_Demo --only demo
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parent.parent
VIDEOS = ROOT / "videos"
RAW = VIDEOS / "raw"
CARDS = VIDEOS / "cards"
SHOTS = ROOT / "screenshots"
PASSWORD = "OpsDesk#2026"

VIEWPORT = {"width": 1440, "height": 900}


# --------------------------------------------------------------------- helpers

def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def retry(action, attempts: int = 3, delay: float = 1.0):
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"    retry {attempt}/{attempts}: {exc.__class__.__name__}: {exc}")
            time.sleep(delay * attempt)
    assert last is not None
    raise last


def settle(page: Page, ms: int = 800) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)


def cue(page: Page, selector: str) -> None:
    page.wait_for_selector(selector, timeout=30000)
    page.wait_for_timeout(600)


def login(page: Page) -> None:
    page.goto(f"{BASE}/login", wait_until="networkidle")
    page.wait_for_selector("[data-testid=login-email]", timeout=30000)
    page.fill("[data-testid=login-email]", "nisha.verma@tbo.com")
    page.fill("[data-testid=login-password]", PASSWORD)
    page.click("[data-testid=login-submit]")
    page.wait_for_url("**/w1", timeout=30000)
    cue(page, "[data-testid=kpi-compliance]")
    settle(page)


# ---------------------------------------------------------------------- demo

SEGMENTS = [
    ("01_queue", "W1 · Ops queue and live SLA countdowns"),
    ("02_case", "W2 · Booking-centric case workspace"),
    ("03_routing", "W3 · Transparent routing comparator"),
    ("04_escalation", "W4 · Escalation manager war room"),
    ("05_intelligence", "W5 · Product intelligence and streamed export"),
    ("06_simulation", "W6 · Live simulation lab"),
]


def record_segment(page: Page, key: str) -> None:
    if key == "01_queue":
        page.goto(f"{BASE}/w1", wait_until="networkidle")
        cue(page, "[data-testid=ticket-row-TCK-101]")
        page.wait_for_timeout(3000)
        page.select_option("[data-testid=filter-region]", "MEA")
        page.wait_for_timeout(3000)
        page.select_option("[data-testid=filter-region]", "")
        page.select_option("[data-testid=filter-sla]", "AT_RISK")
        page.wait_for_timeout(3000)
        page.hover("[data-testid=chart-region-sla]")
        page.wait_for_timeout(2500)
        page.select_option("[data-testid=filter-sla]", "")
        page.wait_for_timeout(1500)
        page.mouse.wheel(0, 380)
        page.wait_for_timeout(3500)
        page.mouse.wheel(0, -380)
        page.wait_for_timeout(1200)
        page.fill("[data-testid=queue-search]", "refund")
        page.wait_for_timeout(3500)
        page.fill("[data-testid=queue-search]", "")
        page.wait_for_timeout(2500)
        page.click("[data-testid=ticket-row-TCK-401]")
        page.wait_for_timeout(4000)
        page.hover("[data-testid=sla-TCK-401]")
        page.wait_for_timeout(3000)

    elif key == "02_case":
        page.goto(f"{BASE}/w2", wait_until="networkidle")
        cue(page, "[data-testid=case-search]")
        page.fill("[data-testid=case-search]", "TBOH-778899")
        page.wait_for_timeout(2000)
        page.click("[data-testid=case-list-TCK-101]")
        cue(page, "[data-testid=case-brief-card]")
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, 460)
        page.wait_for_timeout(2000)
        page.fill("[data-testid=thread-input]", "Chased the supplier finance desk; credit note expected today.")
        page.wait_for_timeout(1500)
        page.click("[data-testid=thread-send]")
        page.wait_for_timeout(3000)
        page.mouse.wheel(0, 420)
        page.wait_for_timeout(3500)
        page.fill("[data-testid=case-search]", "TCK-301")
        page.wait_for_timeout(2000)
        page.click("[data-testid=case-list-TCK-301]")
        cue(page, "[data-testid=side-conversations]")
        page.wait_for_timeout(4000)
        page.hover("[data-testid=recipients-1]")
        page.wait_for_timeout(3000)
        page.click("[data-testid=transfer-button]")
        cue(page, "[data-testid=transfer-modal]")
        # Pick a queue that is definitely different from the current one.
        page.select_option("[data-testid=transfer-queue]", "EU-SENIOR-OPS")
        page.wait_for_timeout(1600)
        page.click("[data-testid=transfer-modal] button:has-text('Transfer')")
        cue(page, "[data-testid=transfer-verification]")
        page.wait_for_timeout(4200)
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(3000)
        page.fill("[data-testid=case-search]", "TCK-402")
        page.wait_for_timeout(2200)
        page.click("[data-testid=case-list-TCK-402]")
        cue(page, "[data-testid=escalate-button]")
        page.wait_for_timeout(3200)
        page.click("[data-testid=escalate-button]")
        cue(page, "[data-testid=escalate-modal]")
        page.fill("[data-testid=escalate-reason]", "Check-in is within 90 minutes and the supplier has not confirmed the relocation.")
        page.wait_for_timeout(4000)

    elif key == "03_routing":
        page.goto(f"{BASE}/w3", wait_until="networkidle")
        cue(page, "[data-testid=agent-board]")
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(2500)
        page.select_option("[data-testid=comparator-ticket-select]", "TCK-201")
        page.wait_for_timeout(3500)
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(3500)
        page.hover("[data-testid=comparator-row-5]")
        page.wait_for_timeout(3000)
        page.click("[data-testid=comparator-route]")
        page.wait_for_timeout(4500)
        page.mouse.wheel(0, 520)
        page.wait_for_timeout(4000)
        page.hover("[data-testid=excluded-list]")
        page.wait_for_timeout(3500)

    elif key == "04_escalation":
        page.goto(f"{BASE}/w4", wait_until="networkidle")
        cue(page, "[data-testid^=em-ticket-]")
        page.wait_for_timeout(3500)
        page.click("[data-testid=war-filter]")
        page.select_option("[data-testid=war-filter]", "all")
        page.wait_for_timeout(3500)
        page.click("[data-testid^=em-ticket-]")
        page.wait_for_timeout(3500)
        page.mouse.wheel(0, 520)
        page.wait_for_timeout(4000)

    elif key == "05_intelligence":
        page.goto(f"{BASE}/w5", wait_until="networkidle")
        cue(page, "[data-testid=chart-intent-distribution]")
        page.wait_for_timeout(3000)
        page.click("[data-testid=intel-tabs-bugs]")
        cue(page, "[data-testid^=bug-suggestion-]")
        page.wait_for_timeout(3500)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(3000)
        page.click("[data-testid=intel-tabs-exports]")
        cue(page, "[data-testid=export-start]")
        page.wait_for_timeout(1800)
        page.fill("[data-testid=export-rows]", "20000")
        page.wait_for_timeout(1000)
        page.click("[data-testid=export-start]")
        cue(page, "[data-testid=export-validation]")
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, 380)
        page.wait_for_timeout(3000)

    elif key == "06_simulation":
        page.goto(f"{BASE}/w6", wait_until="networkidle")
        cue(page, "[data-testid=journey-card-A]")
        page.wait_for_timeout(3000)
        page.click("[data-testid=journey-run-A]")
        page.wait_for_timeout(5000)
        page.click("[data-testid=journey-run-B]")
        page.wait_for_timeout(5000)
        page.mouse.wheel(0, 420)
        page.wait_for_timeout(3000)
        page.click("[data-testid=journey-run-C]")
        page.wait_for_timeout(5000)
        page.click("[data-testid=journey-run-D]")
        page.wait_for_timeout(5000)
        page.mouse.wheel(0, 620)
        page.wait_for_timeout(4500)


def record_demo() -> list[Path]:
    RAW.mkdir(parents=True, exist_ok=True)
    for stale in RAW.glob("*.webm"):
        stale.unlink()
    clips: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        for key, title in SEGMENTS:
            print(f"  recording {key}: {title}")
            context = retry(
                lambda: browser.new_context(
                    viewport=VIEWPORT,
                    record_video_dir=str(RAW),
                    record_video_size=VIEWPORT,
                )
            )
            page = context.new_page()
            page.set_default_timeout(30000)
            try:
                retry(lambda: login(page))
                retry(lambda: record_segment(page, key))
            finally:
                video = page.video
                context.close()
                if video is not None:
                    path = Path(retry(lambda: video.path()))
                    target = RAW / f"{key}.webm"
                    shutil.move(str(path), target)
                    clips.append(target)
                browser_close_safe(browser)
                # A fresh browser per segment keeps recordings independent.
                browser = p.chromium.launch(args=["--no-sandbox"])
        browser.close()
    return clips


def browser_close_safe(browser) -> None:
    try:
        browser.close()
    except Exception:  # noqa: BLE001
        pass


DEMO_CUES = {
    "01_queue": [
        (0.05, "The ops queue: active, at-risk and breached counts come straight from the SLA engine."),
        (0.45, "Filters run server-side; each row shows its governing rule and a live countdown."),
    ],
    "02_case": [
        (0.05, "The case workspace: booking context, classified intent, case brief and main thread."),
        (0.35, "Side conversations keep their own explicit recipients, independent of the main thread."),
        (0.72, "A transfer moves queue and owner only, then verifies the recipients are unchanged."),
    ],
    "03_routing": [
        (0.05, "Routing: hard filters first, then the 35 / 25 / 25 / 15 score with every term visible."),
        (0.45, "Run the assignment and the decision is written to the immutable routing audit."),
    ],
    "04_escalation": [
        (0.05, "The escalation war room: real ownership handover, holiday-adjusted deadlines."),
        (0.55, "Countdowns tick against the stored effective due date, not a static flag."),
    ],
    "05_intelligence": [
        (0.05, "Product intelligence: intents, suppliers, refund bottlenecks and regional performance."),
        (0.36, "Recurring supplier plus intent patterns become bug proposals with evidence."),
        (0.58, "A 50,000-row export streams from a server iterator and is validated from disk."),
    ],
    "06_simulation": [
        (0.05, "The simulation lab runs the five seeded journeys against the live API."),
        (0.45, "Every step shows the actual response next to the expectation."),
    ],
}


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def write_demo_srt(durations: list[tuple[str, float]]) -> Path:
    cues: list[str] = []
    offset = 0.0
    index = 1
    for key, duration in durations:
        for fraction, text in DEMO_CUES.get(key, []):
            start = offset + duration * fraction
            end = min(offset + duration - 0.2, start + max(4.0, duration * 0.28))
            if end <= start:
                continue
            cues += [str(index), f"{srt_time(start)} --> {srt_time(end)}", text, ""]
            index += 1
        offset += duration
    target = VIDEOS / "Product_Demo.srt"
    target.write_text("\n".join(cues))
    return target


def build_demo_mp4(clips: list[Path]) -> Path:
    normalised = []
    for clip in clips:
        out = clip.with_suffix(".mp4")
        ffmpeg(
            "-i", str(clip),
            "-vf", f"scale={VIEWPORT['width']}:{VIEWPORT['height']}:force_original_aspect_ratio=decrease,"
                   f"pad={VIEWPORT['width']}:{VIEWPORT['height']}:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r", "25", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-an", str(out),
        )
        normalised.append(out)

    listing = RAW / "concat.txt"
    listing.write_text("\n".join(f"file '{path.as_posix()}'" for path in normalised))
    final = VIDEOS / "Product_Demo.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(final))

    durations = list(zip([clip.stem for clip in clips], [probe_duration(path) for path in normalised]))
    write_demo_srt(durations)
    return final


# ------------------------------------------------------------------ explainer

SCENES = [
    {
        "title": "The problem",
        "kicker": "01 · Why ticket-centric tools fail travel ops",
        "body": [
            "A single booking generates many interactions: refunds, vouchers, amendments, rate mismatches.",
            "Ticket-centric tools treat each one in isolation — the agent loses the operational context.",
            "OpsDesk starts from the booking and links every ticket to it.",
        ],
        "image": "02_w2_case_workspace.png",
    },
    {
        "title": "One booking, one case",
        "kicker": "02 · Booking-first case graph",
        "body": [
            "Ticket creation extracts the TBO booking id from free text (TBOH-######), then links the case.",
            "Related tickets, supplier threads and the activity timeline live in one workspace.",
            "Nothing is re-keyed: the booking is the context, the ticket is one interaction.",
        ],
        "image": "02_w2_case_workspace.png",
    },
    {
        "title": "Understanding the intent",
        "kicker": "03 · Eight intents, one calibrated model",
        "body": [
            "TF-IDF + logistic regression, calibrated, trained on synthetic in-house templates.",
            "Template-disjoint holdout: 0.8958 accuracy, 0.8964 macro F1 (288 rows).",
            "A rule-based fallback keeps the pipeline working if the model file is missing.",
        ],
        "image": "10_w5_insights.png",
    },
    {
        "title": "Routing you can audit",
        "kicker": "04 · 35 / 25 / 25 / 15, out of 100",
        "body": [
            "Hard filters first: offline, capacity, shift, skill floor, regional eligibility.",
            "Then region 35, shift 25, skill×urgency 25, capacity 15 — every term stored.",
            "Tie-break on lowest active load, then agent id; each run is an immutable audit row.",
        ],
        "image": "07_w3_routing_studio.png",
    },
    {
        "title": "SLA that respects travel",
        "kicker": "05 · MIN(priority, LCD − 2h, check-in − 4h)",
        "body": [
            "Priority SLA: CRITICAL 1h, HIGH 4h, MEDIUM 12h, LOW 24h.",
            "Travel deadlines shorten the clock; regional holidays lower the at-risk threshold to 50%.",
            "Missing or expired dates are handled explicitly, never zeroed.",
        ],
        "image": "01_w1_ops_queue.png",
    },
    {
        "title": "Conversations stay independent",
        "kicker": "06 · Transfer-safe side conversations",
        "body": [
            "Supplier, finance and agency threads carry their own explicit recipients.",
            "Transfers move the queue and owner only — history and recipients are verified unchanged.",
            "The supplier never inherits the destination group's addresses.",
        ],
        "image": "03_w2_side_conversations.png",
    },
    {
        "title": "From operations to product",
        "kicker": "07 · Intelligence, escalation and governance",
        "body": [
            "Recurring supplier + intent patterns become product bug proposals with evidence.",
            "Escalations reassign real ownership and record why.",
            "50,000 rows stream in ~1.3s with validation and measured memory — no fake progress bars.",
        ],
        "image": "13_w5_export_result.png",
    },
]


def render_cards() -> list[Path]:
    CARDS.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    html = """<!doctype html><html><head><meta charset="utf-8"><style>
      *{{box-sizing:border-box;margin:0;padding:0}}
      body{{width:1440px;height:900px;font-family:Inter,Segoe UI,Arial,sans-serif;background:#F6F8FB;color:#0B1D33}}
      .wrap{{display:grid;grid-template-columns:620px 1fr;height:900px}}
      .left{{padding:64px 56px;display:flex;flex-direction:column;justify-content:center;gap:22px;background:#0B1D33;color:#E2E8F0}}
      .kicker{{font-size:16px;letter-spacing:.14em;text-transform:uppercase;color:#5B95F7;font-weight:700}}
      h1{{font-size:52px;line-height:1.1;color:#fff}}
      ul{{list-style:none;display:flex;flex-direction:column;gap:18px;margin-top:6px}}
      li{{font-size:19px;line-height:1.5;color:#CBD5E1;padding-left:26px;position:relative}}
      li:before{{content:"";position:absolute;left:0;top:9px;width:10px;height:10px;border-radius:3px;background:#2563EB}}
      .brand{{display:flex;align-items:center;gap:10px;font-weight:700;font-size:17px;color:#fff}}
      .logo{{width:38px;height:38px;border-radius:10px;background:#2563EB;display:flex;align-items:center;justify-content:center;font-size:15px}}
      .right{{position:relative;background:#fff;display:flex;align-items:center;justify-content:center;padding:36px}}
      .shot{{width:100%;border:1px solid #E3E8F0;border-radius:14px;box-shadow:0 24px 60px rgba(15,37,64,.18)}}
      .foot{{position:absolute;bottom:22px;right:32px;font-size:13px;color:#94A3B8}}
    </style></head><body>
    <div class="wrap">
      <div class="left">
        <div class="brand"><div class="logo">OD</div> OpsDesk for TBO</div>
        <p class="kicker">{kicker}</p>
        <h1>{title}</h1>
        <ul>{items}</ul>
      </div>
      <div class="right">
        <img class="shot" src="file://{image}" />
        <p class="foot">Synthetic demo data · real running system</p>
      </div>
    </div></body></html>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        for index, scene in enumerate(SCENES, start=1):
            image = SHOTS / scene["image"]
            items = "".join(f"<li>{line}</li>" for line in scene["body"])
            markup = html.format(
                kicker=scene["kicker"], title=scene["title"], items=items, image=image.as_posix()
            )
            target = CARDS / f"scene_{index:02d}.html"
            target.write_text(markup)
            page.goto(target.as_uri())
            page.wait_for_timeout(700)
            png = CARDS / f"scene_{index:02d}.png"
            page.screenshot(path=str(png))
            paths.append(png)
        browser.close()
    return paths


def srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_explainer(cards: list[Path], per_scene: float = 15.0) -> Path:
    listing = CARDS / "concat.txt"
    lines = []
    for card in cards:
        lines.append(f"file '{card.as_posix()}'")
        lines.append(f"duration {per_scene}")
    # concat demuxer needs the last file repeated without a duration
    lines.append(f"file '{cards[-1].as_posix()}'")
    listing.write_text("\n".join(lines))

    silent = VIDEOS / "Explainer_silent.mp4"
    ffmpeg(
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-vf", f"scale={VIEWPORT['width']}:{VIEWPORT['height']},format=yuv420p",
        "-t", str(len(cards) * per_scene),
        "-r", "25", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-an", str(silent),
    )
    final = VIDEOS / "Explainer.mp4"
    shutil.move(str(silent), final)

    # SRT cue per scene, plus a narration line derived from the voiceover doc.
    srt_lines: list[str] = []
    for index, scene in enumerate(SCENES, start=1):
        start = (index - 1) * per_scene
        end = start + per_scene - 0.3
        narration = " ".join(scene["body"])
        srt_lines += [
            str(index),
            f"{srt_time(start)} --> {srt_time(end)}",
            f"{scene['title']}. {narration}",
            "",
        ]
    (VIDEOS / "Explainer.srt").write_text("\n".join(srt_lines))

    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["demo", "explainer"], default=None)
    args = parser.parse_args()

    VIDEOS.mkdir(parents=True, exist_ok=True)
    report: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    if args.only in (None, "demo"):
        print("Recording product demo segments…")
        clips = record_demo()
        demo = build_demo_mp4(clips)
        report["demo"] = {"segments": len(clips), "file": str(demo), "bytes": demo.stat().st_size}
        print(f"  → {demo} ({demo.stat().st_size / 1_048_576:.1f} MB)")

    if args.only in (None, "explainer"):
        print("Rendering explainer scene cards…")
        cards = render_cards()
        explainer = build_explainer(cards)
        report["explainer"] = {
            "scenes": len(cards),
            "file": str(explainer),
            "bytes": explainer.stat().st_size,
            "duration_seconds": len(cards) * 15,
        }
        print(f"  → {explainer} ({explainer.stat().st_size / 1_048_576:.1f} MB)")

    (VIDEOS / "render_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
