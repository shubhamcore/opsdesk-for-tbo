/** Application chrome: sidebar navigation, top bar, identity switcher. */

import { useEffect, useRef, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  Radio,
  ShieldAlert,
  Ticket,
  Users,
} from 'lucide-react'
import { ROLE_LABELS, useSession } from '../lib/store'
import type { Capability } from '../lib/types'

export interface NavItem {
  to: string
  label: string
  short: string
  icon: typeof LayoutDashboard
  capability?: Capability
  testId: string
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/w1', label: 'Ops Queue & SLA Command Center', short: 'Ops Queue', icon: LayoutDashboard, capability: 'ops', testId: 'nav-w1' },
  { to: '/w2', label: 'Unified Ticket & Booking Case Workspace', short: 'Case Workspace', icon: Ticket, capability: 'ops', testId: 'nav-w2' },
  { to: '/w3', label: 'Routing & Agent Capacity Studio', short: 'Routing Studio', icon: Users, capability: 'route', testId: 'nav-w3' },
  { to: '/w4', label: 'Escalation Manager War Room', short: 'War Room', icon: ShieldAlert, capability: 'ops', testId: 'nav-w4' },
  { to: '/w5', label: 'Product Intelligence & Governance Hub', short: 'Intelligence Hub', icon: BarChart3, capability: 'product_intelligence', testId: 'nav-w5' },
  { to: '/w6', label: 'OpsDesk Live Simulation Lab', short: 'Simulation Lab', icon: Activity, capability: 'simulation', testId: 'nav-w6' },
]

export function Sidebar() {
  const { can, user } = useSession()
  return (
    <aside className="flex w-[228px] shrink-0 flex-col border-r border-line bg-navy text-slate-200">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-[13px] font-bold text-white">
          OD
        </div>
        <div>
          <p className="text-[13px] font-semibold leading-tight text-white">OpsDesk</p>
          <p className="text-[10px] leading-tight text-slate-400">TBO Travel Ops</p>
        </div>
      </div>

      <nav className="mt-1 flex-1 space-y-0.5 px-2" aria-label="Workspaces">
        {NAV_ITEMS.filter((item) => !item.capability || can(item.capability)).map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              title={item.label}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[12.5px] font-medium transition ${
                  isActive ? 'bg-white/10 text-white' : 'text-slate-300 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              <Icon className="h-4 w-4 shrink-0" aria-hidden />
              <span className="truncate">{item.short}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="border-t border-white/10 px-3 py-3 text-[11px] leading-relaxed text-slate-400">
        <p className="flex items-center gap-1.5 font-semibold text-slate-200">
          <Radio className="h-3 w-3 text-emerald-400" aria-hidden />
          {user ? ROLE_LABELS[user.role] : 'Signed out'}
        </p>
        <p className="mt-0.5 truncate">{user?.region ?? 'All regions'}</p>
        <p className="mt-1 text-[10px] text-slate-500">Synthetic dataset — not real TBO records</p>
      </div>
    </aside>
  )
}

export function TopBar({
  title,
  subtitle,
  actions,
}: {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-5 py-3">
      <div className="min-w-0">
        <h1 className="truncate text-[15px] font-semibold text-navy">{title}</h1>
        {subtitle ? <p className="truncate text-[11px] text-slate-500">{subtitle}</p> : null}
      </div>
      <div className="flex items-center gap-2">
        {actions}
        <IdentitySwitcher />
      </div>
    </header>
  )
}

function IdentitySwitcher() {
  const { user, identities, switchIdentity, logout, loading } = useSession()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  async function pick(email: string) {
    if (!user || email === user.email) {
      setOpen(false)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const next = await switchIdentity(email)
      setOpen(false)
      // Land each role on the workspace that proves its capability.
      navigate(next.role === 'ESCALATION_MANAGER' ? '/w4' : next.role === 'OPS_LEAD' ? '/w1' : '/w2')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Switch failed')
    } finally {
      setBusy(false)
    }
  }

  const grouped = identities.reduce<Record<string, typeof identities>>((acc, identity) => {
    acc[identity.role] = acc[identity.role] ?? []
    acc[identity.role].push(identity)
    return acc
  }, {})

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        className="btn-ghost"
        data-testid="role-switcher"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={busy || loading}
      >
        <span className="max-w-[150px] truncate">{user?.full_name ?? 'Sign in'}</span>
        <ChevronDown className="h-3.5 w-3.5" aria-hidden />
      </button>

      {open ? (
        <div className="absolute right-0 z-40 mt-1 w-[290px] overflow-hidden rounded-lg border border-line bg-white shadow-lg">
          <div className="max-h-[320px] overflow-y-auto py-1" role="listbox">
            {Object.entries(grouped).map(([role, people]) => (
              <div key={role} className="pb-1">
                <p className="px-3 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                  {ROLE_LABELS[role as keyof typeof ROLE_LABELS] ?? role}
                </p>
                {people.map((person) => (
                  <button
                    key={person.id}
                    type="button"
                    role="option"
                    aria-selected={person.email === user?.email}
                    data-testid={`identity-${person.email}`}
                    onClick={() => pick(person.email)}
                    className={`flex w-full items-center justify-between px-3 py-1.5 text-left text-[12px] hover:bg-slate-50 ${
                      person.email === user?.email ? 'font-semibold text-brand' : 'text-navy'
                    }`}
                  >
                    <span className="truncate">{person.full_name}</span>
                    <span className="ml-2 shrink-0 text-[10px] text-slate-400">{person.region ?? '—'}</span>
                  </button>
                ))}
              </div>
            ))}
          </div>
          {error ? <p className="border-t border-line px-3 py-2 text-[11px] text-rose-600">{error}</p> : null}
          <button
            type="button"
            onClick={() => {
              logout()
              navigate('/login')
            }}
            className="flex w-full items-center gap-2 border-t border-line px-3 py-2 text-[12px] text-slate-600 hover:bg-slate-50"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden /> Sign out
          </button>
        </div>
      ) : null}
    </div>
  )
}

export function PageBody({ children }: { children: React.ReactNode }) {
  return <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
}
