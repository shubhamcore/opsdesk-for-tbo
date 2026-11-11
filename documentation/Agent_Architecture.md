# OpsDesk — Agent Mesh Architecture

> Eight specialist reviewers run over a single case, each restricted to an explicit tool
> allow-list, each trace persisted. No external model is contacted in this build.

---

## 1. Why a mesh and not one assistant

A travel-ops case is decided by several independent questions that fail in different ways:

| Question | Failure mode if it is folded into one prompt |
| --- | --- |
| What is this case actually about? | Intent drifts toward whatever dominates the text |
| How much time is left? | Deadline arithmetic quietly becomes prose |
| Who should own it? | Routing weights get ignored |
| Does it need escalation? | Escalation criteria get rationalised away |
| What do we tell the customer? | Reply invents details not present in the booking |
| What should not leave the building? | Leakage checks are never performed |
| Is this a pattern or an incident? | Recurrence is invisible |
| What is the standard procedure? | Process knowledge is lost |

Splitting them gives one owner per question, an audit trail *per* question, and a failure
that is contained to a single reviewer instead of poisoning the whole answer.

## 2. The eight specialists

| Agent | Question it owns | Tools it may call | Emits |
| --- | --- | --- | --- |
| `intake` — Intake & Classification | What is this case? | `classify_intent`, `extract_references`, `case_links` | Intent, calibrated confidence, extracted TBOH references, case size |
| `sla_risk` — SLA & Travel Deadline Risk | How much time is left? | `sla_state` | State, governing rule, minutes remaining, holiday adjustment |
| `routing_advisor` — Routing & Capacity Advisor | Who should own it? | `routing_decision` | Winner, score out of 100, margin, hard-filter exclusions |
| `escalation` — Escalation Readiness | Does it need an EM? | `escalation_context`, `sla_state` | Criteria verdict, eligible escalation manager |
| `comms` — Customer Communications | What do we say? | `thread_messages`, `side_conversations`, `sla_state` | A draft reply built only from stored facts |
| `qa` — Quality & Leakage Guard | What must not get out? | `thread_messages`, `side_conversations`, `activity_events` | Card/passport tokens in public text, recipient-less side threads |
| `product_intel` — Product Intelligence | Pattern or incident? | `product_patterns`, `case_links` | Supplier × intent recurrence with ticket numbers |
| `playbook` — Resolution Playbook | What is the SOP? | `sla_state`, `case_links` | Authored steps for the case intent |

`playbook` returns hand-written operating guidance shipped with the product — it is labelled
`source: authored-sop` in the payload and in the UI, never presented as model output.

## 3. Tool contract

Tools are read-only adapters over services the REST API already uses:

```
classify_intent      → backend.services.classifier.get_classifier().classify(...)
extract_references   → backend.services.extraction.extract_entities(...)
case_links           → backend.services.linking.unified_case_tickets(...)
sla_state            → backend.services.sla.compute_sla(...)
routing_decision     → backend.services.assignment.build_decision(...)
thread_messages      → messages table
side_conversations   → side_conversations + side_messages
escalation_context   → escalation_records + users (ESCALATION_MANAGER)
product_patterns     → backend.services.analytics.bug_suggestions(...)
activity_events      → activity_timeline
```

Two invariants make the mesh trustworthy:

1. **No write tools exist.** Agents cannot post a message, reassign a ticket, escalate or
   create a bug. Mutations stay behind the authenticated endpoints, so RBAC, validation and
   the immutable audit trail apply to an agent-assisted action exactly as to a human one.
2. **Every tool call is recorded** with its arguments, duration, success flag and an output
   preview. A finding without a tool call behind it is a bug in the agent, and
   `tests/test_agents.py` asserts that OK/ATTENTION findings always carry tool evidence.

## 4. Execution model

```
POST /api/agents/cases/{ticket}/run
        │
        ├── ToolBox(db, ticket, blackboard)         per agent, fresh recorder
        ├── for agent in ALL_AGENTS:                synchronous, ordered
        │       result = agent.run(box)             exceptions → status ERROR
        ├── summarise(results)                      plan, confidence, needs_human
        └── INSERT agent_runs (trace + plan)        one row per review
```

* **Ordering** is intake → SLA → routing → escalation → comms → QA → product → playbook:
  cheap structural facts first, so later agents read a case that is already understood.
* **Containment**: a raising agent is recorded as `ERROR` and the run becomes `PARTIAL`; the
  other seven still complete (`test_agent_failure_is_contained`).
* **Plan derivation**: every agent returns recommendations tagged `P0/P1/P2`; the
  orchestrator de-duplicates by action text, sorts by priority, and keeps the top eight.
* **Confidence**: the mean of the non-skipped agents' own confidence values. It is reported
  as *mean confidence of the reviewers*, never as a probability judged correct.
* **Persistence**: `agent_runs` holds `run_uuid`, ticket, objective, status, per-agent JSON
  trace, plan JSON, confidence, duration and the acting user.

Measured on the seeded dataset (this build): a full eight-agent review of `TCK-101` completes
in **24–56 ms** server-side, `TCK-101 → 5 plan actions`.

## 5. What the agents are *not*

* Not an LLM. `OPSDESK_LLM_ENDPOINT` exists in `.env.example` as a documented extension
  point and is never contacted; every payload carries `"external_model": null`.
* Not autonomous. Nothing is written to a case by a run; the UI shows the plan and a human
  (or an explicit, audited endpoint) acts on it.
* Not decisive about routing or SLA. Those numbers come from the same engines the rest of the
  product uses, which is why the agent's evidence and the API's own payload agree — asserted
  in `test_swarm_run_produces_a_grounded_plan`.
* Not a quality guarantee. The QA agent catches pattern-shaped risks (card/passport tokens,
  missing recipients); it is not a substitute for a privacy review.

## 6. Surfaces

| Surface | What it shows |
| --- | --- |
| `GET /api/agents/registry` | Catalogue: tools, determinism, absence of an external model |
| `POST /api/agents/cases/{ticket}/run` | Run the mesh; persisted and returned |
| `GET /api/agents/runs?ticket_id=` | Review history for a case |
| `GET /api/agents/runs/{run_uuid}` | One archived trace |
| `GET /api/agents/telemetry` | Per-agent runs, success rate, average duration, tool calls |
| W2 → **Agent mesh** panel | Run button, eight agent cards, prioritised plan, case history |

## 7. Extending it

Adding an agent means: declare `name`, `title`, `description`, `tool_names`; implement
`run(box) -> AgentResult`; append it to `ALL_AGENTS`. Adding a tool means: write a read-only
function `(db, ticket, **kwargs)` and register a `ToolSpec` in `backend/agents/tools.py`.
Both are enforced at import time — an unknown tool name raises immediately rather than
failing mid-review.
