import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './AuthContext.jsx'
import AccessDenied from '../../components/AccessDenied.jsx'
import { homeForRoles } from '../../auth/roleAccess.js'

export default function LoginPage() {
  const { user, loading, signIn } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (loading) return <p role="status">Checking your session…</p>
  if (user) {
    const home = homeForRoles(user.roles)
    return home ? <Navigate to={home} replace /> : <AccessDenied />
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)

    try {
      const authenticatedUser = await signIn({ username, password })
      navigate(
        location.state?.from?.pathname ?? homeForRoles(authenticatedUser.roles) ?? '/',
        { replace: true },
      )
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-card">
      <p className="eyebrow">Agriculture shop management</p>
      <h1>Sign in</h1>
      <form onSubmit={handleSubmit}>
        <label>
          Username
          <input
            autoComplete="username"
            name="username"
            onChange={(event) => setUsername(event.target.value)}
            required
            value={username}
          />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            name="password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error && <p role="alert">{error}</p>}
        <button disabled={submitting} type="submit">
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
