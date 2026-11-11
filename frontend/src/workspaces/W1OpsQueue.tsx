/**
 * W1 — Ops Queue & SLA Command Center.
 *
 * Queue is filtered server-side; the countdowns recompute from the absolute
 * `effective_due_at` returned by the SLA engine, so a page that stays open
 * never drifts away from the backend.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlarmClock, RefreshCw, Search, ShieldAlert, TriangleAlert } from 'lucide-react'
import { Donut, StackedStates, TrendLine, VerticalBars } from '../components/charts'
import { Badge, EmptyState, ErrorNote, Kpi, Section, Select, SlaCell, Spinner, TextInput } from '../components/ui'
import { useDebounced, useFetch } from '../lib/hooks'
import { fmtDateTime, fmtNumber, humanise, priorityTone, slaTone } from '../lib/format'
import { useTicker } from '../lib/store'
import type { QueueSnapshot, TicketListResponse, TicketRow } from '../lib/types'

interface Filters {
  search: string
  region: string
  priority: string
  sla: string
  intent: string
}

const EMPTY: Filters = { search: '', region: '', priority: '', sla: '', intent: '' }

export default function W1OpsQueue() {
  const [filters, setFilters] = useState<Filters>(EMPTY)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const search = useDebounced(filters.search, 300)
  const tick = useTicker(1000)

  const query = useMemo(() => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (filters.region) params.set('region', filters.region)
    if (filters.priority) params.set('priority', filters.priority)
    if (filters.sla) params.set('sla_state', filters.sla)
    if (filters.intent) params.set('intent', filters.intent)
    return params.toString()
  }, [search, filters.region, filters.priority, filters.sla, filters.intent])

  const queue = useFetch<QueueSnapshot>('/api/analytics/queue', autoRefresh ? 60_000 : undefined)
  const tickets = useFetch<TicketListResponse>(`/api/tickets?${query}`, autoRefresh ? 60_000 : undefined)

  const snapshot = queue.data
  const rows: TicketRow[] = tickets.data?.tickets ?? []
  const matrix = snapshot?.sla_matrix ?? tickets.data?.sla_matrix

  const states = useMemo(() => {
    const base = snapshot?.sla_states ?? {}
    return [
      { name: 'Healthy', value: base.HEALTHY ?? 0 },
      { name: 'At risk', value: base.AT_RISK ?? 0 },
      { name: 'Breached', value: base.BREACHED ?? 0 },
      { name: 'Resolved', value: base.RESOLVED ?? 0 },
    ]
  }, [snapshot])

  const regionStates = useMemo(() => {
    const byRegion = new Map<string, { healthy: number; at_risk: number; breached: number }>()
    ;(snapshot?.tickets ?? []).forEach((ticket) => {
      if (ticket.status === 'RESOLVED' || ticket.status === 'CLOSED') return
      const entry = byRegion.get(ticket.region) ?? { healthy: 0, at_risk: 0, breached: 0 }
      if (ticket.sla.state === 'BREACHED') entry.breached += 1
      else if (ticket.sla.state === 'AT_RISK') entry.at_risk += 1
      else entry.healthy += 1
      byRegion.set(ticket.region, entry)
    })
    return Array.from(byRegion.entries()).map(([name, value]) => ({ name, ...value }))
  }, [snapshot])

  const working = useMemo(
    () =>
      rows
        .filter((row) => row.status !== 'RESOLVED' && row.status !== 'CLOSED')
        .sort((a, b) => a.sla.seconds_remaining - b.sla.seconds_remaining),
    [rows],
  )

  const regionOptions = (snapshot?.by_region ?? []).map((entry) => ({ value: entry.region, label: entry.region }))
  const intentOptions = (snapshot?.by_intent ?? []).map((entry) => ({
    value: entry.intent,
    label: `${entry.label} (${entry.count})`,
  }))

  return (
    <div className="space-y-4">
      {/* KPI strip */}
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <Kpi
          label="Active tickets"
          value={snapshot?.totals.active ?? '—'}
          hint={`${snapshot?.totals.tickets ?? 0} total in database`}
          tone="brand"
          testId="kpi-active"
        />
        <Kpi
          label="At risk"
          value={snapshot?.totals.at_risk ?? '—'}
          hint="Past the at-risk threshold"
          tone="amber"
          testId="kpi-at-risk"
        />
        <Kpi
          label="Breached"
          value={snapshot?.totals.breached ?? '—'}
          hint="Effective SLA due date passed"
          tone="rose"
          testId="kpi-breached"
        />
        <Kpi
          label="SLA compliance"
          value={snapshot ? `${fmtNumber(snapshot.sla_compliance.compliance_pct)}%` : '—'}
          hint={snapshot?.sla_compliance.definition}
          tone="green"
          testId="kpi-compliance"
        />
        <Kpi
          label="Escalated"
          value={snapshot?.totals.escalated ?? '—'}
          hint="Held by an escalation manager"
          tone="slate"
          testId="kpi-escalated"
        />
      </div>

      {queue.error ? <ErrorNote message={queue.error} onRetry={queue.reload} /> : null}
      {tickets.error ? <ErrorNote message={tickets.error} onRetry={tickets.reload} /> : null}

      {/* Filters */}
      <Section
        title="Queue filters"
        subtitle="Server-side filtering — the API is queried on every change"
        action={
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-[11px] text-slate-500">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(event) => setAutoRefresh(event.target.checked)}
                className="h-3.5 w-3.5"
              />
              Auto-refresh 60s
            </label>
            <button
              type="button"
              className="btn-ghost"
              onClick={() => {
                queue.reload()
                tickets.reload()
              }}
            >
              <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Refresh
            </button>
          </div>
        }
      >
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="block xl:col-span-1">
            <span className="label">Search</span>
            <span className="relative block">
              <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-slate-400" aria-hidden />
              <input
                className="input pl-7"
                placeholder="TCK-101, TBOH-778899, agency…"
                value={filters.search}
                data-testid="queue-search"
                onChange={(event) => setFilters({ ...filters, search: event.target.value })}
              />
            </span>
          </label>
          <Select
            label="Region"
            value={filters.region}
            options={regionOptions}
            testId="filter-region"
            onChange={(value) => setFilters({ ...filters, region: value })}
          />
          <Select
            label="Priority"
            value={filters.priority}
            options={['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((value) => ({ value, label: value }))}
            testId="filter-priority"
            onChange={(value) => setFilters({ ...filters, priority: value })}
          />
          <Select
            label="SLA state"
            value={filters.sla}
            options={['HEALTHY', 'AT_RISK', 'BREACHED', 'RESOLVED'].map((value) => ({ value, label: humanise(value) }))}
            testId="filter-sla"
            onChange={(value) => setFilters({ ...filters, sla: value })}
          />
          <Select
            label="Intent"
            value={filters.intent}
            options={intentOptions}
            testId="filter-intent"
            onChange={(value) => setFilters({ ...filters, intent: value })}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
          <span>
            <strong className="text-navy">{rows.length}</strong> ticket(s) match
            {filters.sla || filters.region || filters.priority || filters.intent || search ? ' the current filters' : ' — no filters applied'}
          </span>
          <button
            type="button"
            className="link"
            onClick={() => setFilters(EMPTY)}
            disabled={JSON.stringify(filters) === JSON.stringify(EMPTY)}
          >
            Clear filters
          </button>
        </div>
      </Section>

      {/* Charts */}
      <div className="grid gap-3 xl:grid-cols-4">
        <Donut
          data={states}
          testId="chart-sla-mix"
          title="SLA state mix"
          subtitle="Live from the SLA engine"
          colors={['#10B981', '#F59E0B', '#EF4444', '#64748B']}
        />
        <TrendLine
          data={snapshot?.weekly_volume ?? []}
          testId="chart-weekly-volume"
          title="Weekly ticket volume"
          subtitle="ISO week buckets (UTC)"
        />
        <StackedStates
          data={regionStates}
          testId="chart-region-sla"
          title="SLA state by region"
          subtitle="Non-resolved tickets"
        />
        <VerticalBars
          data={(snapshot?.by_intent ?? []).map((entry) => ({ name: entry.label, value: entry.count }))}
          testId="chart-intent-volume"
          title="Tickets by intent"
          subtitle="Classifier output, not a form field"
          layout="vertical"
        />
      </div>

      {/* Queue table */}
      <Section
        title="Working queue"
        subtitle={
          matrix
            ? `Effective SLA = MIN(priority deadline, LCD − ${matrix.lcd_buffer_hours}h, check-in − ${matrix.checkin_buffer_hours}h)`
            : undefined
        }
        action={<span className="text-[11px] text-slate-400">tick {tick % 60}s</span>}
      >
        {tickets.loading && rows.length === 0 ? (
          <Spinner label="Loading queue…" />
        ) : working.length === 0 ? (
          <EmptyState title="No tickets match this view" hint="Clear the filters or widen the SLA state." />
        ) : (
          <div className="max-h-[520px] overflow-auto rounded-lg border border-line">
            <table className="table-base">
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Intent</th>
                  <th>Priority</th>
                  <th>Region</th>
                  <th>Agency</th>
                  <th>Owner</th>
                  <th>Governing rule</th>
                  <th>Next travel</th>
                  <th>SLA</th>
                </tr>
              </thead>
              <tbody>
                {working.map((ticket) => (
                  <tr key={ticket.ticket_number} data-testid={`ticket-row-${ticket.ticket_number}`}>
                    <td>
                      <Link to={`/w2/${ticket.ticket_number}`} className="link font-medium">
                        {ticket.ticket_number}
                      </Link>
                      <p className="max-w-[240px] truncate text-[11px] text-slate-500" title={ticket.title}>
                        {ticket.title}
                      </p>
                    </td>
                    <td>
                      <span className="text-[12px]">{ticket.intent_label ?? 'Unclassified'}</span>
                      <p className="mono text-[10px] text-slate-400">
                        {ticket.intent_confidence ? `${(ticket.intent_confidence * 100).toFixed(1)}% · ${ticket.intent_source}` : '—'}
                      </p>
                    </td>
                    <td>
                      <Badge tone={priorityTone(ticket.priority)}>{ticket.priority}</Badge>
                    </td>
                    <td className="text-[12px]">{ticket.region}</td>
                    <td className="max-w-[130px] truncate text-[12px]">{ticket.agency ?? '—'}</td>
                    <td className="text-[12px]">
                      {ticket.assigned_to ?? <span className="text-slate-400">Unassigned</span>}
                      <p className="text-[10px] text-slate-400">{ticket.queue}</p>
                    </td>
                    <td>
                      <span className="mono text-[10px] text-slate-500">{ticket.sla.governing_rule}</span>
                      {ticket.sla.holiday_adjustment_applied ? (
                        <p className="text-[10px] text-amber-700">holiday threshold 50%</p>
                      ) : null}
                      {ticket.sla.expired_travel_deadline ? (
                        <p className="text-[10px] text-slate-500">travel deadline passed</p>
                      ) : null}
                    </td>
                    <td className="text-[11px]">
                      {ticket.booking ? (
                        <>
                          <span className="mono">{ticket.booking.tboh_id}</span>
                          <p className="text-[10px] text-slate-500">{ticket.booking.check_in_local ?? '—'}</p>
                        </>
                      ) : (
                        <span className="text-slate-400">No booking</span>
                      )}
                    </td>
                    <td>
                      <SlaCell
                        state={ticket.sla.state}
                        secondsRemaining={ticket.sla.seconds_remaining}
                        dueAt={fmtDateTime(ticket.sla.effective_due_at, ticket.booking?.timezone)}
                        testId={`sla-${ticket.ticket_number}`}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* Side panels */}
      <div className="grid gap-3 xl:grid-cols-2">
        <Section
          title="Next travel deadlines"
          subtitle="Bookings whose check-in or last cancellation date is closest"
          action={<AlarmClock className="h-4 w-4 text-slate-400" aria-hidden />}
        >
          <div className="space-y-2">
            {(snapshot?.next_travel ?? []).map((ticket) => (
              <div key={ticket.ticket_number} className="flex items-start justify-between gap-3 rounded-lg border border-line px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-[12px] font-medium">
                    {ticket.booking?.hotel_name ?? ticket.title}
                    <span className="ml-1.5 mono text-[10px] text-slate-400">{ticket.booking?.tboh_id}</span>
                  </p>
                  <p className="text-[11px] text-slate-500">
                    check-in {ticket.booking?.check_in_local ?? '—'} · LCD {ticket.booking?.lcd_local ?? '—'}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <SlaCell
                    state={ticket.sla.state}
                    secondsRemaining={ticket.sla.seconds_remaining}
                    dueAt={fmtDateTime(ticket.sla.effective_due_at, ticket.booking?.timezone)}
                  />
                  <p className="mt-0.5 text-[10px] text-slate-400">{ticket.sla.governing_rule}</p>
                </div>
              </div>
            ))}
            {(snapshot?.next_travel ?? []).length === 0 ? <EmptyState title="No upcoming travel" /> : null}
          </div>
        </Section>

        <Section
          title="Agent capacity snapshot"
          subtitle="Active load against maximum concurrent capacity"
          action={<ShieldAlert className="h-4 w-4 text-slate-400" aria-hidden />}
        >
          <div className="space-y-1.5">
            {(snapshot?.agent_workload ?? []).map((agent) => {
              const ratio = agent.max_capacity ? agent.active_load / agent.max_capacity : 0
              const tone = ratio >= 0.99 ? 'rose' : ratio >= 0.75 ? 'amber' : 'green'
              return (
                <div key={agent.agent_id} className="flex items-center gap-2">
                  <span className="w-[130px] shrink-0 truncate text-[12px]">{agent.name}</span>
                  <Badge tone={agent.is_online ? 'green' : 'slate'}>{agent.is_online ? 'online' : 'offline'}</Badge>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className={`h-full ${tone === 'rose' ? 'bg-rose-500' : tone === 'amber' ? 'bg-amber-500' : 'bg-emerald-500'}`}
                      style={{ width: `${Math.min(100, ratio * 100)}%` }}
                    />
                  </div>
                  <span className="w-[52px] shrink-0 text-right text-[11px] tabular-nums text-slate-600">
                    {agent.active_load}/{agent.max_capacity}
                  </span>
                  <span className="w-[52px] shrink-0 text-right text-[10px] text-slate-400">{agent.region}</span>
                </div>
              )
            })}
          </div>
        </Section>
      </div>

      <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
        <TriangleAlert className="h-3 w-3" aria-hidden />
        All tickets, agencies and bookings in this environment are synthetic seed data generated for the demo.
      </p>
    </div>
  )
}
