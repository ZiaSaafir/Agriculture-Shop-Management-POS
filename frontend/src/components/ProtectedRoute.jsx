import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../features/auth/AuthContext.jsx'
import { capabilityForPath, hasAccess, homeForRoles } from '../auth/roleAccess.js'
import AccessDenied from './AccessDenied.jsx'

export default function ProtectedRoute() {
  const { user, loading, initializationError } = useAuth()
  const location = useLocation()

  if (loading) {
    return <p role="status">Checking your session…</p>
  }

  if (initializationError) {
    return <p role="alert">{initializationError}</p>
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  const capability = capabilityForPath(location.pathname)
  if (capability && !hasAccess(user.roles, capability)) {
    const home = homeForRoles(user.roles)
    return home ? <Navigate to={home} replace /> : <AccessDenied />
  }

  return <Outlet />
}
