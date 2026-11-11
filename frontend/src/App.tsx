import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactElement } from 'react'
import { useSession } from './lib/store'
import Login from './pages/Login'
import WorkspaceShell from './pages/WorkspaceShell'
import W1OpsQueue from './workspaces/W1OpsQueue'
import W2CaseWorkspace from './workspaces/W2CaseWorkspace'
import W3RoutingStudio from './workspaces/W3RoutingStudio'
import W4WarRoom from './workspaces/W4WarRoom'
import W5IntelligenceHub from './workspaces/W5IntelligenceHub'
import W6SimulationLab from './workspaces/W6SimulationLab'

function RequireAuth({ children }: { children: ReactElement }) {
  const { token } = useSession()
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <WorkspaceShell />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/w1" replace />} />
        <Route path="w1" element={<W1OpsQueue />} />
        <Route path="w2" element={<W2CaseWorkspace />} />
        <Route path="w2/:ticketId" element={<W2CaseWorkspace />} />
        <Route path="w3" element={<W3RoutingStudio />} />
        <Route path="w4" element={<W4WarRoom />} />
        <Route path="w5" element={<W5IntelligenceHub />} />
        <Route path="w6" element={<W6SimulationLab />} />
      </Route>
      <Route path="*" element={<Navigate to="/w1" replace />} />
    </Routes>
  )
}
