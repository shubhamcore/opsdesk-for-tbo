# Product Demo — Shot Script

**File:** `Product_Demo.mp4` · 1440×900 · H.264 · 25 fps · **207 s (3 min 27 s)** · 6 segments
**Subtitles:** `Product_Demo.srt` (cue timings derived from the recorded segment lengths)
**Recorded by:** `python -m scripts.run_Automated_Demo --only demo`
(Playwright records each segment, FFmpeg normalises and concatenates them)

Sign-in used for the recording: Ops Lead (`nisha.verma@tbo.com`) via the documented demo password,
then two identity switches to prove RBAC. The dataset is reseeded immediately before recording so the
timings are deterministic.

| Segment | Length | Screen | Actions performed |
| --- | --- | --- | --- |
| 1 · Ops queue & SLA | ≈37 s | W1 | Land on the queue → region filter `MEA` → clear → SLA filter `AT_RISK` → hover the region×SLA chart → scroll the table → search `refund` → open `TCK-401` → hover its SLA cell |
| 2 · Case workspace | ≈52 s | W2 | Search `TBOH-778899` → open `TCK-101` → read classification + 3-point brief → post a main-thread reply → search `TCK-301` → open the supplier conversation (hover recipient chips) → Transfer modal → confirm → read the verification panel → open `TCK-402` → Escalate modal with a reason |
| 3 · Routing | ≈33 s | W3 | Agent board (load, utilisation, reference score) → select `TCK-201` in the comparator → hover the winner row → **Route now** → hover the excluded list |
| 4 · War room | ≈21 s | W4 | Escalation inventory (escalated only) → switch to all open → select a ticket → scroll to the trend / deadline charts |
| 5 · Intelligence | ≈26 s | W5 | Insights tab (4 charts) → Bug suggestions tab with evidence → Exports tab → 20,000-row stream → validation panel → job table |
| 6 · Simulation lab | ≈39 s | W6 | Journey cards → run A → run B → run C → run D → scroll the results and console |

## Suggested commentary (record separately)

| Time | Cue |
| --- | --- |
| 00:00 | "This is the ops queue. Active, at-risk and breached counts are computed by the SLA engine on every request." |
| 00:20 | "Filters are server-side. Each row tells you which rule governs its clock." |
| 00:40 | "Opening a ticket gives you the booking context first — the case, not the message." |
| 01:05 | "The brief has exactly three points, and it cites the tickets it used." |
| 01:25 | "Here is the supplier conversation for the same case — different object, different recipients." |
| 01:40 | "I transfer it to senior ops. The platform verifies the recipients did not change." |
| 02:00 | "Routing: five eligible, four excluded, and the winner's score broken into its four terms." |
| 02:30 | "Escalation hands the ticket to a named manager, and the ticket shows time over its deadline." |
| 03:00 | "Fifty thousand rows, streamed, then validated by re-reading the file." |
| 03:20 | "Finally, the lab runs the seeded journeys against this same API." |

## Production notes

- Deterministic: `wait_for_load_state("networkidle")` + explicit `data-testid` selector waits, plus a
  3-attempt retry wrapper per segment.
- Cursor motion is real (Playwright), so no cursor overlay is required; if you want a highlight ring, add
  it in post at the timestamps above.
- A single run reseeds the baseline, so each rehearsal produces the same numbers — useful when the
  narration quotes a figure.
