/**
 * W3 — Routing & Agent Capacity Studio.
 *
 * Shows the live agent board, the weighting formula, a side-by-side comparator of
 * eligible candidates with the excluded list, and the immutable audit trail.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Ban, Gauge, PlayCircle, Scale, ScrollText, Users } from 'lucide-react'
import { ScatterPlot, VerticalBars } from '../components/charts'
import { Badge, EmptyState, ErrorNote, Meter, Section, Select, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { fmtDateTime, fmtNumber } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { useSession } from '../lib/store'
import type {
  AgentBoardRow,
  RoutingAudit,
  RoutingDecision,
  RoutingFormula,
  RoutingOutcome,
  TicketListResponse,
  TicketRow,
} from '../lib/types'

interface BoardResponse {
  agents: AgentBoardRow[]
  count: number
  eligible_now: number
  at_capacity: number
}

export default function W3RoutingStudio() {
  const { can } = useSession()
  const board = useFetch<BoardResponse>('/api/routing/board', 60_000)
  const formula = useFetch<RoutingFormula>('/api/routing/formula')
  const tickets = useFetch<TicketListResponse>('/api/tickets')
  const [ticketRef, setTicketRef] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  const openTickets = useMemo(
    () => (tickets.data?.tickets ?? []).filter((row: TicketRow) => row.status !== 'RESOLVED' && row.status !== 'CLOSED'),
    [tickets.data],
  )

  const selected = ticketRef || openTickets[0]?.ticket_number || ''
  // The audit endpoint keys on the numeric ticket id, the comparator accepts the
  // human ticket number — both resolve to the same row.
  const selectedId = openTickets.find((row) => row.ticket_number === selected)?.id
  const comparator = useFetch<RoutingDecision>(
    selected ? `/api/routing/tickets/${selected}/comparator` : null,
  )
  const audits = useFetch<{ audits: RoutingAudit[]; count: number }>(
    selectedId ? `/api/routing/audits?ticket_id=${selectedId}&limit=12` : null,
  )

  const [routing, setRouting] = useState<RoutingOutcome | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [overrideNote, setOverrideNote] = useState('')
  const [overrideAgent, setOverrideAgent] = useState('')

  const agents = board.data?.agents ?? []
  const decision = comparator.data

  function refreshAll() {
    board.reload()
    comparator.reload()
    audits.reload()
    setRefreshKey((value) => value + 1)
  }

  async function route() {
    if (!decision) return
    setBusy(true)
    setError(null)
    try {
      const outcome = await api<RoutingOutcome>(`/api/routing/tickets/${decision.ticket_id}/route`, {
        method: 'POST',
        body: { triggered_by: 'MANUAL' },
      })
      setRouting(outcome)
      refreshAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Routing failed')
    } finally {
      setBusy(false)
    }
  }

  async function override() {
    if (!decision || !overrideAgent) return
    setBusy(true)
    setError(null)
    try {
      const outcome = await api<RoutingOutcome & { override: boolean }>(
        `/api/routing/tickets/${decision.ticket_id}/reassign`,
        { method: 'POST', body: { agent_id: Number(overrideAgent), note: overrideNote || null } },
      )
      setRouting(outcome)
      setOverrideAgent('')
      setOverrideNote('')
      refreshAll()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Override failed')
    } finally {
      setBusy(false)
    }
  }

  const winner = decision?.winner ?? routing?.decision?.winner ?? null

  return (
    <div className="space-y-3">
      {board.error ? <ErrorNote message={board.error} onRetry={board.reload} /> : null}
      {tickets.error ? <ErrorNote message={tickets.error} onRetry={tickets.reload} /> : null}

      {/* formula */}
      <section className="card card-pad" data-testid="formula-card">
        <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="section-title flex items-center gap-1.5">
            <Scale className="h-3.5 w-3.5 text-brand" aria-hidden /> Scoring model
          </h2>
          <span className="text-[11px] text-slate-500">
            max {formula.data?.max_score ?? 100} points · tie-break: {formula.data?.tie_break ?? '…'}
          </span>
        </header>
        <p className="mono rounded-lg bg-navy px-3 py-2 text-[12px] text-brand-50">
          {formula.data?.formula ?? 'Loading formula…'}
        </p>
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          <div>
            <p className="label">Weights</p>
            <div className="space-y-1">
              {Object.entries(formula.data?.weights ?? {}).map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <span className="w-[70px] text-[11px] capitalize text-slate-600">{key}</span>
                  <Meter value={value} max={35} />
                  <span className="w-10 text-right text-[11px] tabular-nums text-navy">{value}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="label">Hard filters applied before scoring</p>
            <ul className="space-y-0.5">
              {(formula.data?.hard_filters ?? []).map((filter) => (
                <li key={filter} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                  <Ban className="mt-0.5 h-3 w-3 shrink-0 text-rose-500" aria-hidden />
                  {filter}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* agent board */}
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Section
          title="Agent board"
          testId="agent-board"
          subtitle={
            board.data
              ? `${board.data.eligible_now} eligible now · ${board.data.at_capacity} at capacity · ${board.data.count} agents`
              : 'Live capacity and shift state'
          }
          action={<Users className="h-4 w-4 text-slate-400" aria-hidden />}
        >
          {board.loading && agents.length === 0 ? (
            <Spinner />
          ) : (
            <div className="max-h-[380px] overflow-auto rounded-lg border border-line">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Region</th>
                    <th>Skill</th>
                    <th>Shift</th>
                    <th>Load</th>
                    <th>Utilisation</th>
                    <th>Reference score</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.map((agent) => (
                    <tr key={agent.agent_id} data-testid={`agent-row-${agent.agent_id}`}>
                      <td>
                        <span className="text-[12px] font-medium">{agent.name}</span>
                        <p className="text-[10px] text-slate-400">{agent.email}</p>
                      </td>
                      <td className="text-[12px]">{agent.region}</td>
                      <td className="text-[12px] tabular-nums">{agent.skill_rank}/5</td>
                      <td>
                        <span className="mono text-[10.5px]">{agent.shift}</span>
                        <p className={`text-[10px] ${agent.shift_match_now ? 'text-emerald-600' : 'text-slate-400'}`}>
                          {agent.shift_match_now ? 'on shift now' : 'outside shift'}
                        </p>
                      </td>
                      <td className="text-[12px] tabular-nums">
                        {agent.active_load}/{agent.max_capacity}
                      </td>
                      <td>
                        <div className="flex items-center gap-1.5">
                          <Meter
                            value={agent.utilization_pct}
                            max={100}
                            tone={agent.utilization_pct >= 100 ? 'rose' : agent.utilization_pct >= 75 ? 'amber' : 'green'}
                          />
                          <span className="w-9 text-right text-[10.5px] tabular-nums text-slate-500">
                            {fmtNumber(agent.utilization_pct)}%
                          </span>
                        </div>
                      </td>
                      <td className="text-[12px] tabular-nums">{fmtNumber(agent.reference_score)}</td>
                      <td>
                        {!agent.is_online ? (
                          <Badge tone="slate">offline</Badge>
                        ) : agent.active_load >= agent.max_capacity ? (
                          <Badge tone="rose">at capacity</Badge>
                        ) : agent.shift_match_now ? (
                          <Badge tone="green">available</Badge>
                        ) : (
                          <Badge tone="amber">off shift</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <div className="space-y-3">
          <VerticalBars
            data={agents
              .slice()
              .sort((a, b) => b.reference_score - a.reference_score)
              .map((agent) => ({ name: agent.name, value: Number(agent.reference_score.toFixed(1)) }))}
            testId="chart-reference-scores"
            title="Reference score by agent"
            subtitle="Generic reference ticket, all filters applied"
            layout="vertical"
            height={230}
          />
          <ScatterPlot
            data={agents.map((agent) => ({
              name: agent.name,
              x: agent.active_load,
              y: agent.reference_score,
              z: agent.skill_rank,
            }))}
            testId="chart-load-vs-score"
            title="Load vs score"
            subtitle="Bubble size = skill rank"
            xLabel="Active load"
            yLabel="Reference score"
            height={230}
          />
        </div>
      </div>

      {/* comparator */}
      <section className="card card-pad" data-testid="comparator-card">
        <header className="mb-2 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="section-title flex items-center gap-1.5">
              <Gauge className="h-3.5 w-3.5 text-brand" aria-hidden /> Comparator
            </h2>
            <p className="text-[11px] text-slate-500">
              Every eligible candidate with the exact contribution of each weighted term.
            </p>
          </div>
          <div className="flex items-end gap-2">
            <div className="w-[190px]">
              <Select
                label="Ticket"
                value={selected}
                allowEmpty={false}
                options={openTickets.map((row) => ({
                  value: row.ticket_number,
                  label: `${row.ticket_number} · ${row.priority} · ${row.region}`,
                }))}
                onChange={(value) => {
                  setTicketRef(value)
                  setRouting(null)
                }}
                testId="comparator-ticket-select"
              />
            </div>
            <button type="button" className="btn-primary" onClick={route} disabled={busy || !decision} data-testid="comparator-route">
              <PlayCircle className="h-3.5 w-3.5" aria-hidden /> {busy ? 'Routing…' : 'Route now'}
            </button>
          </div>
        </header>

        {error ? <p className="mb-2 text-[11px] text-rose-600">{error}</p> : null}
        {comparator.error ? <ErrorNote message={comparator.error} onRetry={comparator.reload} /> : null}

        {decision ? (
          <>
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
              <Badge tone="brand">{decision.ticket_number}</Badge>
              <span>region {decision.ticket_region}</span>
              <span>SLA {decision.sla_state}</span>
              <span>urgency weight {decision.urgency_weight.toFixed(2)}</span>
              <span>{decision.candidates.length} eligible / {decision.excluded.length} excluded</span>
              {decision.tie_break_applied ? <Badge tone="amber">tie-break applied</Badge> : null}
            </div>

            <div className="overflow-auto rounded-lg border border-line">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Agent</th>
                    <th>Region</th>
                    <th>Skill</th>
                    <th>Region 35</th>
                    <th>Shift 25</th>
                    <th>Skill 25</th>
                    <th>Capacity 15</th>
                    <th>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {decision.candidates.map((candidate, index) => {
                    const isWinner = winner?.agent_id === candidate.agent_id
                    return (
                      <tr
                        key={candidate.agent_id}
                        data-testid={`comparator-row-${candidate.agent_id}`}
                        className={isWinner ? 'bg-brand-50' : undefined}
                      >
                        <td className="text-[11px] text-slate-400">{index + 1}</td>
                        <td>
                          <span className="text-[12px] font-medium">{candidate.full_name}</span>
                          {isWinner ? <Badge tone="brand">selected</Badge> : null}
                          <p className="text-[10px] text-slate-400">
                            load {candidate.active_load}/{candidate.max_capacity} · skill {candidate.skill_rank}
                          </p>
                        </td>
                        <td className="text-[11.5px]">{candidate.region ?? '—'}</td>
                        <td className="text-[11.5px] tabular-nums">{candidate.skill_rank}/5</td>
                        <td className="tabular-nums text-[11.5px]">{fmtNumber(candidate.region_match)}</td>
                        <td className="tabular-nums text-[11.5px]">{fmtNumber(candidate.shift_match * 25)}</td>
                        <td className="tabular-nums text-[11.5px]">{fmtNumber(candidate.skill_component)}</td>
                        <td className="tabular-nums text-[11.5px]">{fmtNumber(candidate.capacity_component)}</td>
                        <td className="font-semibold tabular-nums text-[12px]">{fmtNumber(candidate.total_score)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <div data-testid="excluded-list" className="rounded-lg border border-rose-200 bg-rose-50/60 p-2">
                <p className="label !text-rose-700">Excluded by hard filters</p>
                <ul className="space-y-1">
                  {decision.excluded.map((excluded) => (
                    <li key={excluded.agent_id} className="text-[11px] text-rose-800">
                      <strong>{excluded.full_name}</strong> ({excluded.region ?? '—'}): {excluded.reasons.join('; ')}
                    </li>
                  ))}
                  {decision.excluded.length === 0 ? <li className="text-[11px] text-slate-500">None excluded.</li> : null}
                </ul>
              </div>
              <div className="rounded-lg border border-line bg-slate-50 p-2">
                <p className="label">Decision</p>
                {routing ? (
                  <div className="space-y-0.5 text-[11px] text-slate-700">
                    <p>
                      Assigned to <strong>{routing.assigned_to?.name ?? 'nobody'}</strong>
                      {routing.assigned_to ? ` (load ${routing.assigned_to.active_load}/${routing.assigned_to.max_capacity})` : ''}
                    </p>
                    <p>Score {fmtNumber(routing.decision.score)} · audit #{routing.audit_id}</p>
                    <p>{routing.decision.decision_reason}</p>
                    <p className="text-slate-500">{routing.fifo_note}</p>
                  </div>
                ) : (
                  <p className="text-[11px] text-slate-500">
                    Run “Route now” to persist an assignment, or open the audit table below to inspect past decisions.
                  </p>
                )}
              </div>
            </div>

            {can('override_assignment') && decision.candidates.length > 0 ? (
              <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-2">
                <p className="label !text-amber-800">Ops Lead override (audited)</p>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-[190px]">
                    <Select
                      label="Assign to"
                      value={overrideAgent}
                      allowEmpty={false}
                      options={decision.candidates.map((candidate) => ({
                        value: String(candidate.agent_id),
                        label: `${candidate.full_name} (${candidate.total_score.toFixed(1)})`,
                      }))}
                      onChange={setOverrideAgent}
                      testId="override-agent"
                    />
                  </div>
                  <div className="min-w-[180px] flex-1">
                    <label className="block">
                      <span className="label">Reason</span>
                      <input
                        className="input"
                        value={overrideNote}
                        onChange={(event) => setOverrideNote(event.target.value)}
                        placeholder="Commercial agreement with the agency"
                      />
                    </label>
                  </div>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={override}
                    disabled={busy || !overrideAgent}
                    data-testid="override-submit"
                  >
                    Override assignment
                  </button>
                </div>
              </div>
            ) : null}
          </>
        ) : (
          <EmptyState title="Select a ticket" hint="Pick an open ticket to compare eligible agents." />
        )}
      </section>

      {/* audit */}
      <Section
        title="Routing audit trail"
        testId="audit-table"
        subtitle="Immutable record of every scoring run for the selected ticket"
        action={<ScrollText className="h-4 w-4 text-slate-400" aria-hidden />}
      >
        {audits.loading && !audits.data ? (
          <Spinner />
        ) : (
          <div className="max-h-[300px] overflow-auto rounded-lg border border-line">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Audit</th>
                  <th>Ticket</th>
                  <th>Selected</th>
                  <th>Score</th>
                  <th>Candidates</th>
                  <th>Excluded</th>
                  <th>Trigger</th>
                  <th>Reason</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {(audits.data?.audits ?? []).map((audit) => (
                  <tr key={audit.id}>
                    <td className="mono text-[11px]">#{audit.id}</td>
                    <td>
                      <Link className="link mono text-[11px]" to={`/w2/${audit.ticket_id}`}>
                        ticket {audit.ticket_id}
                      </Link>
                    </td>
                    <td className="text-[11.5px]">{audit.selected_agent ?? '—'}</td>
                    <td className="tabular-nums text-[11.5px]">{audit.selected_score !== null ? fmtNumber(audit.selected_score) : '—'}</td>
                    <td className="tabular-nums text-[11.5px]">{audit.eligible_count}</td>
                    <td className="tabular-nums text-[11.5px]">{audit.excluded.length}</td>
                    <td className="text-[11px]">{audit.triggered_by}</td>
                    <td className="max-w-[280px] text-[11px] text-slate-600">{audit.decision_reason}</td>
                    <td className="text-[11px] text-slate-500">{fmtDateTime(audit.created_at)}</td>
                  </tr>
                ))}
                {(audits.data?.audits ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-4 text-center text-[12px] text-slate-500">
                      No routing runs recorded for this ticket yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-[10.5px] text-slate-400">
          refresh key {refreshKey} · audits are append-only; overrides are recorded as separate rows with the actor.
        </p>
      </Section>
    </div>
  )
}
