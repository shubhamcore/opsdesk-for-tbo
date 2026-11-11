# Explainer — Storyboard

**File:** `Explainer.mp4` · 1440×900 · H.264 · 25 fps · **104.96 s** · 7 scenes × 15 s
**Subtitles:** `Explainer.srt` (cue per scene)
**Built by:** `python -m scripts.run_Automated_Demo --only explainer`
(scene cards rendered with Playwright at `videos/cards/scene_XX.png`, then assembled with FFmpeg)

Each scene pairs a dark narrative panel (left, 43 %) with a **real screenshot of the running product**
(right). Nothing on screen is a mock-up of a feature that does not exist.

| # | In | Out | Title | On-screen text | Screenshot used |
| --- | --- | --- | --- | --- | --- |
| 1 | 00:00 | 00:15 | The problem | "Ticket-centric tools treat each interaction in isolation — the agent loses the operational context." | `02_w2_case_workspace.png` |
| 2 | 00:15 | 00:30 | One booking, one case | "Ticket creation extracts the TBO booking id from free text, then links the case." | `02_w2_case_workspace.png` |
| 3 | 00:30 | 00:45 | Understanding the intent | "TF-IDF + logistic regression, calibrated · holdout 0.8958 accuracy / 0.8964 macro F1 (n=288)." | `10_w5_insights.png` |
| 4 | 00:45 | 01:00 | Routing you can audit | "35 / 25 / 25 / 15 out of 100, with every term stored and every exclusion explained." | `07_w3_routing_studio.png` |
| 5 | 01:00 | 01:15 | SLA that respects travel | "MIN(priority deadline, LCD − 2h, check-in − 4h) · holiday threshold 75% → 50%." | `01_w1_ops_queue.png` |
| 6 | 01:15 | 01:30 | Conversations stay independent | "Transfers move the queue and owner only — recipients verified unchanged." | `03_w2_side_conversations.png` |
| 7 | 01:30 | 01:45 | From operations to product | "Recurring supplier patterns become bug proposals with evidence · 50,000 rows stream in ~1.2 s." | `13_w5_export_result.png` |

## Visual system

- Left panel `#0B1D33`, kicker `#5B95F7` at 16 px uppercase with 0.14 em tracking.
- Headline 52 px, body 19 px `#CBD5E1`, square bullets `#2563EB`.
- Right panel white with a 14 px-radius screenshot, `0 24px 60px rgba(15,37,64,.18)` shadow.
- Corner label: "Synthetic demo data · real running system".
- No logo animation, no music bed, no transition effects — scenes hard-cut so the SRT stays frame-accurate.

## Editing notes

- Re-cut with the same 15 s cadence and `Explainer.srt` stays valid; changing scene length means
  regenerating the SRT (the script derives cue timings from the scene list).
- To add music or narration, mux the audio without touching video timing (see
  `Video_Production_Guide.md`).
