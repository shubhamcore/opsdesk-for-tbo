/**
 * W2 — Unified Ticket & Booking Case Workspace (three panes).
 *
 * Left: queue / search. Centre: classification, case brief, main thread.
 * Right: booking context, SLA evidence, side conversations, transfer + escalate.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowRightLeft,
  Brain,
  GitBranch,
  Mail,
  MessageSquarePlus,
  Plus,
  Send,
  ShieldAlert,
  Sparkles,
  Bot,
  Ticket as TicketIcon,
} from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  Badge,
  EmptyState,
  ErrorNote,
  Meter,
  Modal,
  Notice,
  Section,
  Select,
  SlaCell,
  Spinner,
  TextInput,
} from '../components/ui'
import { api } from '../lib/api'
import { CHART_COLORS, fmtDateTime, fmtMoney, humanise, priorityTone } from '../lib/format'
import { useDebounced, useFetch } from '../lib/hooks'
import { useSession } from '../lib/store'
import type {
  AgentRun,
  SideConversation,
  TicketDetail,
  TicketListResponse,
  TicketRow,
  TransferRecord,
} from '../lib/types'

const QUEUES = [
  'MEA-SUPPORT',
  'APAC-SUPPORT',
  'EU-TRIAGE',
  'EU-SENIOR-OPS',
  'AMER-SUPPORT',
  'ESCALATION_MANAGER',
]

interface CreateResult {
  ticket_id: number
  ticket_number: string
  extraction: { tboh_ids: string[]; extraction_source: string; [key: string]: unknown }
  classification: { intent: string; confidence: number | null; source: string; reasoning: string[] }
  booking: { tboh_id: string; hotel_name: string } | null
  sla: { state: string; effective_due_at: string; governing_rule: string }
}

export default function W2CaseWorkspace() {
  const params = useParams()
  const navigate = useNavigate()
  const { can } = useSession()

  const [search, setSearch] = useState('')
  const debounced = useDebounced(search, 250)
  const [selected, setSelected] = useState<string | null>(params.ticketId ?? null)
  const [composerOpen, setComposerOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const list = useFetch<TicketListResponse>(`/api/tickets?search=${encodeURIComponent(debounced)}`)
  const detail = useFetch<TicketDetail>(selected ? `/api/tickets/${selected}` : null)

  useEffect(() => {
    if (params.ticketId) setSelected(params.ticketId)
  }, [params.ticketId])

  // Default to the first row once the queue arrives so the panes are never empty.
  useEffect(() => {
    if (!selected && list.data?.tickets?.length) setSelected(list.data.tickets[0].ticket_number)
  }, [list.data, selected])

  const ticket = detail.data
  const rows: TicketRow[] = list.data?.tickets ?? []

  function openTicket(number: string) {
    setSelected(number)
    navigate(`/w2/${number}`, { replace: true })
  }

  function afterMutation(message: string) {
    setNotice(message)
    detail.reload()
    list.reload()
  }

  return (
    <div className="space-y-3">
      {notice ? (
        <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-[12px] text-emerald-800">
          <span>{notice}</span>
          <button type="button" className="text-emerald-700 underline" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      ) : null}

      <div className="grid gap-3 xl:grid-cols-[292px_minmax(0,1fr)_368px]">
        {/* ---------------------------------------------------------- left pane */}
        <div className="space-y-3">
          <Section
            title="Case search"
            subtitle="Ticket, booking (TBOH) or agency"
            action={
              <button type="button" className="btn-primary !px-2 !py-1" onClick={() => setComposerOpen(true)}>
                <Plus className="h-3.5 w-3.5" aria-hidden /> New
              </button>
            }
          >
            <input
              className="input"
              placeholder="TCK-101 · TBOH-778899 · Wanderlust"
              value={search}
              data-testid="case-search"
              onChange={(event) => setSearch(event.target.value)}
            />
            <div className="mt-2 max-h-[560px] space-y-1 overflow-y-auto">
              {list.loading && rows.length === 0 ? <Spinner label="Loading tickets…" /> : null}
              {rows.map((row) => {
                const active = row.ticket_number === selected
                return (
                  <button
                    key={row.ticket_number}
                    type="button"
                    onClick={() => openTicket(row.ticket_number)}
                    data-testid={`case-list-${row.ticket_number}`}
                    className={`w-full rounded-lg border px-2.5 py-2 text-left transition ${
                      active ? 'border-brand bg-brand-50' : 'border-line hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="mono text-[11px] font-semibold text-navy">{row.ticket_number}</span>
                      <Badge tone={priorityTone(row.priority)}>{row.priority}</Badge>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-[11.5px] leading-snug text-slate-700">{row.title}</p>
                    <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
                      <span className="truncate">{row.booking?.tboh_id ?? 'no booking'}</span>
                      <span className={row.sla.state === 'BREACHED' ? 'text-rose-600' : row.sla.state === 'AT_RISK' ? 'text-amber-600' : ''}>
                        {row.sla.state}
                      </span>
                    </div>
                  </button>
                )
              })}
              {!list.loading && rows.length === 0 ? <EmptyState title="No matching tickets" /> : null}
            </div>
          </Section>
        </div>

        {/* -------------------------------------------------------- centre pane */}
        <div className="space-y-3">
          {detail.error ? <ErrorNote message={detail.error} onRetry={detail.reload} /> : null}
          {detail.loading && !ticket ? <Spinner label="Loading case…" /> : null}
          {ticket ? (
            <>
              <Section
                title={`${ticket.ticket_number} · ${ticket.title}`}
                subtitle={`${ticket.agency ?? 'No agency'} · ${ticket.region} · ${ticket.queue} · owner ${
                  ticket.assigned_to ?? 'unassigned'
                }`}
                action={
                  <div className="flex items-center gap-1.5">
                    <Badge tone={priorityTone(ticket.priority)}>{ticket.priority}</Badge>
                    <Badge tone={ticket.status === 'RESOLVED' ? 'green' : 'brand'}>{humanise(ticket.status)}</Badge>
                    {ticket.escalated ? <Badge tone="rose">Escalated</Badge> : null}
                  </div>
                }
              >
                <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-700">{ticket.description}</p>
                <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-slate-500">
                  <span>created {fmtDateTime(ticket.created_at)}</span>
                  <span>updated {fmtDateTime(ticket.updated_at)}</span>
                  {ticket.resolved_at ? <span>resolved {fmtDateTime(ticket.resolved_at)}</span> : null}
                </div>
              </Section>

              <section className="card card-pad" data-testid="classification-card">
                <header className="mb-2 flex items-center justify-between">
                  <h2 className="section-title flex items-center gap-1.5">
                    <Brain className="h-3.5 w-3.5 text-brand" aria-hidden /> Intent classification
                  </h2>
                  <span className="text-[11px] text-slate-500">
                    source <strong>{ticket.classification.source ?? '—'}</strong>
                  </span>
                </header>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-[15px] font-semibold text-navy">
                    {ticket.classification.label ?? 'Unclassified'}
                  </span>
                  <span className="mono text-[11px] text-slate-500">{ticket.classification.intent}</span>
                  {ticket.classification.confidence !== null ? (
                    <Badge tone="brand">confidence {(ticket.classification.confidence * 100).toFixed(1)}%</Badge>
                  ) : null}
                </div>
                <div className="mt-2">
                  <p className="label">Calibrated class scores</p>
                  <div style={{ height: 132 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={Object.entries(ticket.classification.scores ?? {})
                          .map(([name, value]) => ({ name: humanise(name), value: Number(value) }))
                          .sort((a, b) => b.value - a.value)}
                        layout="vertical"
                        margin={{ top: 0, right: 16, bottom: 0, left: 118 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#EDF1F7" />
                        <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 10 }} />
                        <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={112} />
                        <Tooltip formatter={(value: number) => [value.toFixed(4), 'score']} />
                        <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                          {Object.keys(ticket.classification.scores ?? {}).map((key, index) => (
                            <Cell
                              key={key}
                              fill={key === ticket.classification.intent ? CHART_COLORS[0] : '#CBD5E1'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <ul className="mt-1 space-y-0.5">
                  {(ticket.classification.reasoning ?? []).map((reason) => (
                    <li key={reason} className="text-[11.5px] leading-relaxed text-slate-600">
                      • {reason}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="card card-pad" data-testid="case-brief-card">
                <header className="mb-2 flex items-center justify-between">
                  <h2 className="section-title flex items-center gap-1.5">
                    <Sparkles className="h-3.5 w-3.5 text-brand" aria-hidden /> AI case brief
                  </h2>
                  <span className="text-[10px] text-slate-400">
                    {ticket.case_brief.method} · {ticket.case_brief.tickets_in_case} ticket(s) in case
                  </span>
                </header>
                <ol className="space-y-1.5">
                  {ticket.case_brief.points.map((point, index) => (
                    <li key={point} className="flex gap-2 text-[12.5px] leading-relaxed text-slate-700">
                      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[10px] font-bold text-brand">
                        {index + 1}
                      </span>
                      {point}
                    </li>
                  ))}
                </ol>
                <p className="mt-2 border-t border-line pt-2 text-[10.5px] text-slate-500">
                  Evidence used: {ticket.case_brief.sources.ticket_ids.length} ticket(s),{' '}
                  {ticket.case_brief.sources.message_count} message(s),{' '}
                  {ticket.case_brief.sources.side_conversation_count} side conversation(s), booking{' '}
                  {ticket.case_brief.sources.booking_id ?? '—'} · generated {fmtDateTime(ticket.case_brief.generated_at)}
                </p>
              </section>

              <AgentMesh ticket={ticket} canReview={can('agents')} />

              <ThreadPanel
                ticket={ticket}
                canNote={can('internal_notes')}
                onDone={() => afterMutation('Message added to the main thread.')}
              />
            </>
          ) : null}
        </div>

        {/* --------------------------------------------------------- right pane */}
        <div className="space-y-3">
          {ticket ? (
            <>
              <BookingContext ticket={ticket} />
              <SlaPanel ticket={ticket} />
              <GraphPanel ticket={ticket} onOpen={openTicket} />
              <SideConversations
                ticket={ticket}
                onDone={(message) => afterMutation(message)}
              />
              <TransferPanel ticket={ticket} onDone={(message) => afterMutation(message)} />
              {can('escalate') ? <EscalatePanel ticket={ticket} onDone={(message) => afterMutation(message)} /> : null}
            </>
          ) : (
            <div className="card card-pad">
              <p className="text-[12px] text-slate-500">Select a ticket to load its booking context.</p>
            </div>
          )}
        </div>
      </div>

      <NewTicketModal
        open={composerOpen}
        onClose={() => setComposerOpen(false)}
        onCreated={(result) => {
          setComposerOpen(false)
          setNotice(
            `Created ${result.ticket_number} — extracted ${result.extraction.tboh_ids.join(', ') || 'no booking id'} (${result.extraction.extraction_source}), classified ${result.classification.intent} via ${result.classification.source}.`,
          )
          openTicket(result.ticket_number)
        }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ thread */

const AGENT_STATUS_TONE: Record<string, 'green' | 'amber' | 'slate' | 'rose'> = {
  OK: 'green',
  ATTENTION: 'amber',
  SKIPPED: 'slate',
  ERROR: 'rose',
}

function AgentMesh({ ticket, canReview }: { ticket: TicketDetail; canReview: boolean }) {
  const [run, setRun] = useState<AgentRun | null>(null)
  const [history, setHistory] = useState<AgentRun[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadHistory = () => {
    api<{ runs: AgentRun[] }>('/api/agents/runs', { query: { ticket_id: ticket.id, limit: 5 } })
      .then((payload) => setHistory(payload.runs))
      .catch(() => setHistory([]))
  }

  useEffect(() => {
    setRun(null)
    setError(null)
    if (canReview) loadHistory()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket.id, canReview])

  const runSwarm = async () => {
    setBusy(true)
    setError(null)
    try {
      const payload = await api<AgentRun>(`/api/agents/cases/${ticket.ticket_number}/run`, {
        body: { objective: 'CASE_REVIEW' },
      })
      setRun(payload)
      loadHistory()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Agent run failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card card-pad" data-testid="agent-mesh-card">
      <header className="mb-2 flex items-start justify-between gap-3">
        <div>
          <h2 className="section-title flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5 text-brand" aria-hidden /> Agent mesh
          </h2>
          <p className="text-[11px] text-slate-500">
            8 specialist reviewers · each restricted to a declared tool allow-list · no external model
          </p>
        </div>
        {canReview ? (
          <button
            type="button"
            className="btn-primary !px-2.5 !py-1"
            onClick={runSwarm}
            disabled={busy}
            data-testid="agent-run-button"
          >
            {busy ? 'Reviewing…' : 'Run agent review'}
          </button>
        ) : null}
      </header>

      {!canReview ? (
        <p className="text-[11.5px] text-slate-500" data-testid="agent-mesh-restricted">
          Agent reviews are an internal operations capability. You can read this case, but the
          swarm runs under an ops role — ask your TBO contact for the review summary.
        </p>
      ) : null}

      {error ? <ErrorNote message={error} /> : null}

      {run ? (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-600" data-testid="agent-run-summary">
            <Badge tone={run.status === 'COMPLETED' ? 'green' : run.status === 'PARTIAL' ? 'amber' : 'rose'}>
              {run.status}
            </Badge>
            <span className="font-mono text-[10.5px] text-slate-500">{run.run_uuid}</span>
            <span>{run.agent_count} agents</span>
            <span>· {(run.overall_confidence * 100).toFixed(0)}% mean confidence</span>
            <span>· {run.duration_ms.toFixed(0)} ms</span>
            <span>· {run.created_by}</span>
          </div>
          <p className="mb-2 text-[11.5px] text-slate-600">{run.headline}</p>

          <div className="grid gap-2 sm:grid-cols-2">
            {run.agents.map((agent) => (
              <div
                key={agent.agent}
                className="rounded-lg border border-line bg-white p-2"
                data-testid={`agent-card-${agent.agent}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11.5px] font-semibold text-slate-800">{agent.title}</span>
                  <Badge tone={AGENT_STATUS_TONE[agent.status] ?? 'slate'}>{agent.status}</Badge>
                </div>
                <p className="mt-1 text-[11px] leading-snug text-slate-600">{agent.summary}</p>
                <p className="mt-1 text-[10px] text-slate-400">
                  conf {(agent.confidence * 100).toFixed(0)}% · {agent.tool_calls.length} tool call(s) ·{' '}
                  {agent.duration_ms.toFixed(0)} ms
                </p>
              </div>
            ))}
          </div>

          <div className="mt-2 rounded-lg border border-line bg-slate-50 p-2" data-testid="agent-plan">
            <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-slate-500">
              Prioritised plan
            </p>
            <ol className="space-y-1">
              {run.plan.length === 0 ? (
                <li className="text-[11px] text-slate-500">No action proposed — nothing to escalate.</li>
              ) : (
                run.plan.map((item) => (
                  <li key={item.action} className="text-[11.5px] leading-snug text-slate-700">
                    <span className="mr-1 font-mono text-[10px] font-bold text-brand">{item.priority}</span>
                    {item.action}
                    <span className="ml-1 text-[10px] text-slate-400">from {item.source_agent}</span>
                  </li>
                ))
              )}
            </ol>
          </div>
        </>
      ) : (
        <p className="text-[11.5px] text-slate-500">
          Run the mesh to have every specialist review this case. Each finding cites the tool output
          that produced it; nothing is written to the case until you act on it.
        </p>
      )}

      {history.length ? (
        <div className="mt-2 border-t border-line pt-2" data-testid="agent-history">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Recent reviews on this case
          </p>
          <ul className="mt-1 space-y-0.5">
            {history.map((item) => (
              <li key={item.run_uuid} className="flex items-center justify-between gap-2 text-[10.5px] text-slate-500">
                <span className="font-mono">{item.run_uuid}</span>
                <span>
                  {item.plan.length} action(s) · {item.status} · {fmtDateTime(item.created_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

function ThreadPanel({
  ticket,
  canNote,
  onDone,
}: {
  ticket: TicketDetail
  canNote: boolean
  onDone: () => void
}) {
  const [content, setContent] = useState('')
  const [type, setType] = useState<'PUBLIC_REPLY' | 'INTERNAL_NOTE'>('PUBLIC_REPLY')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send() {
    if (!content.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api(`/api/tickets/${ticket.id}/messages`, {
        method: 'POST',
        body: { content: content.trim(), message_type: type },
      })
      setContent('')
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not post the message')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card card-pad" data-testid="ticket-thread">
      <header className="mb-2 flex items-center justify-between">
        <h2 className="section-title">Main thread</h2>
        <span className="text-[11px] text-slate-400">{ticket.messages.length} message(s)</span>
      </header>
      <div className="max-h-[280px] space-y-2 overflow-y-auto pr-1">
        {ticket.messages.map((message) => {
          const internal = message.message_type === 'INTERNAL_NOTE'
          return (
            <article
              key={message.id}
              className={`rounded-lg border px-3 py-2 ${
                internal ? 'border-amber-200 bg-amber-50' : 'border-line bg-white'
              }`}
            >
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-medium text-navy">
                  {message.sender_name}{' '}
                  <span className="font-normal text-slate-400">({humanise(message.sender_role)})</span>
                </span>
                <span className="text-slate-400">{fmtDateTime(message.created_at)}</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-700">{message.content}</p>
              <span className="mt-1 inline-block text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                {internal ? 'internal note — not visible to the agency' : 'public reply'}
              </span>
            </article>
          )
        })}
        {ticket.messages.length === 0 ? <EmptyState title="No messages yet" /> : null}
      </div>

      <div className="mt-3 border-t border-line pt-2">
        <div className="flex gap-1.5">
          <button
            type="button"
            className={type === 'PUBLIC_REPLY' ? 'btn-primary !py-1' : 'btn-ghost !py-1'}
            onClick={() => setType('PUBLIC_REPLY')}
          >
            Public reply
          </button>
          {canNote ? (
            <button
              type="button"
              className={type === 'INTERNAL_NOTE' ? 'btn-primary !py-1' : 'btn-ghost !py-1'}
              onClick={() => setType('INTERNAL_NOTE')}
            >
              Internal note
            </button>
          ) : null}
        </div>
        <textarea
          className="input mt-2 h-16 resize-none"
          placeholder={type === 'INTERNAL_NOTE' ? 'Internal note — hidden from the agency' : 'Reply to the agency'}
          value={content}
          data-testid="thread-input"
          onChange={(event) => setContent(event.target.value)}
        />
        {error ? <p className="mt-1 text-[11px] text-rose-600">{error}</p> : null}
        <div className="mt-1.5 flex items-center justify-between">
          <span className="text-[10.5px] text-slate-400">
            {type === 'INTERNAL_NOTE' ? 'Stored on the ticket, excluded from agency view' : 'Delivered to the agency requesters'}
          </span>
          <button type="button" className="btn-primary" onClick={send} disabled={busy || !content.trim()} data-testid="thread-send">
            <Send className="h-3.5 w-3.5" aria-hidden /> {busy ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </section>
  )
}

/* --------------------------------------------------------- booking + SLA */

function BookingContext({ ticket }: { ticket: TicketDetail }) {
  const booking = ticket.booking
  if (!booking) {
    return (
      <Section title="Booking context" testId="booking-context">
        <EmptyState title="No booking linked" hint="This case has no TBOH booking reference." />
      </Section>
    )
  }
  const rows: [string, string][] = [
    ['TBO booking', booking.tboh_id],
    ['Property', `${booking.hotel_name} · ${booking.destination_city}, ${booking.destination_country}`],
    ['Supplier', `${booking.supplier_name}${booking.supplier_email ? ` · ${booking.supplier_email}` : ''}`],
    ['Passenger', booking.passenger_name],
    ['Value', fmtMoney(booking.amount, booking.currency)],
    ['Booking status', humanise(booking.booking_status)],
    ['Check-in (local)', booking.check_in_local ?? '—'],
    ['Last cancel date', booking.lcd_local ?? '—'],
    ['Agency', `${booking.agency_name ?? '—'} · ${booking.agency_tier ?? '—'}`],
    ['Timezone', booking.timezone],
  ]
  return (
    <Section title="Booking context" testId="booking-context" subtitle="The operational context — not the ticket">
      <dl className="space-y-1">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3 text-[11.5px]">
            <dt className="shrink-0 text-slate-500">{label}</dt>
            <dd className="truncate text-right font-medium text-navy" title={value}>
              {value}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 rounded-md bg-slate-50 px-2 py-1.5 text-[10.5px] text-slate-500">
        Times shown in the booking's own timezone ({booking.timezone}); stored in UTC.
      </p>
    </Section>
  )
}

function SlaPanel({ ticket }: { ticket: TicketDetail }) {
  const sla = ticket.sla
  const tone = sla.state === 'HEALTHY' ? 'green' : sla.state === 'AT_RISK' ? 'amber' : sla.state === 'BREACHED' ? 'rose' : 'slate'
  return (
    <section className="card card-pad" data-testid="sla-panel">
      <header className="mb-2 flex items-center justify-between">
        <h2 className="section-title">Effective SLA</h2>
        <Badge tone={tone}>{sla.state}</Badge>
      </header>
      <div className="mb-2 flex items-baseline gap-2">
        <span className="text-[20px] font-semibold tabular-nums text-navy">
          {sla.minutes_remaining >= 0
            ? `${Math.floor(sla.minutes_remaining / 60)}h ${Math.abs(sla.minutes_remaining % 60)}m left`
            : `${Math.abs(Math.floor(sla.minutes_remaining / 60))}h ${Math.abs(sla.minutes_remaining % 60)}m over`}
        </span>
        <span className="text-[11px] text-slate-500">governed by {sla.governing_rule}</span>
      </div>
      <Meter value={sla.elapsed_ratio * 100} max={100} tone={tone} />
      <dl className="mt-2 space-y-1 text-[11.5px]">
        <Row label="Effective due (UTC)" value={fmtDateTime(sla.effective_due_at)} />
        <Row label={`Priority deadline (${ticket.priority})`} value={fmtDateTime(sla.priority_due_at)} />
        <Row label="LCD − 2h" value={fmtDateTime(sla.lcd_deadline)} />
        <Row label="Check-in − 4h" value={fmtDateTime(sla.checkin_deadline)} />
        <Row label="At-risk threshold" value={`${(sla.at_risk_threshold * 100).toFixed(0)}% elapsed`} />
        <Row label="Urgency weight" value={sla.urgency_weight.toFixed(2)} />
      </dl>
      <ul className="mt-2 space-y-1">
        {sla.reasons.map((reason) => (
          <li key={reason} className="rounded-md bg-slate-50 px-2 py-1 text-[11px] text-slate-600">
            {reason}
          </li>
        ))}
      </ul>
      {sla.holiday_adjustment_applied ? (
        <p className="mt-1.5 rounded-md border border-amber-200 bg-amber-50 px-2 py-1 text-[10.5px] text-amber-800">
          Regional holiday window: at-risk threshold lowered from 75% to 50% and recorded on this ticket.
        </p>
      ) : null}
      {sla.expired_travel_deadline ? (
        <p className="mt-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10.5px] text-slate-600">
          Travel deadline already passed — the travel-derived rule is ignored rather than zeroed.
        </p>
      ) : null}
      {sla.missing_dates.length > 0 ? (
        <p className="mt-1.5 text-[10.5px] text-slate-500">Missing dates: {sla.missing_dates.join(', ')}</p>
      ) : null}
    </section>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-slate-500">{label}</dt>
      <dd className="tabular-nums text-navy">{value}</dd>
    </div>
  )
}

/* ------------------------------------------------------------------ graph */

function GraphPanel({ ticket, onOpen }: { ticket: TicketDetail; onOpen: (number: string) => void }) {
  return (
    <Section
      title="Booking-first case graph"
      testId="graph-panel"
      subtitle={`${ticket.related_tickets.length} linked ticket(s) on ${ticket.booking?.tboh_id ?? 'no booking'}`}
      action={<GitBranch className="h-4 w-4 text-slate-400" aria-hidden />}
    >
      <div className="space-y-1.5">
        <div className="flex items-center gap-2 rounded-lg border border-brand bg-brand-50 px-2.5 py-1.5">
          <TicketIcon className="h-3.5 w-3.5 text-brand" aria-hidden />
          <span className="mono text-[11px] font-semibold text-navy">{ticket.ticket_number}</span>
          <span className="text-[10.5px] text-slate-600">this ticket</span>
        </div>
        {ticket.related_tickets.map((related) => (
          <button
            key={related.ticket_id}
            type="button"
            onClick={() => onOpen(related.ticket_number)}
            className="flex w-full items-center justify-between gap-2 rounded-lg border border-line px-2.5 py-1.5 text-left hover:bg-slate-50"
          >
            <span className="min-w-0">
              <span className="mono text-[11px] font-medium text-navy">{related.ticket_number}</span>
              <span className="ml-1.5 text-[10px] uppercase tracking-wide text-slate-400">{related.link_type}</span>
              <p className="truncate text-[11px] text-slate-600">{related.title}</p>
            </span>
            <span className="shrink-0 text-right text-[10px] text-slate-400">
              {humanise(related.intent)}
              <br />
              {related.status}
            </span>
          </button>
        ))}
        {ticket.related_tickets.length === 0 ? (
          <EmptyState title="First ticket on this booking" hint="Later tickets for the same TBOH will link here." />
        ) : null}
      </div>
    </Section>
  )
}

/* --------------------------------------------------- side conversations */

function SideConversations({ ticket, onDone }: { ticket: TicketDetail; onDone: (message: string) => void }) {
  const [openForm, setOpenForm] = useState(false)
  const [subject, setSubject] = useState('')
  const [counterparty, setCounterparty] = useState('')
  const [channel, setChannel] = useState<'SUPPLIER' | 'FINANCE' | 'AGENCY' | 'INTERNAL'>('SUPPLIER')
  const [recipients, setRecipients] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const list = recipients
        .split(/[,\s;]+/)
        .map((value) => value.trim())
        .filter(Boolean)
      await api(`/api/tickets/${ticket.id}/side-conversations`, {
        method: 'POST',
        body: { channel_type: channel, subject, counterparty_name: counterparty, recipients: list },
      })
      setOpenForm(false)
      setSubject('')
      setCounterparty('')
      setRecipients('')
      onDone('Side conversation created with explicit recipients.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the conversation')
    } finally {
      setBusy(false)
    }
  }

  async function send(conversation: SideConversation) {
    const content = (drafts[conversation.id] ?? '').trim()
    if (!content) return
    setError(null)
    try {
      const result = await api<{ messages_created: number; recipients: string[] }>(
        `/api/side-conversations/${conversation.id}/messages`,
        { method: 'POST', body: { content } },
      )
      setDrafts({ ...drafts, [conversation.id]: '' })
      onDone(
        `Message sent to ${result.recipients.join(', ')} — ${result.messages_created} delivery record(s), recipients unchanged.`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send the message')
    }
  }

  return (
    <Section
      title="Side conversations"
      testId="side-conversations"
      subtitle="Independent of the main thread — recipients never inherit across a transfer"
      action={
        <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => setOpenForm((value) => !value)}>
          <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden /> New
        </button>
      }
    >
      {openForm ? (
        <div className="mb-2 space-y-1.5 rounded-lg border border-line bg-slate-50 p-2">
          <Select
            label="Channel"
            value={channel}
            allowEmpty={false}
            options={[
              { value: 'SUPPLIER', label: 'Supplier' },
              { value: 'FINANCE', label: 'Finance' },
              { value: 'AGENCY', label: 'Agency' },
              { value: 'INTERNAL', label: 'Internal' },
            ]}
            onChange={(value) => setChannel(value as typeof channel)}
          />
          <TextInput label="Subject" value={subject} onChange={setSubject} />
          <TextInput label="Counterparty" value={counterparty} onChange={setCounterparty} placeholder="Hilton Paris Opera" />
          <TextInput
            label="Recipients (comma separated)"
            value={recipients}
            onChange={setRecipients}
            placeholder="groups@hilton-paris.com"
            testId="recipients-input"
          />
          <button type="button" className="btn-primary w-full" onClick={create} disabled={busy || !subject || !counterparty || !recipients}>
            Create conversation
          </button>
        </div>
      ) : null}

      {error ? <p className="mb-2 text-[11px] text-rose-600">{error}</p> : null}

      <div className="space-y-2">
        {ticket.side_conversations.map((conversation) => (
          <div key={conversation.id} className="rounded-lg border border-line">
            <header className="flex items-start justify-between gap-2 border-b border-line bg-slate-50 px-2.5 py-1.5">
              <div className="min-w-0">
                <p className="truncate text-[11.5px] font-semibold text-navy">{conversation.subject}</p>
                <p className="text-[10px] text-slate-500">
                  {humanise(conversation.channel_type)} · {conversation.counterparty_name} ·{' '}
                  {conversation.messages.length} message(s)
                </p>
              </div>
              <Badge tone="slate">{conversation.status}</Badge>
            </header>
            <div className="px-2.5 py-1.5">
              <p className="label">Explicit recipients</p>
              <div className="flex flex-wrap gap-1" data-testid={`recipients-${conversation.id}`}>
                {conversation.explicit_recipients.map((email) => (
                  <span key={email} className="chip border border-slate-200 bg-slate-100 text-slate-700">
                    <Mail className="h-3 w-3" aria-hidden /> {email}
                  </span>
                ))}
              </div>
              <div className="mt-1.5 max-h-[150px] space-y-1 overflow-y-auto">
                {conversation.messages.map((message) => (
                  <div
                    key={message.id}
                    className={`rounded-md px-2 py-1 text-[11px] ${
                      message.direction === 'OUTBOUND' ? 'bg-brand-50 text-navy' : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    <p className="text-[9.5px] uppercase tracking-wide text-slate-500">
                      {message.direction} · {message.sender_email} → {message.recipient_email} ·{' '}
                      {fmtDateTime(message.created_at)}
                    </p>
                    {message.content}
                  </div>
                ))}
              </div>
              <div className="mt-1.5 flex gap-1">
                <input
                  className="input !py-1 text-[11px]"
                  placeholder="Message this conversation only"
                  value={drafts[conversation.id] ?? ''}
                  onChange={(event) => setDrafts({ ...drafts, [conversation.id]: event.target.value })}
                />
                <button
                  type="button"
                  className="btn-ghost !px-2 !py-1"
                  onClick={() => send(conversation)}
                  disabled={!(drafts[conversation.id] ?? '').trim()}
                >
                  <Send className="h-3.5 w-3.5" aria-hidden />
                </button>
              </div>
            </div>
          </div>
        ))}
        {ticket.side_conversations.length === 0 ? (
          <EmptyState title="No side conversations" hint="Supplier, finance or agency threads stay separate from the main thread." />
        ) : null}
      </div>
    </Section>
  )
}

/* --------------------------------------------------------------- transfer */

function TransferPanel({ ticket, onDone }: { ticket: TicketDetail; onDone: (message: string) => void }) {
  const [open, setOpen] = useState(false)
  const [toQueue, setToQueue] = useState('EU-SENIOR-OPS')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [verification, setVerification] = useState<{
    message: string
    recipients_unchanged: boolean
    preserved_side_conversations: number
    from_queue: string
    to_queue: string
  } | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const result = await api<{
        message: string
        recipients_unchanged: boolean
        preserved_side_conversations: number
        from_queue: string
        to_queue: string
      }>(`/api/tickets/${ticket.id}/transfer`, {
        method: 'POST',
        body: { to_queue: toQueue, note: note || null },
      })
      setVerification(result)
      setOpen(false)
      setNote('')
      onDone(result.message)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Transfer failed')
    } finally {
      setBusy(false)
    }
  }

  const transfers: TransferRecord[] = ticket.transfers ?? []

  return (
    <Section
      title="Transfer ownership"
      subtitle={`Current queue ${ticket.queue}`}
      action={
        <button type="button" className="btn-ghost !px-2 !py-1" onClick={() => setOpen(true)} data-testid="transfer-button">
          <ArrowRightLeft className="h-3.5 w-3.5" aria-hidden /> Transfer
        </button>
      }
    >
      {verification ? (
        <div
          className={`rounded-lg border px-2.5 py-2 text-[11px] ${
            verification.recipients_unchanged
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-rose-200 bg-rose-50 text-rose-800'
          }`}
          data-testid="transfer-verification"
        >
          <p className="font-semibold">
            {verification.from_queue} → {verification.to_queue}
          </p>
          <p className="mt-0.5">{verification.message}</p>
          <p className="mt-0.5">
            Recipients unchanged: <strong>{verification.recipients_unchanged ? 'verified' : 'FAILED'}</strong> ·{' '}
            {verification.preserved_side_conversations} conversation(s) preserved
          </p>
        </div>
      ) : (
        <p className="text-[11px] text-slate-500">
          A transfer moves the queue and owner only. Conversation ids, explicit recipients and full message history are
          preserved and verified afterwards.
        </p>
      )}

      {transfers.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {transfers.map((transfer) => (
            <li key={transfer.id} className="rounded-md bg-slate-50 px-2 py-1 text-[10.5px] text-slate-600">
              {transfer.from_queue} → {transfer.to_queue} · {fmtDateTime(transfer.created_at)} ·{' '}
              {transfer.preserved_side_conversations} conversation(s),{' '}
              {transfer.preserved_recipients.reduce((sum, item) => sum + item.recipients.length, 0)} recipient(s)
            </li>
          ))}
        </ul>
      ) : null}

      <Modal
        open={open}
        title="Transfer ticket"
        onClose={() => setOpen(false)}
        testId="transfer-modal"
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn-primary" onClick={submit} disabled={busy}>
              {busy ? 'Transferring…' : 'Transfer'}
            </button>
          </>
        }
      >
        <div className="space-y-2">
          <Select
            label="Destination queue"
            value={toQueue}
            allowEmpty={false}
            options={QUEUES.map((queue) => ({ value: queue, label: queue }))}
            onChange={setToQueue}
            testId="transfer-queue"
          />
          <label className="block">
            <span className="label">Note (optional)</span>
            <textarea
              className="input h-16 resize-none"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Why is this moving?"
            />
          </label>
          <Notice>
            Side conversations keep their own explicit recipients. The destination group's addresses are never added to
            them, and the transfer is written to the ticket timeline.
          </Notice>
          {error ? <p className="text-[11px] text-rose-600">{error}</p> : null}
        </div>
      </Modal>
    </Section>
  )
}

/* --------------------------------------------------------------- escalate */

function EscalatePanel({ ticket, onDone }: { ticket: TicketDetail; onDone: (message: string) => void }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ status: string; queue: string; assigned_to: { name: string; role: string } } | null>(
    null,
  )

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const response = await api<{
        status: string
        queue: string
        assigned_to: { name: string; role: string }
      }>(`/api/escalations/tickets/${ticket.id}/escalate`, { method: 'POST', body: { reason: reason.trim() } })
      setResult(response)
      setOpen(false)
      setReason('')
      onDone(`Escalated to ${response.assigned_to.name} (${response.assigned_to.role}) — queue ${response.queue}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Escalation failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Section
      title="Escalate to a manager"
      subtitle="Creates an immutable escalation event with real ownership"
      action={
        ticket.escalated ? (
          <Badge tone="rose">Escalated</Badge>
        ) : (
          <button
            type="button"
            className="btn-danger !px-2 !py-1"
            onClick={() => setOpen(true)}
            data-testid="escalate-button"
          >
            <ShieldAlert className="h-3.5 w-3.5" aria-hidden /> Escalate
          </button>
        )
      }
    >
      {result ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-2 text-[11px] text-rose-800">
          Status {result.status} · queue {result.queue} · owner {result.assigned_to.name} ({humanise(result.assigned_to.role)})
        </p>
      ) : null}

      {(ticket.escalations ?? []).length > 0 ? (
        <ul className="space-y-1">
          {ticket.escalations.map((escalation) => (
            <li key={escalation.id} className="rounded-md bg-slate-50 px-2 py-1 text-[10.5px] text-slate-600">
              <p className="font-semibold text-navy">
                {escalation.escalated_by} → {escalation.assigned_em}
              </p>
              <p>{escalation.reason}</p>
              <p className="text-slate-400">
                {fmtDateTime(escalation.escalated_at)} · was {escalation.previous_status} in {escalation.previous_queue}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[11px] text-slate-500">No escalation on this ticket.</p>
      )}

      <Modal
        open={open}
        title={`Escalate ${ticket.ticket_number}`}
        onClose={() => setOpen(false)}
        testId="escalate-modal"
        footer={
          <>
            <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-danger"
              onClick={submit}
              disabled={busy || reason.trim().length < 8}
              data-testid="escalate-submit"
            >
              {busy ? 'Escalating…' : 'Escalate'}
            </button>
          </>
        }
      >
        <div className="space-y-2">
          <label className="block">
            <span className="label">Reason (min 8 characters)</span>
            <textarea
              className="input h-20 resize-none"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="LCD closes within the hour and the supplier is unreachable…"
              data-testid="escalate-reason"
            />
          </label>
          <p className="text-[11px] text-slate-500">
            The selected manager is chosen server-side from the ticket's region. Status becomes ESCALATED, the queue
            becomes ESCALATION_MANAGER and the previous owner is recorded.
          </p>
          {error ? <p className="text-[11px] text-rose-600">{error}</p> : null}
        </div>
      </Modal>
    </Section>
  )
}

/* ------------------------------------------------------------ new ticket */

function NewTicketModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (result: CreateResult) => void
}) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tboh, setTboh] = useState('')
  const [priority, setPriority] = useState('HIGH')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const result = await api<CreateResult>('/api/tickets', {
        method: 'POST',
        body: {
          title: title.trim(),
          description: description.trim(),
          tboh_id: tboh.trim() || null,
          priority,
        },
      })
      setTitle('')
      setDescription('')
      setTboh('')
      onCreated(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the ticket')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open={open}
      title="Raise a ticket"
      onClose={onClose}
      testId="new-ticket-modal"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={busy || !title.trim() || description.trim().length < 10}
            data-testid="new-ticket-submit"
          >
            {busy ? 'Creating…' : 'Create ticket'}
          </button>
        </>
      }
    >
      <div className="space-y-2">
        <TextInput label="Title" value={title} onChange={setTitle} testId="new-ticket-title" />
        <label className="block">
          <span className="label">Description</span>
          <textarea
            className="input h-28 resize-none"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Leave the TBO booking id out to see extraction fill it in from the text."
            data-testid="new-ticket-description"
          />
        </label>
        <TextInput
          label="TBO booking id (optional)"
          value={tboh}
          onChange={setTboh}
          placeholder="Leave blank to auto-extract"
          testId="new-ticket-tboh"
        />
        <Select
          label="Priority"
          value={priority}
          allowEmpty={false}
          options={['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((value) => ({ value, label: value }))}
          onChange={setPriority}
        />
        <Notice>
          Extraction (TBOH-######) and classification run server-side on create. Nothing is hardcoded in the browser.
        </Notice>
        {error ? <p className="text-[11px] text-rose-600">{error}</p> : null}
      </div>
    </Modal>
  )
}
