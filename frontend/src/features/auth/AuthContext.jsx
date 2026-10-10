import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  ApiError,
  initializeSession,
  login as loginRequest,
  logout as logoutRequest,
} from '../../services/authApi.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [initializationError, setInitializationError] = useState('')

  useEffect(() => {
    let active = true

    initializeSession()
      .then((currentUser) => {
        if (active) setUser(currentUser)
      })
      .catch((error) => {
        if (active && !(error instanceof ApiError && error.status === 401)) {
          setInitializationError(error.message)
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [])

  const signIn = useCallback(async (credentials) => {
    const authenticatedUser = await loginRequest(credentials)
    setUser(authenticatedUser)
    setInitializationError('')
    return authenticatedUser
  }, [])

  const signOut = useCallback(async () => {
    await logoutRequest()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      initializationError,
      signIn,
      signOut,
    }),
    [user, loading, initializationError, signIn, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider.')
  }
  return context
}
