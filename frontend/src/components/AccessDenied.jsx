import { useState } from 'react'
import { useAuth } from '../features/auth/AuthContext.jsx'

export default function AccessDenied() {
  const { signOut } = useAuth()
  const [error, setError] = useState('')
  const [signingOut, setSigningOut] = useState(false)

  async function handleSignOut() {
    setError('')
    setSigningOut(true)
    try {
      await signOut()
    } catch (signOutError) {
      setError(signOutError.message)
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <main className="pos-shell">
      <section className="pos-notice" role="alert">
        <p className="eyebrow">Account permissions</p>
        <h1>Access is not configured</h1>
        <p>
          Your account does not have a recognized shop role. Ask an administrator
          to assign the appropriate role, then sign in again.
        </p>
        {error && <p role="alert">{error}</p>}
        <button disabled={signingOut} onClick={handleSignOut} type="button">
          {signingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </section>
    </main>
  )
}
