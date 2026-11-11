/**
 * W5 — Product Intelligence & Governance Hub.
 *
 * Insights are computed by the API over real ticket rows. Exports stream from a
 * server-side iterator and are validated by re-reading the written file.
 */

import { useState } from 'react'
import {
  Bug,
  CheckCircle2,
  Database,
  Download,
  FileSpreadsheet,
  Lightbulb,
  Play,
  RefreshCw,
  Tags,
} from 'lucide-react'
import { Donut, TrendLine, VerticalBars } from '../components/charts'
import { Badge, EmptyState, ErrorNote, Kpi, Meter, Notice, Section, Select, Spinner, Tabs } from '../components/ui'
import { api, downloadExport, streamExport } from '../lib/api'
import { fmtBytes, fmtDateTime, fmtNumber, humanise } from '../lib/format'
import { useFetch } from '../lib/hooks'
import type { BugSuggestion, ExportJob, ExportValidation, ProductBugRecord, ProductIntelligence } from '../lib/types'

type Tab = 'insights' | 'bugs' | 'exports'

export default function W5IntelligenceHub() {
  const [tab, setTab] = useState<Tab>('insights')

  return (
    <div className="space-y-3">
      <Tabs
        testId="intel-tabs"
        testIdPrefix="intel-tabs"
        active={tab}
        onChange={setTab}
        tabs={[
          { key: 'insights', label: 'Product insights' },
          { key: 'bugs', label: 'Bug suggestions' },
          { key: 'exports', label: 'Governance exports' },
        ]}
      />
      {tab === 'insights' ? <Insights /> : null}
      {tab === 'bugs' ? <Bugs /> : null}
      {tab === 'exports' ? <Exports /> : null}
    </div>
  )
}

/* --------------------------------------------------------------- insights */

function Insights() {
  const [windowDays, setWindowDays] = useState('30')
  const data = useFetch<ProductIntelligence>(`/api/analytics/product-intelligence?window_days=${windowDays}`)
  const [themeMessage, setThemeMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const intel = data.data
  const inventory = intel?.inventory_sync

  async function rebuildThemes() {
    setBusy(true)
    try {
      const result = await api<{ count: number }>('/api/analytics/themes/refresh', { method: 'POST' })
      setThemeMessage(`${result.count} theme(s) refreshed from the current ticket corpus.`)
      data.reload()
    } catch (err) {
      setThemeMessage(err instanceof Error ? err.message : 'Theme refresh failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <Section
        title="Analysis window"
        subtitle={
          intel
            ? `${intel.tickets_in_window} tickets since ${fmtDateTime(intel.window_start)} · ${intel.data_notice}`
            : 'Loading…'
        }
        action={
          <div className="flex items-end gap-2">
            <div className="w-[150px]">
              <Select
                label=""
                value={windowDays}
                allowEmpty={false}
                options={[
                  { value: '7', label: 'Last 7 days' },
                  { value: '30', label: 'Last 30 days' },
                  { value: '90', label: 'Last 90 days' },
                  { value: '365', label: 'Last 365 days' },
                ]}
                onChange={setWindowDays}
                testId="intel-window"
              />
            </div>
            <button type="button" className="btn-ghost" onClick={data.reload}>
              <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Refresh
            </button>
            <button type="button" className="btn-primary" onClick={rebuildThemes} disabled={busy} data-testid="intel-theme-refresh">
              <Tags className="h-3.5 w-3.5" aria-hidden /> {busy ? 'Extracting…' : 'Extract themes'}
            </button>
          </div>
        }
      >
        {data.error ? <ErrorNote message={data.error} onRetry={data.reload} /> : null}
        {themeMessage ? (
          <p className="mb-2 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-800">{themeMessage}</p>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi
            label="Top intent"
            value={intel?.intent_distribution[0]?.label ?? '—'}
            hint={intel?.intent_distribution[0] ? `${intel.intent_distribution[0].count} tickets` : undefined}
            tone="brand"
          />
          <Kpi
            label="Most complained supplier"
            value={intel?.supplier_complaints[0]?.supplier ?? '—'}
            hint={intel?.supplier_complaints[0] ? `${intel.supplier_complaints[0].tickets} tickets` : undefined}
            tone="amber"
          />
          <Kpi
            label="Open refunds"
            value={intel?.refund_bottleneck.open_refunds ?? '—'}
            hint={intel ? `mean open age ${fmtNumber(intel.refund_bottleneck.avg_open_age_hours)}h` : undefined}
            tone="rose"
          />
          <Kpi
            label="Inventory-sync tickets"
            value={intel?.inventory_sync.ticket_count ?? '—'}
            hint={intel ? `${intel.inventory_sync.suppliers.length} supplier(s) affected` : undefined}
            tone="slate"
          />
        </div>
      </Section>

      {data.loading && !intel ? <Spinner label="Computing insights…" /> : null}

      {intel ? (
        <>
          <div className="grid gap-3 xl:grid-cols-2">
            <Donut
              data={intel.intent_distribution.map((entry) => ({ name: entry.label, value: entry.count }))}
              testId="chart-intent-distribution"
              title="Common intents"
              subtitle={`${intel.intent_distribution.length} canonical intents in the window`}
              height={240}
            />
            <VerticalBars
              data={intel.supplier_complaints.map((entry) => ({ name: entry.supplier, value: entry.tickets }))}
              testId="chart-supplier-complaints"
              title="Supplier complaint volume"
              subtitle="Tickets per supplier in the window"
              layout="vertical"
              height={240}
            />
            <TrendLine
              data={intel.weekly_trends}
              testId="chart-intel-weekly"
              title="Weekly ticket trend"
              subtitle="ISO weeks counted from ticket creation"
              height={230}
            />
            <VerticalBars
              data={intel.resolution_time_distribution.map((entry) => ({ name: entry.bucket, value: entry.count }))}
              testId="chart-resolution-distribution"
              title="Resolution-time distribution"
              subtitle={
                intel.resolution_stats.avg_hours !== null
                  ? `${intel.resolution_stats.resolved} resolved · mean ${fmtNumber(intel.resolution_stats.avg_hours)}h`
                  : 'No resolved tickets in the window'
              }
              height={230}
            />
          </div>

          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
            <Section
              title="Regional performance"
              subtitle="Volume, breaches and mean resolution time per region"
              action={<Database className="h-4 w-4 text-slate-400" aria-hidden />}
            >
              <div className="overflow-auto rounded-lg border border-line">
                <table className="table-base">
                  <thead>
                    <tr>
                      <th>Region</th>
                      <th>Tickets</th>
                      <th>Breached</th>
                      <th>Resolved</th>
                      <th>Mean resolution</th>
                      <th>Breach rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {intel.regional_performance.map((row) => (
                      <tr key={row.region}>
                        <td className="text-[12px] font-medium">{row.region}</td>
                        <td className="tabular-nums text-[12px]">{row.tickets}</td>
                        <td className="tabular-nums text-[12px] text-rose-600">{row.breached}</td>
                        <td className="tabular-nums text-[12px]">{row.resolved}</td>
                        <td className="tabular-nums text-[12px]">
                          {row.avg_resolution_hours !== null ? `${fmtNumber(row.avg_resolution_hours)}h` : '—'}
                        </td>
                        <td className="w-[130px]">
                          <div className="flex items-center gap-1.5">
                            <Meter value={row.tickets ? (row.breached / row.tickets) * 100 : 0} max={100} tone="rose" />
                            <span className="w-9 text-right text-[10.5px] tabular-nums text-slate-500">
                              {row.tickets ? Math.round((row.breached / row.tickets) * 100) : 0}%
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="mt-2 grid gap-2 md:grid-cols-2">
                <div className="rounded-lg border border-rose-200 bg-rose-50 p-2.5">
                  <p className="label !text-rose-700">Refund bottleneck</p>
                  <p className="text-[11.5px] text-rose-900">
                    {intel.refund_bottleneck.open_refunds} open refund ticket(s), mean age{' '}
                    {fmtNumber(intel.refund_bottleneck.avg_open_age_hours)}h
                    {intel.refund_bottleneck.avg_resolved_hours !== null
                      ? ` · resolved mean ${fmtNumber(intel.refund_bottleneck.avg_resolved_hours)}h`
                      : ''}
                  </p>
                  {intel.refund_bottleneck.oldest_open ? (
                    <p className="mt-1 text-[11px] text-rose-800">
                      Oldest: <strong>{intel.refund_bottleneck.oldest_open.ticket_number}</strong> (
                      {intel.refund_bottleneck.oldest_open.supplier ?? 'unknown supplier'}) —{' '}
                      {fmtNumber(intel.refund_bottleneck.oldest_open.age_hours)}h old
                    </p>
                  ) : null}
                </div>
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-2.5">
                  <p className="label !text-amber-800">Inventory &amp; rate sync</p>
                  <p className="text-[11.5px] text-amber-900">
                    {inventory?.ticket_count ?? 0} ticket(s) across {inventory?.suppliers.length ?? 0} supplier(s)
                  </p>
                  <p className="mt-1 text-[10.5px] text-amber-800">{inventory?.suppliers.join(', ') || 'No pattern detected'}</p>
                  <p className="mt-1 truncate text-[10.5px] text-amber-700" title={inventory?.ticket_numbers.join(', ')}>
                    {inventory?.ticket_numbers.slice(0, 8).join(', ')}
                    {(inventory?.ticket_numbers.length ?? 0) > 8 ? ' …' : ''}
                  </p>
                </div>
              </div>
            </Section>

            <Section
              title="Extracted themes"
              subtitle="Recurring language patterns tagged on tickets"
              action={<Tags className="h-4 w-4 text-slate-400" aria-hidden />}
            >
              <div className="max-h-[330px] space-y-1.5 overflow-y-auto">
                {intel.themes.map((theme) => (
                  <div key={`${theme.category}-${theme.name}`} className="rounded-lg border border-line px-2.5 py-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11.5px] font-medium text-navy">{humanise(theme.name)}</span>
                      <Badge tone="slate">{theme.category}</Badge>
                    </div>
                    <p className="text-[10.5px] text-slate-500">
                      {theme.occurrences} occurrence(s) · {theme.distinct_suppliers} supplier(s)
                    </p>
                  </div>
                ))}
                {intel.themes.length === 0 ? <EmptyState title="No themes extracted yet" /> : null}
              </div>
              {intel.theme_tags.length > 0 ? (
                <p className="mt-2 text-[10.5px] text-slate-500">
                  {intel.theme_tags.length} persisted theme tag(s), latest{' '}
                  {fmtDateTime(intel.theme_tags[0].last_seen)}
                </p>
              ) : (
                <p className="mt-2 text-[10.5px] text-slate-500">
                  Run “Extract themes” to persist tags against individual tickets.
                </p>
              )}
            </Section>
          </div>
        </>
      ) : null}
    </div>
  )
}

/* ------------------------------------------------------------------- bugs */

function Bugs() {
  const suggestions = useFetch<{ suggestions: BugSuggestion[]; window_days: number; min_tickets: number; note: string }>(
    '/api/analytics/bug-suggestions',
  )
  const existing = useFetch<{ bugs: ProductBugRecord[]; count: number }>('/api/analytics/product-bugs')
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function createRecord(suggestion: BugSuggestion) {
    const key = `${suggestion.supplier}-${suggestion.intent}`
    setBusyKey(key)
    setError(null)
    try {
      const record = await api<{ bug_code: string; status: string }>('/api/analytics/product-bugs', {
        method: 'POST',
        body: {
          supplier: suggestion.supplier,
          intent: suggestion.intent,
          title: `${suggestion.supplier} ${suggestion.intent_label} pattern`,
          suggested_action: suggestion.suggested_action,
          related_ticket_ids: suggestion.ticket_ids,
          frequency: suggestion.frequency,
        },
      })
      setMessage(`Created ${record.bug_code} (${record.status}) as a local product-bug record.`)
      existing.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the record')
    } finally {
      setBusyKey(null)
    }
  }

  return (
    <div className="space-y-3">
      <Section
        title="Recurring supplier patterns"
        subtitle={
          suggestions.data
            ? `${suggestions.data.suggestions.length} suggestion(s) from tickets sharing a supplier + intent pattern (≥ ${suggestions.data.min_tickets} tickets in ${suggestions.data.window_days} days)`
            : 'Detecting patterns…'
        }
        action={
          <button type="button" className="btn-ghost" onClick={suggestions.reload}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Re-run detection
          </button>
        }
      >
        {suggestions.error ? <ErrorNote message={suggestions.error} onRetry={suggestions.reload} /> : null}
        {message ? <p className="mb-2 rounded-md bg-emerald-50 px-2 py-1 text-[11px] text-emerald-800">{message}</p> : null}
        {error ? <p className="mb-2 text-[11px] text-rose-600">{error}</p> : null}
        <Notice>
          {suggestions.data?.note ??
            'Suggestions are stored in this database only. No Jira or external tracker integration is implemented or claimed.'}
        </Notice>

        <div className="mt-2 space-y-2">
          {(suggestions.data?.suggestions ?? []).map((suggestion) => {
            const key = `${suggestion.supplier}-${suggestion.intent}`
            return (
              <article key={key} className="rounded-lg border border-line p-3" data-testid={`bug-suggestion-${key}`}>
                <header className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Bug className="h-4 w-4 text-rose-500" aria-hidden />
                    <h3 className="text-[13px] font-semibold text-navy">
                      {suggestion.supplier} · {suggestion.intent_label}
                    </h3>
                    <Badge tone="rose">{suggestion.frequency} tickets</Badge>
                    <Badge tone="slate">{suggestion.confidence}</Badge>
                  </div>
                  <button
                    type="button"
                    className="btn-ghost"
                    onClick={() => createRecord(suggestion)}
                    disabled={busyKey === key}
                    data-testid={`bug-create-${key}`}
                  >
                    <Lightbulb className="h-3.5 w-3.5" aria-hidden /> {busyKey === key ? 'Recording…' : 'Record product bug'}
                  </button>
                </header>
                <p className="mt-1 text-[12px] leading-relaxed text-slate-700">{suggestion.suggested_action}</p>
                <div className="mt-1.5 grid gap-2 text-[10.5px] text-slate-500 md:grid-cols-2">
                  <p>
                    Period {fmtDateTime(suggestion.period.from)} → {fmtDateTime(suggestion.period.to)} · links{' '}
                    {suggestion.related_ticket_links}
                  </p>
                  <p className="truncate" title={suggestion.ticket_numbers.join(', ')}>
                    Tickets: {suggestion.ticket_numbers.join(', ')}
                  </p>
                </div>
                <details className="mt-1">
                  <summary className="cursor-pointer text-[11px] text-brand">Evidence ({suggestion.evidence.length})</summary>
                  <ul className="mt-1 space-y-0.5">
                    {suggestion.evidence.map((line) => (
                      <li key={line} className="text-[11px] text-slate-600">
                        • {line}
                      </li>
                    ))}
                  </ul>
                </details>
              </article>
            )
          })}
          {(suggestions.data?.suggestions ?? []).length === 0 ? (
            <EmptyState title="No recurring pattern above the threshold" hint="Lower the threshold or widen the window." />
          ) : null}
        </div>
      </Section>

      <Section
        title="Recorded product bugs"
        subtitle="Local records created from the suggestions above"
        action={<span className="text-[11px] text-slate-400">{existing.data?.count ?? 0} record(s)</span>}
      >
        <div className="overflow-auto rounded-lg border border-line">
          <table className="table-base">
            <thead>
              <tr>
                <th>Code</th>
                <th>Title</th>
                <th>Supplier</th>
                <th>Intent</th>
                <th>Frequency</th>
                <th>Status</th>
                <th>Created</th>
                <th>Tickets</th>
              </tr>
            </thead>
            <tbody>
              {(existing.data?.bugs ?? []).map((bug) => (
                <tr key={bug.bug_code}>
                  <td className="mono text-[11px] font-semibold">{bug.bug_code}</td>
                  <td className="max-w-[220px] truncate text-[11.5px]">{bug.title}</td>
                  <td className="text-[11.5px]">{bug.supplier}</td>
                  <td className="text-[11.5px]">{bug.intent_label ?? '—'}</td>
                  <td className="tabular-nums text-[11.5px]">{bug.frequency}</td>
                  <td>
                    <Badge tone="amber">{bug.status}</Badge>
                  </td>
                  <td className="text-[11px] text-slate-500">{fmtDateTime(bug.created_at)}</td>
                  <td className="text-[11px] text-slate-500">{bug.related_ticket_ids.length}</td>
                </tr>
              ))}
              {(existing.data?.bugs ?? []).length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-4 text-center text-[12px] text-slate-500">
                    No product bug recorded yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}

/* ---------------------------------------------------------------- exports */

function Exports() {
  const [format, setFormat] = useState<'CSV' | 'JSONL'>('CSV')
  const [source, setSource] = useState<'SYNTHETIC_BENCHMARK' | 'DB'>('SYNTHETIC_BENCHMARK')
  const [rows, setRows] = useState('50000')
  const [region, setRegion] = useState('')
  const [status, setStatus] = useState('OPEN')
  const [progress, setProgress] = useState<{ bytes: number; rows: number; total: number } | null>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<{ jobUuid: string; filename: string; bytes: number; rows: number; totalRows: number; elapsed: number } | null>(null)
  const [validation, setValidation] = useState<ExportValidation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloadNote, setDownloadNote] = useState<string | null>(null)
  const jobs = useFetch<{ jobs: ExportJob[]; count: number }>('/api/exports/jobs')

  async function start() {
    setRunning(true)
    setError(null)
    setResult(null)
    setValidation(null)
    setDownloadNote(null)
    const total = Number(rows) || 50000
    setProgress({ bytes: 0, rows: 0, total })
    const started = performance.now()
    try {
      const streamed = await streamExport(
        {
          file_format: format,
          source,
          total_rows: total,
          region: region || null,
          status: status || null,
        },
        (bytes, received) => setProgress({ bytes, rows: received, total }),
      )
      const elapsed = performance.now() - started
      setResult({ ...streamed, elapsed })
      jobs.reload()
      // Validate by re-reading the file the server actually wrote.
      const check = await api<ExportValidation>(`/api/exports/${streamed.jobUuid}/validate`)
      setValidation(check)
      jobs.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setRunning(false)
    }
  }

  async function download() {
    if (!result) return
    try {
      const file = await downloadExport(result.jobUuid)
      setDownloadNote(`Downloaded ${file.filename} (${fmtBytes(file.bytes)}) from the server-written file.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    }
  }

  const pctDone = progress && progress.total ? Math.min(100, (progress.rows / progress.total) * 100) : 0

  return (
    <div className="space-y-3">
      <Section
        title="Generate and stream rows"
        subtitle="StreamingResponse with a server-side iterator (batch size 5,000) — the browser receives bytes as they are produced"
        action={<FileSpreadsheet className="h-4 w-4 text-slate-400" aria-hidden />}
      >
        <div className="grid gap-2 md:grid-cols-4">
          <Select
            label="Format"
            value={format}
            allowEmpty={false}
            options={[
              { value: 'CSV', label: 'CSV' },
              { value: 'JSONL', label: 'JSONL' },
            ]}
            onChange={(value) => setFormat(value as 'CSV' | 'JSONL')}
            testId="export-format"
          />
          <Select
            label="Source"
            value={source}
            allowEmpty={false}
            options={[
              { value: 'SYNTHETIC_BENCHMARK', label: 'Synthetic benchmark rows' },
              { value: 'DB', label: 'Live database rows' },
            ]}
            onChange={(value) => setSource(value as 'SYNTHETIC_BENCHMARK' | 'DB')}
            testId="export-source"
          />
          <label className="block">
            <span className="label">Rows</span>
            <input
              className="input"
              type="number"
              min={1}
              max={200000}
              value={rows}
              onChange={(event) => setRows(event.target.value)}
              data-testid="export-rows"
            />
          </label>
          <Select
            label="Region filter"
            value={region}
            options={['MEA', 'APAC', 'EU', 'AMER'].map((value) => ({ value, label: value }))}
            onChange={setRegion}
            testId="export-region"
          />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button type="button" className="btn-primary" onClick={start} disabled={running} data-testid="export-start">
            <Play className="h-3.5 w-3.5" aria-hidden />
            {running ? 'Streaming…' : `Generate and stream ${Number(rows || 0).toLocaleString('en-GB')} rows`}
          </button>
          <Select
            label=""
            value={status}
            allowEmpty={false}
            options={[
              { value: 'OPEN', label: 'Status filter: open' },
              { value: '', label: 'Status filter: none' },
            ]}
            onChange={setStatus}
          />
          <span className="text-[10.5px] text-slate-500">
            DB source streams the real ticket rows (fewer than the requested count when the filters are narrow).
          </span>
        </div>

        {progress ? (
          <div className="mt-2">
            <div className="flex items-center justify-between text-[11px] text-slate-600">
              <span>
                {progress.rows.toLocaleString('en-GB')} / {progress.total.toLocaleString('en-GB')} rows received ·{' '}
                {fmtBytes(progress.bytes)}
              </span>
              <span className="tabular-nums">{pctDone.toFixed(1)}%</span>
            </div>
            <Meter value={pctDone} max={100} tone={pctDone >= 100 ? 'green' : 'brand'} />
          </div>
        ) : null}

        {error ? <div className="mt-2"><ErrorNote message={error} /></div> : null}
      </Section>

      {result ? (
        <Section
          title="Stream result"
          testId="export-result"
          subtitle={`Job ${result.jobUuid}`}
          action={<CheckCircle2 className="h-4 w-4 text-emerald-500" aria-hidden />}
        >
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Rows received" value={result.rows.toLocaleString('en-GB')} hint={`requested ${result.totalRows.toLocaleString('en-GB')}`} />
            <Kpi label="Bytes received" value={fmtBytes(result.bytes)} hint={result.filename} />
            <Kpi label="Client duration" value={`${Math.round(result.elapsed)} ms`} hint="wall clock in the browser" />
            <Kpi
              label="Throughput"
              value={`${Math.round(result.rows / Math.max(0.001, result.elapsed / 1000)).toLocaleString('en-GB')}/s`}
              hint="rows per second"
              tone="brand"
            />
          </div>
        </Section>
      ) : null}

      {validation ? (
        <Section
          title="File validation"
          testId="export-validation"
          subtitle={validation.note}
          action={
            <Badge tone={validation.row_count_matches && validation.readable ? 'green' : 'rose'}>
              {validation.row_count_matches && validation.readable ? 'PASSED' : 'FAILED'}
            </Badge>
          }
        >
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <Kpi label="Rows in file" value={validation.actual_rows_in_file.toLocaleString('en-GB')} hint={`expected ${validation.expected_rows.toLocaleString('en-GB')}`} />
            <Kpi label="Columns" value={validation.column_count} hint={`format ${validation.file_format}`} />
            <Kpi label="Server duration" value={`${fmtNumber(validation.duration_ms)} ms`} hint={`${fmtNumber(validation.throughput_rows_per_sec)} rows/s`} />
            <Kpi label="Peak memory" value={`${fmtNumber(validation.peak_memory_mb)} MB`} hint="VmRSS sampled during the stream" tone="slate" />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button type="button" className="btn-primary" onClick={download} data-testid="export-download">
              <Download className="h-3.5 w-3.5" aria-hidden /> Download file
            </button>
            <span className="text-[11px] text-slate-500">file check: {validation.result}</span>
            {downloadNote ? <span className="text-[11px] text-emerald-700">{downloadNote}</span> : null}
          </div>
        </Section>
      ) : null}

      <Section
        title="Export jobs"
        testId="export-jobs"
        subtitle="Every stream is recorded with rows, duration, size, throughput and peak memory"
        action={
          <button type="button" className="btn-ghost" onClick={jobs.reload}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Refresh
          </button>
        }
      >
        <div className="max-h-[320px] overflow-auto rounded-lg border border-line">
          <table className="table-base">
            <thead>
              <tr>
                <th>Job</th>
                <th>Status</th>
                <th>Format</th>
                <th>Source</th>
                <th>Rows</th>
                <th>Duration</th>
                <th>Size</th>
                <th>Throughput</th>
                <th>Peak mem</th>
                <th>By</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {(jobs.data?.jobs ?? []).map((job) => (
                <tr key={job.job_uuid}>
                  <td className="mono text-[10.5px]" title={job.job_uuid}>
                    #{job.job_id} {job.job_uuid.slice(0, 8)}
                  </td>
                  <td>
                    <Badge tone={job.status === 'COMPLETED' ? 'green' : job.status === 'FAILED' ? 'rose' : 'brand'}>
                      {job.status}
                    </Badge>
                  </td>
                  <td className="text-[11px]">{job.format}</td>
                  <td className="text-[11px]">{job.data_source === 'DB' ? 'database' : 'synthetic'}</td>
                  <td className="tabular-nums text-[11px]">{job.rows_streamed.toLocaleString('en-GB')}</td>
                  <td className="tabular-nums text-[11px]">{job.duration_ms !== null ? `${fmtNumber(job.duration_ms)} ms` : '—'}</td>
                  <td className="tabular-nums text-[11px]">{job.file_size_mb !== null ? `${fmtNumber(job.file_size_mb)} MB` : '—'}</td>
                  <td className="tabular-nums text-[11px]">{job.throughput_rows_per_sec !== null ? `${Math.round(job.throughput_rows_per_sec).toLocaleString('en-GB')}/s` : '—'}</td>
                  <td className="tabular-nums text-[11px]">{job.peak_memory_mb !== null ? `${fmtNumber(job.peak_memory_mb)} MB` : '—'}</td>
                  <td className="text-[10.5px] text-slate-500">{job.requested_by}</td>
                  <td className="text-[10.5px] text-slate-500">{fmtDateTime(job.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[10.5px] text-slate-400">
          Hot tier (0–90 days) is Postgres in the reference architecture; this MVP stores rows in SQLite and is described
          separately in documentation/Storage_Architecture.md.
        </p>
      </Section>
    </div>
  )
}
