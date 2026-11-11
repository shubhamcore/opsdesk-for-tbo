import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowRight, KeyRound, Loader2, ShieldCheck, Ticket, Users } from 'lucide-react'
import { api } from '../lib/api'
import { ROLE_LABELS, useSession } from '../lib/store'
import type { Agency, Role, User } from '../lib/types'

interface IdentityLite {
  email: string
  full_name: string
  role: Role
  region: string | null
  agency_code: string | null
}

const DEMO_TARGET: Partial<Record<Role, string>> = {
  OPS_LEAD: '/w1',
  ESCALATION_MANAGER: '/w4',
  OPS_AGENT: '/w3',
  AGENCY_REQUESTER: '/w2',
}

export default function Login() {
  const { token, login, switchIdentity } = useSession()
  const navigate = useNavigate()
  const [email, setEmail] = useState('nisha.verma@tbo.com')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [identities, setIdentities] = useState<IdentityLite[]>([])
  const [agencies, setAgencies] = useState<Agency[]>([])
  const [hint, setHint] = useState('')

  useEffect(() => {
    api<{ identities: IdentityLite[]; agencies: Agency[]; demo_password_hint: string }>('/api/auth/identities')
      .then((payload) => {
        setIdentities(payload.identities)
        setAgencies(payload.agencies)
        setHint(payload.demo_password_hint)
      })
      .catch(() => setError('Cannot reach the OpsDesk API. Is the backend running on port 8000?'))
  }, [])

  if (token) return <Navigate to="/w1" replace />

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy('form')
    try {
      const user = await login(email.trim(), password)
      navigate(DEMO_TARGET[user.role] ?? '/w1', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(null)
    }
  }

  async function demoSignIn(identity: IdentityLite) {
    setError(null)
    setBusy(identity.email)
    try {
      const user = await switchIdentity(identity.email)
      navigate(DEMO_TARGET[user.role] ?? '/w1', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      {/* Narrative panel */}
      <aside className="flex w-full flex-col justify-between bg-navy px-8 py-10 text-slate-200 lg:w-[44%]">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-[13px] font-bold text-white">
              OD
            </div>
            <div>
              <p className="text-[14px] font-semibold text-white">OpsDesk</p>
              <p className="text-[11px] text-slate-400">TBO Travel Operations Platform</p>
            </div>
          </div>

          <h1 className="mt-10 text-[26px] font-semibold leading-tight text-white">
            A booking is the operational context.
            <br />
            <span className="text-brand-400">A ticket is only one interaction</span> associated with that booking.
          </h1>

          <ul className="mt-8 space-y-3 text-[13px] text-slate-300">
            <li className="flex gap-2">
              <Ticket className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" aria-hidden />
              Eight canonical intents, an ML classifier trained on synthetic in-house data, and a booking-first case graph.
            </li>
            <li className="flex gap-2">
              <Users className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" aria-hidden />
              Transparent routing out of 100 points — region, shift, skill and live capacity, with a full audit trail.
            </li>
            <li className="flex gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" aria-hidden />
              Effective SLA = MIN(priority deadline, LCD − 2h, check-in − 4h), with holiday-aware at-risk thresholds.
            </li>
          </ul>
        </div>

        <p className="mt-10 text-[11px] leading-relaxed text-slate-500">
          All agencies, bookings, tickets and passengers in this environment are <strong>synthetic</strong> and generated
          for demonstration. No real TBO customer data is present.
        </p>
      </aside>

      {/* Sign-in panel */}
      <main className="flex w-full flex-1 items-center justify-center bg-surface px-6 py-10">
        <div className="w-full max-w-[560px]">
          <div className="card card-pad">
            <h2 className="text-[16px] font-semibold">Sign in to the operations console</h2>
            <p className="mt-0.5 text-[12px] text-slate-500">
              Use a seeded identity, or type the documented demo password.
            </p>

            <form className="mt-4 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end" onSubmit={submit}>
              <label className="block">
                <span className="label">Work email</span>
                <input
                  className="input"
                  type="email"
                  required
                  value={email}
                  data-testid="login-email"
                  onChange={(event) => setEmail(event.target.value)}
                  autoComplete="username"
                />
              </label>
              <label className="block">
                <span className="label">Password</span>
                <input
                  className="input"
                  type="password"
                  required
                  minLength={8}
                  value={password}
                  placeholder={hint || 'Demo password'}
                  data-testid="login-password"
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                />
              </label>
              <button className="btn-primary sm:col-span-2" type="submit" disabled={busy === 'form'} data-testid="login-submit">
                {busy === 'form' ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <KeyRound className="h-4 w-4" aria-hidden />}
                Sign in
              </button>
            </form>

            {error ? (
              <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-700" role="alert">
                {error}
              </p>
            ) : null}

            {hint ? (
              <p className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-[11px] text-blue-800">
                Demo environment — {hint}. One-click demo sign-in below skips the form.
              </p>
            ) : null}
          </div>

          <div className="card mt-4 overflow-hidden">
            <header className="flex items-center justify-between border-b border-line px-4 py-2.5">
              <h3 className="section-title">Seeded identities</h3>
              <span className="text-[11px] text-slate-400">{identities.length} accounts · {agencies.length} agencies</span>
            </header>
            <div className="max-h-[300px] divide-y divide-line overflow-y-auto">
              {identities.map((identity) => (
                <button
                  key={identity.email}
                  type="button"
                  onClick={() => demoSignIn(identity)}
                  disabled={busy !== null}
                  data-testid={`demo-login-${identity.role}`}
                  className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left hover:bg-slate-50 disabled:opacity-50"
                >
                  <div className="min-w-0">
                    <p className="truncate text-[13px] font-medium text-navy">{identity.full_name}</p>
                    <p className="truncate text-[11px] text-slate-500">{identity.email}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="chip border border-slate-200 bg-slate-100 text-slate-600">
                      {ROLE_LABELS[identity.role] ?? identity.role}
                    </span>
                    <span className="w-10 text-right text-[11px] text-slate-400">{identity.region ?? '—'}</span>
                    {busy === identity.email ? (
                      <Loader2 className="h-4 w-4 animate-spin text-brand" aria-hidden />
                    ) : (
                      <ArrowRight className="h-4 w-4 text-slate-300" aria-hidden />
                    )}
                  </div>
                </button>
              ))}
              {identities.length === 0 ? (
                <p className="px-4 py-6 text-center text-[12px] text-slate-400">Loading identities…</p>
              ) : null}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
