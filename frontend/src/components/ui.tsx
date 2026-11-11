/** Shared presentational primitives. No data fetching lives here. */

import type { ChangeEvent, ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Inbox, Loader2, X } from 'lucide-react'
import type { Tone } from '../lib/format'
import { fmtCountdown } from '../lib/format'

const TONE_CLASS: Record<Tone, string> = {
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  amber: 'bg-amber-50 text-amber-800 border-amber-200',
  rose: 'bg-rose-50 text-rose-700 border-rose-200',
  slate: 'bg-slate-100 text-slate-600 border-slate-200',
  brand: 'bg-blue-50 text-blue-700 border-blue-200',
}

export function Badge({
  children,
  tone = 'slate',
  testId,
  title,
}: {
  children: ReactNode
  tone?: Tone
  testId?: string
  title?: string
}) {
  return (
    <span className={`chip whitespace-nowrap border ${TONE_CLASS[tone]}`} data-testid={testId} title={title}>
      {children}
    </span>
  )
}

export function Section({
  title,
  action,
  children,
  className = '',
  testId,
  subtitle,
}: {
  title: string
  action?: ReactNode
  children: ReactNode
  className?: string
  testId?: string
  subtitle?: string
}) {
  return (
    <section className={`card card-pad animate-in ${className}`} data-testid={testId}>
      <header className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="section-title">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-[11px] text-slate-500">{subtitle}</p> : null}
        </div>
        {action}
      </header>
      {children}
    </section>
  )
}

export function Kpi({
  label,
  value,
  hint,
  tone = 'slate',
  testId,
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: Tone
  testId?: string
}) {
  const accent: Record<Tone, string> = {
    green: 'text-emerald-600',
    amber: 'text-amber-600',
    rose: 'text-rose-600',
    slate: 'text-navy',
    brand: 'text-brand',
  }
  return (
    <div className="card px-4 py-3" data-testid={testId}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${accent[tone]}`}>{value}</p>
      {hint ? <p className="mt-0.5 text-[11px] text-slate-500">{hint}</p> : null}
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-[13px] text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label ?? 'Loading…'}
    </div>
  )
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 py-8 text-center">
      <Inbox className="h-6 w-6 text-slate-300" aria-hidden />
      <p className="text-[13px] font-medium text-slate-600">{title}</p>
      {hint ? <p className="max-w-sm text-[11px] text-slate-400">{hint}</p> : null}
    </div>
  )
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      className="flex items-start gap-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700"
      role="alert"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="flex-1">
        <p className="font-medium">{message}</p>
        {onRetry ? (
          <button type="button" className="mt-1 underline" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
    </div>
  )
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-900">
      {children}
    </p>
  )
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  testId,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  testId?: string
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div
        className="card w-full max-w-lg animate-in overflow-hidden"
        role="dialog"
        aria-modal="true"
        data-testid={testId}
      >
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <h3 className="text-[14px] font-semibold">{title}</h3>
          <button type="button" className="btn-ghost !border-0 !px-1" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[60vh] overflow-y-auto px-4 py-3 text-[13px]">{children}</div>
        {footer ? (
          <footer className="flex items-center justify-end gap-2 border-t border-line bg-slate-50 px-4 py-3">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  )
}

export function Select({
  label,
  value,
  onChange,
  options,
  testId,
  allowEmpty = true,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  testId?: string
  allowEmpty?: boolean
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <select
        className="input"
        value={value}
        data-testid={testId}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value)}
      >
        {allowEmpty ? <option value="">All</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function TextInput({
  label,
  value,
  onChange,
  placeholder,
  testId,
  type = 'text',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
  testId?: string
  type?: string
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        className="input"
        type={type}
        value={value}
        placeholder={placeholder}
        data-testid={testId}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

/** Live SLA cell: recomputes the countdown from the server's absolute due date. */
export function SlaCell({
  state,
  secondsRemaining,
  dueAt,
  testId,
}: {
  state: string
  secondsRemaining: number
  dueAt: string
  testId?: string
}) {
  const tone: Tone = state === 'HEALTHY' ? 'green' : state === 'AT_RISK' ? 'amber' : state === 'BREACHED' ? 'rose' : 'slate'
  return (
    <span
      className={`chip whitespace-nowrap border ${TONE_CLASS[tone]}`}
      data-testid={testId}
      title={`Governing due: ${dueAt}`}
    >
      <span className="tabular-nums">{state === 'RESOLVED' ? 'RESOLVED' : fmtCountdown(secondsRemaining)}</span>
    </span>
  )
}

export function Tabs<T extends string>({
  tabs,
  active,
  onChange,
  testId,
  testIdPrefix,
}: {
  tabs: { key: T; label: string; count?: number }[]
  active: T
  onChange: (key: T) => void
  testId?: string
  testIdPrefix?: string
}) {
  return (
    <div className="flex gap-1 border-b border-line" data-testid={testId} role="tablist">
      {tabs.map((tab) => {
        const selected = tab.key === active
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={selected}
            data-testid={testIdPrefix ? `${testIdPrefix}-${tab.key.toLowerCase()}` : undefined}
            onClick={() => onChange(tab.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition ${
              selected ? 'border-brand text-brand' : 'border-transparent text-slate-500 hover:text-navy'
            }`}
          >
            {tab.label}
            {typeof tab.count === 'number' ? (
              <span className="ml-1.5 rounded-full bg-slate-100 px-1.5 text-[11px] text-slate-600">{tab.count}</span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

export function StatusToast({ message, tone = 'green' }: { message: string; tone?: Tone }) {
  return (
    <div className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-[12px] ${TONE_CLASS[tone]}`} role="status">
      <CheckCircle2 className="h-4 w-4" aria-hidden />
      <span>{message}</span>
    </div>
  )
}

/** Deterministic bar used for score / utilization meters. */
export function Meter({ value, max = 100, tone = 'brand' }: { value: number; max?: number; tone?: Tone }) {
  const ratio = Math.max(0, Math.min(1, max === 0 ? 0 : value / max))
  const fill: Record<Tone, string> = {
    green: 'bg-emerald-500',
    amber: 'bg-amber-500',
    rose: 'bg-rose-500',
    slate: 'bg-slate-400',
    brand: 'bg-brand',
  }
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
      <div className={`h-full rounded-full ${fill[tone]}`} style={{ width: `${ratio * 100}%` }} />
    </div>
  )
}
