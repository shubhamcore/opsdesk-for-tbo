/** Formatting helpers — timezone-aware, locale-stable. */

export const CHART_COLORS = [
  '#2563EB',
  '#0EA5E9',
  '#10B981',
  '#F59E0B',
  '#EF4444',
  '#8B5CF6',
  '#14B8A6',
  '#64748B',
]

export function fmtDateTime(value?: string | null, timeZone?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: timeZone ?? undefined,
      hour12: false,
    }).format(date)
  } catch {
    return date.toISOString().slice(0, 16).replace('T', ' ')
  }
}

export function fmtDate(value?: string | null, timeZone?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  try {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      timeZone: timeZone ?? undefined,
    }).format(date)
  } catch {
    return date.toISOString().slice(0, 10)
  }
}

/** Countdown string from a number of seconds (negative = overdue). */
export function fmtCountdown(seconds: number): string {
  const overdue = seconds < 0
  const abs = Math.abs(Math.round(seconds))
  const days = Math.floor(abs / 86400)
  const hours = Math.floor((abs % 86400) / 3600)
  const minutes = Math.floor((abs % 3600) / 60)
  const secs = abs % 60
  let core: string
  if (days > 0) core = `${days}d ${String(hours).padStart(2, '0')}h`
  else if (hours > 0) core = `${hours}h ${String(minutes).padStart(2, '0')}m`
  else if (minutes > 0) core = `${minutes}m ${String(secs).padStart(2, '0')}s`
  else core = `${secs}s`
  return overdue ? `${core} late` : core
}

export function fmtMoney(amount?: number | null, currency = 'USD'): string {
  if (amount === null || amount === undefined) return '—'
  try {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: currency || 'USD',
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${currency} ${amount.toLocaleString('en-GB')}`
  }
}

export function fmtNumber(value?: number | null): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 2 }).format(value)
}

export function fmtBytes(bytes?: number | null): string {
  if (!bytes) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 100 || index === 0 ? 0 : 2)} ${units[index]}`
}

/** REFUND_DELAY → "Refund Delay", INVENTORY_RATE_SYNC_BUG → "Inventory Rate Sync Bug". */
export function humanise(value?: string | null): string {
  if (!value) return '—'
  return value
    .toLowerCase()
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export type Tone = 'green' | 'amber' | 'rose' | 'slate' | 'brand'

export function slaTone(state: string): Tone {
  if (state === 'HEALTHY') return 'green'
  if (state === 'AT_RISK') return 'amber'
  if (state === 'BREACHED') return 'rose'
  if (state === 'RESOLVED') return 'slate'
  return 'slate'
}

export function priorityTone(priority: string): Tone {
  if (priority === 'CRITICAL') return 'rose'
  if (priority === 'HIGH') return 'amber'
  if (priority === 'MEDIUM') return 'brand'
  return 'slate'
}

export function pct(value?: number | null, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}
