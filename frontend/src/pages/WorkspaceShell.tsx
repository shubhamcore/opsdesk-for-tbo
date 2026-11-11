import { Outlet, useLocation } from 'react-router-dom'
import { NAV_ITEMS, PageBody, Sidebar, TopBar } from '../components/layout'
import { useSession } from '../lib/store'

const TITLES: Record<string, { title: string; subtitle: string }> = {
  '/w1': {
    title: 'W1 · Ops Queue & SLA Command Center',
    subtitle: 'Live queue, effective SLA countdowns and regional compliance',
  },
  '/w2': {
    title: 'W2 · Unified Ticket & Booking Case Workspace',
    subtitle: 'Three-pane case view — ticket thread, booking context, independent side conversations',
  },
  '/w3': {
    title: 'W3 · Routing & Agent Capacity Studio',
    subtitle: 'Score breakdowns, exclusions and the immutable routing audit trail',
  },
  '/w4': {
    title: 'W4 · Escalation Manager War Room',
    subtitle: 'Escalated and at-risk cases with real ownership handover',
  },
  '/w5': {
    title: 'W5 · Product Intelligence & Governance Hub',
    subtitle: 'Recurring-pattern detection, bug suggestions and streamed exports',
  },
  '/w6': {
    title: 'W6 · OpsDesk Live Simulation Lab',
    subtitle: 'Runs the five seeded journeys end-to-end against the live API',
  },
}

export default function WorkspaceShell() {
  const location = useLocation()
  const { can, user } = useSession()
  const root = '/' + (location.pathname.split('/')[1] ?? 'w1')
  const meta = TITLES[root] ?? TITLES['/w1']
  const item = NAV_ITEMS.find((entry) => entry.to === root)
  const permitted = !item?.capability || can(item.capability)

  return (
    <div className="flex h-full">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col bg-surface">
        <TopBar
          title={meta.title}
          subtitle={
            user
              ? `${meta.subtitle} · signed in as ${user.full_name} (${user.role.replace(/_/g, ' ')})`
              : meta.subtitle
          }
        />
        <PageBody>
          {permitted ? (
            <Outlet />
          ) : (
            <div className="card card-pad" data-testid="permission-denied">
              <h2 className="text-[15px] font-semibold">Not available for your role</h2>
              <p className="mt-1 max-w-xl text-[13px] text-slate-600">
                This workspace requires additional permissions. The API enforces the same rule server-side — switching
                identity from the top-right menu will show the workspace for a role that holds it.
              </p>
            </div>
          )}
        </PageBody>
      </div>
    </div>
  )
}
