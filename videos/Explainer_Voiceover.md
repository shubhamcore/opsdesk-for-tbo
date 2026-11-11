# Explainer — Voiceover Script

Target: **90–120 seconds** at a calm pace (≈2.5 words/second).
Recorded audio should be 104–110 s and muxed against `Explainer.mp4` (104.96 s); the guide in
`Video_Production_Guide.md` has the exact `ffmpeg` command.

> Narration is **not** bundled with the shipped video. `Explainer.mp4` is the visual cut with `Explainer.srt`;
> the script below is for a human voice recording. Each block is timed to its scene.

---

**[00:00 — Scene 1 · The problem]**
A single hotel booking generates a dozen interactions — a refund, a voucher, an amendment, a rate mismatch.
Ticket-centric tools see twelve unrelated tickets, so every agent rebuilds the same context from scratch.

**[00:15 — Scene 2 · One booking, one case]**
OpsDesk starts from the booking. When a request arrives without the booking id, the platform extracts it
from the message itself, classifies the intent, and links the ticket into the case that already exists.
Thirteen tickets on one booking become one operational story.

**[00:30 — Scene 3 · Understanding the intent]**
Eight canonical intents, recognised by a calibrated model trained on synthetic in-house templates, with a
rule-based fallback if the model is unavailable. On a template-disjoint holdout the model reaches
eighty-nine and a half percent accuracy and an eighty-nine and a half percent macro F1 over two hundred
and eighty-eight cases. The confidence the agent sees is the model's calibrated probability — not a number
someone typed into the interface.

**[00:45 — Scene 4 · Routing you can audit]**
Routing is a hundred-point decision. Thirty-five for region, twenty-five for shift, twenty-five for
skill weighted by urgency, fifteen for remaining capacity. Hard filters run first: offline, at capacity,
off shift, below the skill floor, or ineligible for that region. Every rejected agent comes with a reason,
the winner comes with a breakdown, and every run is written to an append-only audit.

**[01:00 — Scene 5 · SLA that respects travel]**
The deadline is the earliest of three things: the priority SLA, two hours before the last cancellation
date, and four hours before check-in. A regional holiday lowers the at-risk threshold from seventy-five to
fifty percent — and records why. Missing or expired travel dates are reported explicitly, never quietly
turned into zero.

**[01:15 — Scene 6 · Conversations stay independent]**
The main thread and the supplier conversation are different objects. Each side conversation owns its
recipient list and its history. When a ticket is transferred to another group, the queue and the owner
move — and the platform verifies that every recipient stayed exactly the same.

**[01:30 — Scene 7 · From operations to product]**
Because every ticket sits on a booking, patterns become visible: the same supplier, the same intent, again
and again. OpsDesk turns those clusters into product-bug proposals with the tickets attached. And when
governance needs data, fifty thousand rows stream out in about one second, then get validated from the
file on disk.

**[01:40 — Closing, over Scene 7]**
OpsDesk does not just manage tickets. It understands the entire travel operation.

---

## Delivery notes

- Read scene 1–2 slightly slower; they carry the thesis.
- Numbers: "eighty-nine and a half percent" reads more naturally than "zero point eight nine five eight".
- Leave ~0.5 s of silence at each scene boundary so cuts feel deliberate.
- If the recording runs long, trim scene 2 and 6 first — scenes 4, 5 and 7 carry the evidence.
