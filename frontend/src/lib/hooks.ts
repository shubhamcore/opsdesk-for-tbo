/** Small data-fetching helpers shared by the workspaces. */

import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

export interface FetchState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
  setData: (value: T | null) => void
}

/**
 * GET a path and re-fetch when it changes.
 *
 * Keeps the previous payload visible while refreshing so filters do not flash
 * an empty table. `pollMs` re-fetches quietly in the background.
 */
export function useFetch<T>(path: string | null, pollMs?: number): FetchState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(Boolean(path))
  const [nonce, setNonce] = useState(0)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    if (!path) {
      setData(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    api<T>(path)
      .then((payload) => {
        if (cancelled || !alive.current) return
        setData(payload)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled || !alive.current) return
        setError(err instanceof Error ? err.message : 'Request failed')
      })
      .finally(() => {
        if (!cancelled && alive.current) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [path, nonce])

  useEffect(() => {
    if (!pollMs || !path) return
    const id = window.setInterval(() => setNonce((value) => value + 1), pollMs)
    return () => window.clearInterval(id)
  }, [pollMs, path])

  const reload = useCallback(() => setNonce((value) => value + 1), [])

  return { data, error, loading, reload, setData }
}

/** Debounce a fast-changing value (search boxes). */
export function useDebounced<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(id)
  }, [value, delayMs])
  return debounced
}

/** Clipboard helper that fails loudly instead of silently. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
