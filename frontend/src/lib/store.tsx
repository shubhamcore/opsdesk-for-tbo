/** Session + capability store. Backend RBAC stays authoritative; this only gates UI. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { api, getStoredUser, getToken, setStoredUser, setToken } from './api'
import type { Agency, Capability, Role, User } from './types'

export const ROLE_CAPABILITIES: Record<Role, Capability[]> = {
  AGENCY_REQUESTER: ['ops', 'side_conversations'],
  // Mirrors backend/security.py + router guards: agents do not hold analytics,
  // export or simulation permissions.
  OPS_AGENT: ['ops', 'route', 'agents', 'side_conversations', 'internal_notes', 'escalate'],
  ESCALATION_MANAGER: [
    'ops',
    'route',
    'agents',
    'side_conversations',
    'internal_notes',
    'product_intelligence',
    'exports',
    'simulation',
  ],
  OPS_LEAD: [
    'ops',
    'route',
    'agents',
    'side_conversations',
    'internal_notes',
    'escalate',
    'product_intelligence',
    'exports',
    'simulation',
    'override_assignment',
  ],
}

export const ROLE_LABELS: Record<Role, string> = {
  AGENCY_REQUESTER: 'Agency Requester',
  OPS_AGENT: 'Ops Agent',
  ESCALATION_MANAGER: 'Escalation Manager',
  OPS_LEAD: 'Ops Lead',
}

interface AuthResponse {
  access_token: string
  token_type: string
  user: User
}

interface IdentityListResponse {
  identities: User[]
  agencies: Agency[]
  demo_password_hint: string
}

interface SessionValue {
  user: User | null
  token: string | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<User>
  logout: () => void
  can: (capability: Capability) => boolean
  identities: User[]
  demoHint: string
  switchIdentity: (email: string) => Promise<User>
}

const SessionContext = createContext<SessionValue | null>(null)

export function useSession(): SessionValue {
  const value = useContext(SessionContext)
  if (!value) throw new Error('useSession must be used inside <SessionProvider>')
  return value
}

export function useCan(capability: Capability): boolean {
  const { can } = useSession()
  return can(capability)
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => getStoredUser<User>())
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [identities, setIdentities] = useState<User[]>([])
  const [demoHint, setDemoHint] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const clear = useCallback(() => {
    setToken(null)
    setStoredUser(null)
    setTokenState(null)
    setUser(null)
    setIdentities([])
  }, [])

  // Revalidate a persisted session against the API so a stale token never
  // leaves the shell in a half-authenticated state.
  useEffect(() => {
    if (!token) return
    let cancelled = false
    api<{ user: User; agency: Agency | null }>('/api/auth/me')
      .then((payload) => {
        if (cancelled) return
        setUser(payload.user)
        setStoredUser(payload.user)
      })
      .catch(() => {
        if (!cancelled) clear()
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  // Demo identity switcher (read-only list, no secrets exposed).
  useEffect(() => {
    if (!token) return
    let cancelled = false
    api<IdentityListResponse>('/api/auth/identities')
      .then((payload) => {
        if (cancelled) return
        setIdentities(payload.identities)
        setDemoHint(payload.demo_password_hint)
      })
      .catch(() => {
        if (!cancelled) setIdentities([])
      })
    return () => {
      cancelled = true
    }
  }, [token])

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await api<AuthResponse>('/api/auth/login', {
        method: 'POST',
        body: { email, password },
      })
      setToken(data.access_token)
      setStoredUser(data.user)
      setTokenState(data.access_token)
      setUser(data.user)
      return data.user
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const switchIdentity = useCallback(async (email: string) => {
    setLoading(true)
    setError(null)
    try {
      // Demo identity switching goes through the server-side demo-login route,
      // which is disabled outside demo deployments (OPSDESK_ENABLE_ROLE_SWITCH).
      const data = await api<AuthResponse>('/api/auth/demo-login', {
        method: 'POST',
        body: { email },
      })
      setToken(data.access_token)
      setStoredUser(data.user)
      setTokenState(data.access_token)
      setUser(data.user)
      return data.user
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Could not switch identity'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const can = useCallback(
    (capability: Capability) => {
      if (!user) return false
      return ROLE_CAPABILITIES[user.role]?.includes(capability) ?? false
    },
    [user],
  )

  const value = useMemo<SessionValue>(
    () => ({
      user,
      token,
      loading,
      error,
      login,
      logout: clear,
      can,
      identities,
      demoHint,
      switchIdentity,
    }),
    [user, token, loading, error, login, clear, can, identities, demoHint, switchIdentity],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

/** Small polling helper so SLA countdowns tick without a websocket layer. */
export function useTicker(intervalMs = 1000): number {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = window.setInterval(() => setTick((value) => value + 1), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return tick
}
