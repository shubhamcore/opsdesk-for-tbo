/** Thin fetch wrapper with bearer-token handling and streaming export. */

const TOKEN_KEY = 'opsdesk.token'
const USER_KEY = 'opsdesk.user'

/**
 * Storage that degrades to memory when the browser forbids persistence.
 *
 * OpsDesk is frequently embedded in a sandboxed preview iframe (`allow-scripts`
 * without `allow-same-origin`). In that context merely *touching* `localStorage`
 * throws a SecurityError while the module graph evaluates, which blanks the whole
 * SPA before React can mount. Every read/write therefore goes through this shim:
 * persistence when the browser allows it, an in-memory store when it does not.
 * The trade-off is explicit — inside a sandboxed frame the session lasts for the
 * lifetime of the frame instead of surviving a page reload.
 */
const memoryStore = new Map<string, string>()

function readKey(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return memoryStore.get(key) ?? null
  }
}

function writeKey(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    if (value === null) memoryStore.delete(key)
    else memoryStore.set(key, value)
  }
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, message: string, detail = '') {
    super(message)
    this.status = status
    this.detail = detail
  }
}

export function getToken(): string | null {
  return readKey(TOKEN_KEY)
}

export function setToken(token: string | null) {
  writeKey(TOKEN_KEY, token)
}

export function getStoredUser<T>(): T | null {
  const raw = readKey(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

export function setStoredUser(user: unknown | null) {
  writeKey(USER_KEY, user ? JSON.stringify(user) : null)
}

type Query = Record<string, string | number | boolean | null | undefined>

interface ApiOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
  signal?: AbortSignal
}

function buildUrl(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    params.set(key, String(value))
  })
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

/** JSON request against the same origin (the API is served by the same app). */
export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const token = getToken()
  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? (options.body === undefined ? 'GET' : 'POST'),
    headers: {
      ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  })

  if (!response.ok) {
    const text = await response.text()
    let detail = text
    try {
      const parsed = JSON.parse(text)
      if (typeof parsed.detail === 'string') detail = parsed.detail
      else if (Array.isArray(parsed.detail)) {
        detail = parsed.detail
          .map((item: { loc?: string[]; msg?: string }) =>
            `${item.loc?.slice(1).join('.') ?? 'field'}: ${item.msg ?? 'invalid'}`,
          )
          .join('; ')
      }
    } catch {
      /* keep raw text */
    }
    throw new ApiError(response.status, detail || `Request failed (${response.status})`, text)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export interface ExportRequest {
  file_format: 'CSV' | 'JSONL'
  source: 'DB' | 'SYNTHETIC_BENCHMARK'
  total_rows: number
  region?: string | null
  status?: string | null
  intent?: string | null
  priority?: string | null
}

export interface ExportStreamResult {
  jobUuid: string
  totalRows: number
  filename: string
  bytes: number
  rows: number
}

/**
 * Stream an export and report live progress.
 *
 * Chunks are counted as they arrive so the progress bar reflects bytes that
 * have actually crossed the wire — not a simulated animation.
 */
export async function streamExport(
  payload: ExportRequest,
  onChunk: (bytes: number, rows: number) => void,
): Promise<ExportStreamResult> {
  const token = getToken()
  const response = await fetch('/api/exports/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/csv',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const detail = await response.text()
    throw new ApiError(response.status, detail || 'Export failed', detail)
  }

  const jobUuid = response.headers.get('X-Export-Job-Uuid') ?? ''
  const totalRows = Number(response.headers.get('X-Export-Rows') ?? 0)
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? 'opsdesk_export.csv'

  const reader = response.body?.getReader()
  if (!reader) throw new ApiError(500, 'Streaming is not supported by this browser')

  let bytes = 0
  let rows = 0
  const decoder = new TextDecoder()
  const isCsv = filename.endsWith('.csv')
  let headerSkipped = false

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (!value) continue
    bytes += value.byteLength
    const text = decoder.decode(value, { stream: true })
    const newlines = (text.match(/\n/g) ?? []).length
    if (isCsv && !headerSkipped && newlines > 0) {
      headerSkipped = true
      rows += Math.max(0, newlines - 1)
    } else {
      rows += newlines
    }
    onChunk(bytes, rows)
  }
  return { jobUuid, totalRows, filename, bytes, rows }
}

export function downloadUrl(jobUuid: string): string {
  return `/api/exports/${jobUuid}/download`
}

/**
 * Download a completed export with the bearer token attached.
 *
 * A bare <a href> cannot carry the Authorization header, so the file is fetched
 * with credentials and saved from a blob URL. The bytes come from the file the
 * server wrote during the stream.
 */
export async function downloadExport(jobUuid: string): Promise<{ filename: string; bytes: number }> {
  const token = getToken()
  const response = await fetch(downloadUrl(jobUuid), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new ApiError(response.status, detail || 'Download failed', detail)
  }
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const filename = disposition.match(/filename="?([^";]+)"?/)?.[1] ?? `opsdesk_export_${jobUuid}.csv`
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
  return { filename, bytes: blob.size }
}
