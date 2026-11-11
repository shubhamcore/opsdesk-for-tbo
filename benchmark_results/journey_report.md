# Five Judging Journeys — Execution Report

Generated: 2026-11-11T15:05:31.672774+00:00

**5/5 journeys passed** (34/34 steps)

| Journey | Title | Steps passed | Result |
|---|---|---|---|
| A | Booking context and automatic case linking | 7/7 | PASS |
| B | Intelligent routing and capacity | 6/6 | PASS |
| C | Transfer-safe supplier communication | 6/6 | PASS |
| D | Travel-aware SLA and escalation | 8/8 | PASS |
| E | Product intelligence and large export | 7/7 | PASS |

## Journey A — Booking context and automatic case linking

| Step | Expected | Actual | Result |
|---|---|---|---|
| Agency requester signs in | Token issued for Wanderlust Travels | Maya Al Farsi (AGENCY_REQUESTER, Wanderlust Travels) | PASS |
| Booking context is visible before the new request | >= 3 existing tickets | 7 existing tickets on TBOH-778899 | PASS |
| Submit refund request with the TBOH field left EMPTY | Ticket created | Created TCK-625 | PASS |
| Stage A extracts the booking id from the description | extraction_source=DESCRIPTION, TBOH-778899 | ['TBOH-778899'] via DESCRIPTION | PASS |
| Intent classified as REFUND_DELAY with calibrated confidence | REFUND_DELAY from the ML pipeline | REFUND_DELAY @ 87% (ML) | PASS |
| Previous tickets are linked into one case | TCK-101, TCK-104 and TCK-109 appear in the linked case | 10 related tickets: ['TCK-101', 'TCK-104', 'TCK-109'] | PASS |
| AI Case Brief summarises the linked history in three points | 3 evidence-bound points | 3 points | PASS |

## Journey B — Intelligent routing and capacity

| Step | Expected | Actual | Result |
|---|---|---|---|
| Operations agent signs in | Token issued for an ops agent | None | PASS |
| Create a high-priority APAC ticket | Ticket created (unassigned) | Created TCK-626 | PASS |
| Dry-run the comparator before assignment | Ananya Sharma ranks first | Top candidate Ananya Sharma at 94.375/100 (4 eligible, 5 excluded) | PASS |
| Run intelligent routing | Assigned to Ananya Sharma (APAC, skill 5/5) | Ananya Sharma — score 94.375/100, load 1/8 | PASS |
| Explain why FIFO was not used | Region, shift, skill and capacity all contribute | Winner scored 94.375/100 = region 35 + shift 25 + skill 21.2 + capacity 13.1 | PASS |
| Routing decision is written to the immutable audit log | Audit row with every candidate score | 1 audit row(s); latest records 4 candidates | PASS |

## Journey C — Transfer-safe supplier communication

| Step | Expected | Actual | Result |
|---|---|---|---|
| EU operations agent signs in | Token issued | None | PASS |
| Open the EuroWings supplier ticket | TCK-301 located | TCK-301 in queue EU-TRIAGE | PASS |
| Supplier side conversation exists with explicit recipients | groups@hilton-paris.com | Reusing conversation #1 with ['groups@hilton-paris.com'] | PASS |
| Send a supplier message | Delivered to the explicit recipient | 1 message(s) to ['groups@hilton-paris.com'] | PASS |
| Transfer EU-TRIAGE → EU-SENIOR-OPS | Recipients verified unchanged | Ticket moved to EU-SENIOR-OPS. Original recipients unchanged (1 conversation(s), 1 recipient(s)). | PASS |
| Reopen the conversation after transfer | Recipients and history preserved | queue=EU-SENIOR-OPS, recipients=['groups@hilton-paris.com'], messages=4, transfers=1 | PASS |

## Journey D — Travel-aware SLA and escalation

| Step | Expected | Actual | Result |
|---|---|---|---|
| Operations agent signs in | Token issued | None | PASS |
| Open the queue and read live SLA state | Both AT_RISK and BREACHED present | HEALTHY 10, AT_RISK 6, BREACHED 28 | PASS |
| TCK-401 countdown is governed by the LCD deadline | LCD_DEADLINE rule | AT_RISK governed by LCD_DEADLINE, 49 min remaining (holiday threshold applied) | PASS |
| TCK-402 handles an already-expired check-in deadline safely | CHECK_IN_DEADLINE with explicit expired flag | BREACHED governed by CHECK_IN_DEADLINE, expired_travel_deadline=True | PASS |
| Filter the queue to AT_RISK | Only AT_RISK tickets | 6 AT_RISK tickets | PASS |
| Escalate TCK-401 to an Escalation Manager | ESCALATED + queue ESCALATION_MANAGER + real owner | status=ESCALATED, queue=ESCALATION_MANAGER, owner=Elena Rossi | PASS |
| Switch to the Escalation Manager war room | New ownership visible in the EM queue | Elena Rossi sees 34 tickets; owns TCK-401: True | PASS |
| Audit timeline records the handover | ESCALATED event + escalation record | events=['ESCALATED', 'TICKET_CREATED']; escalation records=1 | PASS |

## Journey E — Product intelligence and large export

| Step | Expected | Actual | Result |
|---|---|---|---|
| Operations lead signs in | Token issued | None | PASS |
| Product intelligence aggregates recurring themes | Inventory-sync theme with >= 3 tickets | 51 tickets in window; top intent REFUND_DELAY×18; inventory-sync tickets=16 | PASS |
| Recurring supplier/API pattern produces a bug suggestion | >= 3 tickets sharing supplier + intent | 5 suggestion(s); top: Accor INVENTORY_RATE_SYNC_BUG ×3 | PASS |
| Create a local product bug record | PROD-BUG-1xx created | Created PROD-BUG-101 (PROPOSED) | PASS |
| Stream a 50,000-row CSV export | Exactly 50,000 data rows | 50000 data rows, 25 columns, 16.31 MB streamed | PASS |
| Validate the generated artifact on disk | Row count matches and file is readable | 50000 rows in file, 25 columns, 16.31 MB, PASS | PASS |
| Export job metrics are measured, not hardcoded | COMPLETED with measured throughput | 50000 rows in 903.9 ms (55315.85 rows/s, peak 33.281 MB) | PASS |
