/**
 * W4 — Escalation Manager War Room.
 *
 * The dedicated manager interface: escalated inventory, at-risk watch list,
 * holiday-adjusted deadlines and the escalation audit per ticket.
 */

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertOctagon, Clock, ShieldCheck, UserCheck } from 'lucide-react'
import { StackedStates, TrendLine, VerticalBars } from '../components/charts'
import { Badge, EmptyState, ErrorNote, Kpi, Section, Select, SlaCell, Spinner } from '../components/ui'
import { fmtDateTime, humanise, priorityTone } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { useTicker } from '../lib/store'
import type { Escalation, EscalationQueue, TicketRow } from '../lib/types'

interface TrendResponse {
  by_week: { week: string; count: number }[]
  total: number
  window_weeks: number
}

interface DeadlineRow {
  ticket_number: string
  title: string
  due_at: string
  state: string
  governing_rule: string
}

export default function W4WarRoom() {
  const tick = useTicker(1000)
  const queue = useFetch<EscalationQueue>('/api/escalations/queue', 30_000)
  const trend = useFetch<TrendResponse>('/api/escalations/trend')
  const deadlines = useFetch<{ deadlines: DeadlineRow[] }>('/api/escalations/deadlines')
  const [filter, setFilter] = useState<'all' | 'escalated' | 'at_risk' | 'breached'>('escalated')
  const [selected, setSelected] = useState<string | null>(null)

  const tickets: TicketRow[] = queue.data?.tickets ?? []

  const visible = useMemo(() => {
    const list = tickets.filter((ticket) => ticket.status !== 'RESOLVED' && ticket.status !== 'CLOSED')
    if (filter === 'all') return list
    if (filter === 'escalated') return list.filter((ticket) => ticket.escalated || ticket.status === 'ESCALATED')
    if (filter === 'at_risk') return list.filter((ticket) => ticket.sla.state === 'AT_RISK')
    return list.filter((ticket) => ticket.sla.state === 'BREACHED')
  }, [tickets, filter])

  const active = tickets.find((ticket) => ticket.ticket_number === selected) ?? visible[0] ?? null
  const history = useFetch<{ escalations: Escalation[] }>(
    active ? `/api/escalations/tickets/${active.ticket_number}` : null,
  )

  const regionMix = useMemo(() => {
    const map = new Map<string, { healthy: number; at_risk: number; breached: number }>()
    tickets.forEach((ticket) => {
      if (ticket.status === 'RESOLVED' || ticket.status === 'CLOSED') return
      const entry = map.get(ticket.region) ?? { healthy: 0, at_risk: 0, breached: 0 }
      if (ticket.sla.state === 'BREACHED') entry.breached += 1
      else if (ticket.sla.state === 'AT_RISK') entry.at_risk += 1
      else entry.healthy += 1
      map.set(ticket.region, entry)
    })
    return Array.from(map.entries()).map(([name, value]) => ({ name, ...value }))
  }, [tickets])

  const holidayCount = tickets.filter((ticket) => ticket.sla.holiday_adjustment_applied).length

  return (
    <div className="space-y-3">
      {queue.error ? <ErrorNote message={queue.error} onRetry={queue.reload} /> : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Escalated to managers"
          value={queue.data?.counts.escalated ?? '—'}
          hint="Status ESCALATED, queue ESCALATION_MANAGER"
          tone="rose"
          testId="war-escalated"
        />
        <Kpi label="At risk" value={queue.data?.counts.at_risk ?? '—'} hint="Past the at-risk threshold" tone="amber" />
        <Kpi label="Breached" value={queue.data?.counts.breached ?? '—'} hint="Effective due date passed" tone="rose" />
        <Kpi
          label="Holiday-adjusted"
          value={holidayCount}
          hint="At-risk threshold lowered to 50%"
          tone="slate"
          testId="war-holiday"
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_330px]">
        <Section
          title="Escalation inventory"
          subtitle={`viewer ${queue.data?.viewer ?? '—'} · countdown ticking (${tick % 60}s)`}
          action={
            <div className="w-[170px]">
              <Select
                label=""
                value={filter}
                allowEmpty={false}
                options={[
                  { value: 'escalated', label: 'Escalated only' },
                  { value: 'at_risk', label: 'At risk' },
                  { value: 'breached', label: 'Breached' },
                  { value: 'all', label: 'All open' },
                ]}
                onChange={(value) => setFilter(value as typeof filter)}
                testId="war-filter"
              />
            </div>
          }
        >
          {queue.loading && tickets.length === 0 ? (
            <Spinner label="Loading escalation queue…" />
          ) : visible.length === 0 ? (
            <EmptyState title="Nothing in this bucket" hint="Switch the filter to inspect another SLA state." />
          ) : (
            <div className="max-h-[460px] overflow-auto rounded-lg border border-line">
              <table className="table-base">
                <thead>
                  <tr>
                    <th>Ticket</th>
                    <th>Priority</th>
                    <th>Region</th>
                    <th>Owner</th>
                    <th>Governing rule</th>
                    <th>Travel</th>
                    <th>SLA</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((ticket) => (
                    <tr
                      key={ticket.ticket_number}
                      data-testid={`em-ticket-${ticket.ticket_number}`}
                      onClick={() => setSelected(ticket.ticket_number)}
                      className={`cursor-pointer ${active?.ticket_number === ticket.ticket_number ? 'bg-brand-50' : ''}`}
                    >
                      <td>
                        <Link to={`/w2/${ticket.ticket_number}`} className="link mono text-[11px] font-semibold">
                          {ticket.ticket_number}
                        </Link>
                        <p className="max-w-[260px] truncate text-[11px] text-slate-600">{ticket.title}</p>
                      </td>
                      <td>
                        <Badge tone={priorityTone(ticket.priority)}>{ticket.priority}</Badge>
                      </td>
                      <td className="text-[11.5px]">{ticket.region}</td>
                      <td className="text-[11.5px]">
                        {ticket.assigned_to ?? <span className="text-slate-400">unassigned</span>}
                        <p className="text-[10px] text-slate-400">{ticket.queue}</p>
                      </td>
                      <td className="mono text-[10.5px] text-slate-500">{ticket.sla.governing_rule}</td>
                      <td className="text-[10.5px] text-slate-500">{ticket.booking?.check_in_local ?? '—'}</td>
                      <td>
                        <SlaCell
                          state={ticket.sla.state}
                          secondsRemaining={ticket.sla.seconds_remaining}
                          dueAt={fmtDateTime(ticket.sla.effective_due_at, ticket.booking?.timezone)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>

        <div className="space-y-3">
          <Section title="Managers on duty" subtitle="Ownership is real — escalation reassigns the ticket">
            <div className="space-y-1.5">
              {(queue.data?.managers ?? []).map((manager) => (
                <div key={manager.id} className="flex items-center justify-between gap-2 rounded-lg border border-line px-2.5 py-1.5">
                  <div>
                    <p className="text-[12px] font-medium">{manager.full_name}</p>
                    <p className="text-[10px] text-slate-500">
                      {manager.region} · {manager.timezone}
                    </p>
                  </div>
                  <div className="text-right">
                    <Badge tone={manager.is_online ? 'green' : 'slate'}>{manager.is_online ? 'online' : 'offline'}</Badge>
                    <p className="mt-0.5 text-[10px] text-slate-500">{manager.active_escalations} escalation(s)</p>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section
            title="Selected case"
            subtitle={active ? active.ticket_number : 'Pick a row'}
            action={<UserCheck className="h-4 w-4 text-slate-400" aria-hidden />}
          >
            {active ? (
              <div className="space-y-1.5 text-[11.5px]">
                <p className="text-[12px] font-medium text-navy">{active.title}</p>
                <p className="text-slate-600">{active.description}</p>
                <p className="text-[11px] text-slate-500">
                  agency {active.agency ?? '—'} · booking {active.booking?.tboh_id ?? '—'} ·{' '}
                  {active.booking?.hotel_name ?? 'no property'}
                </p>
                {(history.data?.escalations ?? []).map((escalation) => (
                  <div key={escalation.id} className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1.5">
                    <p className="text-[11px] font-semibold text-rose-800">
                      {escalation.escalated_by} → {escalation.assigned_em}
                    </p>
                    <p className="text-[11px] text-rose-700">{escalation.reason}</p>
                    <p className="text-[10px] text-rose-500">{fmtDateTime(escalation.escalated_at)}</p>
                  </div>
                ))}
                {(history.data?.escalations ?? []).length === 0 ? (
                  <p className="text-[11px] text-slate-500">No escalation record — this case is in the watch list only.</p>
                ) : null}
                <Link to={`/w2/${active.ticket_number}`} className="link text-[11px]">
                  Open the full case workspace →
                </Link>
              </div>
            ) : (
              <EmptyState title="No case selected" />
            )}
          </Section>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-3">
        <TrendLine
          data={trend.data?.by_week ?? []}
          testId="chart-escalation-trend"
          title="Escalations per week"
          subtitle={`${trend.data?.total ?? 0} total over ${trend.data?.window_weeks ?? 8} weeks`}
          color="#EF4444"
        />
        <StackedStates data={regionMix} testId="chart-war-region" title="SLA state by region" subtitle="Open cases" />
        <VerticalBars
          data={(deadlines.data?.deadlines ?? []).slice(0, 8).map((deadline) => ({
            name: deadline.ticket_number,
            value: Math.round((new Date(deadline.due_at).getTime() - Date.now()) / 3_600_000),
          }))}
          testId="chart-deadline-pressure"
          title="Deadline pressure (hours to due)"
          subtitle="Negative = already overdue"
          layout="vertical"
          height={240}
          color="#2563EB"
        />
      </div>

      <Section
        title="Nearest deadlines"
        subtitle="Governing due date per ticket, including LCD and check-in buffers"
        action={<Clock className="h-4 w-4 text-slate-400" aria-hidden />}
      >
        <div className="grid gap-1.5 md:grid-cols-2 xl:grid-cols-3">
          {(deadlines.data?.deadlines ?? []).map((deadline) => (
            <div key={deadline.ticket_number} className="flex items-center justify-between gap-2 rounded-lg border border-line px-2.5 py-1.5">
              <div className="min-w-0">
                <p className="mono text-[11px] font-semibold">{deadline.ticket_number}</p>
                <p className="truncate text-[10.5px] text-slate-500">{deadline.title}</p>
                <p className="text-[10px] text-slate-400">
                  {humanise(deadline.governing_rule)} · {fmtDateTime(deadline.due_at)}
                </p>
              </div>
              <Badge tone={deadline.state === 'BREACHED' ? 'rose' : deadline.state === 'AT_RISK' ? 'amber' : 'green'}>
                {deadline.state}
              </Badge>
            </div>
          ))}
        </div>
        <p className="mt-2 flex items-center gap-1.5 text-[10.5px] text-slate-400">
          <ShieldCheck className="h-3 w-3" aria-hidden />
          Escalations write an immutable event, reassign ownership and move the queue to ESCALATION_MANAGER in one
          transaction.
        </p>
      </Section>

      {(queue.data?.counts.breached ?? 0) > 0 ? (
        <p className="flex items-center gap-1.5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[11px] text-rose-800">
          <AlertOctagon className="h-3.5 w-3.5" aria-hidden />
          {queue.data?.counts.breached} ticket(s) are past their effective SLA. These are computed from the stored due
          date, not a static flag.
        </p>
      ) : null}
    </div>
  )
}
