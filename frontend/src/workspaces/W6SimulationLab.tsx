/**
 * W6 — OpsDesk Live Simulation Lab.
 *
 * Runs the five seeded journeys against the live API. Every result shown here is
 * the actual HTTP response of that run — nothing is simulated in the browser.
 */

import { useState } from 'react'
import { CheckCircle2, Database, FlaskConical, PlayCircle, RotateCcw, SkipForward, XCircle } from 'lucide-react'
import { Badge, EmptyState, ErrorNote, Kpi, Section, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { fmtDateTime, fmtNumber } from '../lib/format'
import { useFetch } from '../lib/hooks'
import type { JourneyResult, SimStatus } from '../lib/types'

interface RunEnvelope {
  journey: string
  title: string
  steps: {
    name: string
    expected: string
    actual: string
    passed: boolean
    evidence: Record<string, unknown>
    duration_ms: number
    error: string | null
  }[]
  steps_total: number
  steps_passed: number
  passed: boolean
  started_at: string
  finished_at: string
  console?: string
}

export default function W6SimulationLab() {
  const status = useFetch<SimStatus>('/api/simulation/status')
  const results = useFetch<{ available: boolean; journeys: JourneyResult[]; generated_at?: string }>(
    '/api/simulation/journeys/results',
  )
  const [running, setRunning] = useState<string | null>(null)
  const [consoleLines, setConsoleLines] = useState<string[]>([])
  const [outcomes, setOutcomes] = useState<Record<string, JourneyResult>>({})
  const [error, setError] = useState<string | null>(null)
  const [maintenance, setMaintenance] = useState<string | null>(null)

  const stored = new Map<string, JourneyResult>((results.data?.journeys ?? []).map((row) => [row.journey, row]))

  function log(line: string) {
    setConsoleLines((lines) => [...lines, `[${new Date().toLocaleTimeString('en-GB', { hour12: false })}] ${line}`].slice(-200))
  }

  async function seed() {
    setRunning('seed')
    setError(null)
    log('POST /api/simulation/seed — reloading the synthetic dataset')
    try {
      const result = await api<{ seeded: boolean; counts: Record<string, number> }>('/api/simulation/seed', { method: 'POST' })
      log(`Seeded: ${Object.entries(result.counts).map(([key, value]) => `${key}=${value}`).join(' · ')}`)
      setMaintenance('Dataset reseeded. Journey expectations are calibrated to this state.')
      status.reload()
      results.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Seed failed')
      log(`ERROR ${err instanceof Error ? err.message : 'seed failed'}`)
    } finally {
      setRunning(null)
    }
  }

  async function reset() {
    setRunning('reset')
    setError(null)
    log('POST /api/simulation/reset — deleting runtime rows, then reseeding')
    try {
      const result = await api<{ reset: boolean; rows_deleted: Record<string, number> }>('/api/simulation/reset', {
        method: 'POST',
      })
      log(`Reset: ${Object.entries(result.rows_deleted).map(([key, value]) => `${key}=${value}`).join(' · ')}`)
      setMaintenance('Database reset to the seeded baseline.')
      status.reload()
      results.reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
      log(`ERROR ${err instanceof Error ? err.message : 'reset failed'}`)
    } finally {
      setRunning(null)
    }
  }

  async function runJourney(key: string, reseed = true) {
    setRunning(key)
    setError(null)
    log(`POST /api/simulation/journeys/${key}/run?reseed=${reseed}`)
    try {
      const result = await api<RunEnvelope>(`/api/simulation/journeys/${key}/run?reseed=${reseed}`, {
        method: 'POST',
      })
      const journeyResult: JourneyResult = {
        journey: result.journey,
        title: result.title,
        started_at: result.started_at,
        finished_at: result.finished_at,
        steps: result.steps,
        steps_total: result.steps_total,
        steps_passed: result.steps_passed,
        passed: result.passed,
        console: result.console,
      }
      setOutcomes({ ...outcomes, [key]: journeyResult })
      log(`${key}: ${result.steps_passed}/${result.steps_total} steps passed — ${result.passed ? 'PASS' : 'FAIL'}`)
      if (result.console) setConsoleLines((lines) => [...lines, ...result.console!.split('\n')].slice(-300))
      results.reload()
      status.reload()
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Journey failed'
      setError(message)
      log(`ERROR ${key}: ${message}`)
    } finally {
      setRunning(null)
    }
  }

  async function runAll() {
    setRunning('all')
    setError(null)
    log('Restoring the seeded baseline, then running journeys A → E sequentially')
    try {
      await api('/api/simulation/seed', { method: 'POST' })
    } catch (err) {
      log(`WARN could not reseed automatically: ${err instanceof Error ? err.message : 'unknown error'}`)
    }
    for (const key of ['A', 'B', 'C', 'D', 'E']) {
      // The baseline is already fresh, so individual runs skip their own reseed.
      await runJourney(key, false)
    }
    setRunning(null)
    results.reload()
    status.reload()
    log('All journeys finished')
  }

  const journeys = status.data?.journeys ?? []
  const passes = Object.values(outcomes).filter((row) => row.passed).length

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-1 xl:grid-cols-4">
        <Kpi
          label="Tickets in database"
          value={status.data?.database.tickets ?? '—'}
          hint={`${status.data?.database.active ?? 0} active`}
          tone="brand"
        />
        <Kpi
          label="Classifier mode"
          value={status.data?.classifier_mode ?? '—'}
          hint={status.data?.classifier_error ?? 'joblib pipeline loaded from disk'}
          tone="green"
        />
        <Kpi label="Journeys run this session" value={`${Object.keys(outcomes).length}/5`} hint={`${passes} passed`} tone="slate" />
        <Kpi
          label="Dataset"
          value={status.data?.datasets_are_synthetic ? 'Synthetic' : 'Mixed'}
          hint="No real TBO data is present"
          tone="amber"
        />
      </div>

      <Section
        title="Lab controls"
        subtitle={
          status.data
            ? `API target ${status.data.internal_base_url} · results file ${results.data?.generated_at ? fmtDateTime(results.data.generated_at) : 'none yet'}`
            : 'Loading lab status…'
        }
        action={<FlaskConical className="h-4 w-4 text-slate-400" aria-hidden />}
      >
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-ghost" onClick={seed} disabled={running !== null} data-testid="lab-seed">
            <Database className="h-3.5 w-3.5" aria-hidden /> {running === 'seed' ? 'Seeding…' : 'Seed dataset'}
          </button>
          <button type="button" className="btn-ghost" onClick={reset} disabled={running !== null} data-testid="lab-reset">
            <RotateCcw className="h-3.5 w-3.5" aria-hidden /> {running === 'reset' ? 'Resetting…' : 'Reset & reseed'}
          </button>
          <button type="button" className="btn-primary" onClick={runAll} disabled={running !== null} data-testid="lab-run-all">
            <PlayCircle className="h-3.5 w-3.5" aria-hidden /> {running === 'all' ? 'Running all journeys…' : 'Run all journeys'}
          </button>
          {running && running !== 'all' ? <Spinner label={`Running journey ${running}…`} /> : null}
        </div>
        {maintenance ? <p className="mt-2 rounded-md bg-blue-50 px-2 py-1 text-[11px] text-blue-800">{maintenance}</p> : null}
        {error ? <div className="mt-2"><ErrorNote message={error} onRetry={() => setError(null)} /></div> : null}
        <p className="mt-2 text-[11px] text-slate-500">
          Each journey signs in as its own seeded identity and drives the public API with real HTTP calls. A single run
          restores the seeded baseline first (reseed=true) so a journey can always be replayed; “Run all journeys”
          reseeds once and then runs A → E. Journey E also streams a 50,000-row export and validates the row count.
        </p>
      </Section>

      <div className="grid gap-3 xl:grid-cols-2">
        {journeys.map((journey) => {
          const result = outcomes[journey.key] ?? stored.get(journey.key)
          const isRunning = running === journey.key || running === 'all'
          return (
            <section key={journey.key} className="card card-pad" data-testid={`journey-card-${journey.key}`}>
              <header className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-[13px] font-semibold text-navy">
                    Journey {journey.key} · {journey.title}
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    {journey.agency} · {journey.workspace}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {result ? (
                    <Badge tone={result.passed ? 'green' : 'rose'}>
                      {result.passed ? <CheckCircle2 className="h-3 w-3" aria-hidden /> : <XCircle className="h-3 w-3" aria-hidden />}
                      {result.steps_passed}/{result.steps_total}
                    </Badge>
                  ) : (
                    <Badge tone="slate">not run</Badge>
                  )}
                  <button
                    type="button"
                    className="btn-ghost !px-2 !py-1"
                    onClick={() => runJourney(journey.key)}
                    disabled={running !== null}
                    data-testid={`journey-run-${journey.key}`}
                  >
                    {isRunning ? 'Running…' : 'Run'}
                  </button>
                </div>
              </header>

              <p className="mt-1.5 text-[11.5px] leading-relaxed text-slate-600">{journey.expected}</p>

              <div className="mt-2 space-y-1">
                {(result?.steps ?? []).map((step) => (
                  <div key={step.name} className="rounded-md border border-line px-2 py-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[11.5px] font-medium text-navy">
                        {step.passed ? (
                          <CheckCircle2 className="mr-1 inline h-3 w-3 text-emerald-500" aria-hidden />
                        ) : (
                          <XCircle className="mr-1 inline h-3 w-3 text-rose-500" aria-hidden />
                        )}
                        {step.name}
                      </p>
                      <span className="shrink-0 text-[10px] text-slate-400">{fmtNumber(step.duration_ms)} ms</span>
                    </div>
                    <p className="mt-0.5 text-[11px] text-slate-600" data-testid={`journey-actual-${journey.key}`}>
                      {step.actual}
                    </p>
                    <p className="text-[10px] text-slate-400">expected: {step.expected}</p>
                    {step.error ? <p className="text-[10px] text-rose-600">error: {step.error}</p> : null}
                  </div>
                ))}
                {!result ? (
                  <EmptyState
                    title="No result in this session"
                    hint="Press Run — the browser calls the simulation endpoint, which performs the journey server-side."
                  />
                ) : null}
              </div>

              <p className="mt-1.5 text-[10.5px] text-slate-400" data-testid={`journey-steps-${journey.key}`}>
                {result
                  ? `${result.steps_passed}/${result.steps_total} steps passed · ${fmtDateTime(result.finished_at)}`
                  : 'steps: —'}
              </p>
            </section>
          )
        })}
        {journeys.length === 0 ? <EmptyState title="Simulation status unavailable" /> : null}
      </div>

      <Section
        title="Lab console"
        subtitle="Live request log for this session"
        action={
          <button type="button" className="btn-ghost" onClick={() => setConsoleLines([])}>
            <SkipForward className="h-3.5 w-3.5" aria-hidden /> Clear
          </button>
        }
      >
        <pre
          className="mono max-h-[280px] overflow-auto rounded-lg bg-navy p-3 text-[11px] leading-relaxed text-slate-200"
          data-testid="lab-console"
        >
          {consoleLines.length ? consoleLines.join('\n') : 'Console idle. Run a journey to see the HTTP exchange.'}
        </pre>
      </Section>
    </div>
  )
}
