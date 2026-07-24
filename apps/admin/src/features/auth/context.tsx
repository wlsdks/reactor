import { createContext, useContext, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'
import { useToastStore } from '../../shared/store/toast.store'
import type { User, UserRole, AuthResponse } from './types'
import { ApiError, NetworkError } from '../../shared/api/errors'
import * as authApi from './api'
import { IAM_ENABLED } from './api'
import { getAuthToken, setAuthToken, removeAuthToken, setOnUnauthorized } from '../../shared/api/client'
import { clearStoredUser, readStoredUser, writeStoredUser } from './storage'
import { setLogoutReason } from './logoutReason'
import { useSessionExpiry } from './useSessionExpiry'
import { userFromToken } from '../../shared/lib/jwt'
import { setSentryUser, clearSentryUser } from '../../shared/lib/sentry'

interface AuthContextValue {
  user: User | null
  isAuthenticated: boolean
  isAdmin: boolean
  isAuthRequired: boolean
  isLoading: boolean
  error: string | null
  concurrentSession: boolean
  login: (email: string, password: string) => Promise<boolean>
  loginAsDemo: () => Promise<boolean>
  logout: () => Promise<void>
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

interface AuthProviderProps {
  children: ReactNode
}

const AUTH_REQUIRED = true

class ExchangeFailedError extends Error {
  constructor() {
    super('Token exchange failed')
    this.name = 'ExchangeFailedError'
  }
}

async function attemptLogin(
  email: string,
  password: string,
): Promise<{ token: string; user: User } | null> {
  if (IAM_ENABLED) {
    // Step 1: Login to reactor-iam → RS256 JWT (transient, not stored)
    const iamResponse = await authApi.iamLogin({ email, password })
    if (!iamResponse.accessToken) return null

    // Step 2: Exchange IAM token for reactor HS256 JWT
    let exchangeResponse: AuthResponse
    try {
      exchangeResponse = await authApi.exchangeToken(iamResponse.accessToken)
    } catch {
      throw new ExchangeFailedError()
    }
    if (!exchangeResponse.token || !exchangeResponse.user) return null
    return { token: exchangeResponse.token, user: exchangeResponse.user }
  }

  // Fallback: direct reactor login (IAM not configured)
  const response = await authApi.directLogin({ email, password })
  if (!response.token || !response.user) return null
  return { token: response.token, user: response.user }
}

function isAdminRole(role: UserRole | undefined): boolean {
  return role === 'ADMIN' || role === 'ADMIN_MANAGER' || role === 'ADMIN_DEVELOPER'
}

function loginFailureMessage(
  t: (key: string) => string,
  error: unknown,
): string {
  if (
    error instanceof NetworkError
    || (error instanceof ApiError && error.status >= 500)
  ) {
    return t('auth.loginUnavailable')
  }

  if (error instanceof ApiError && [400, 401, 403, 422].includes(error.status)) {
    return t('auth.loginFailed')
  }

  return t('auth.serverError')
}

export function AuthProvider({ children }: AuthProviderProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [concurrentSession, setConcurrentSession] = useState(false)

  useEffect(() => {
    let cancelled = false

    function init() {
      try {
        const token = getAuthToken()
        if (!token) return
        const cachedUser = readStoredUser()
        if (cachedUser && isAdminRole(cachedUser.role)) {
          if (!cancelled) {
            setUser(cachedUser)
            setSentryUser({ id: cachedUser.id, role: cachedUser.role })
          }
          return
        }
        const isLoginRoute = window.location.pathname === '/login'
        if (isLoginRoute) return
        // Restore user from JWT claims (no /auth/me endpoint)
        const parsed = userFromToken(token)
        if (!cancelled) {
          if (parsed && isAdminRole(parsed.role)) {
            writeStoredUser(parsed)
            setUser(parsed)
            setSentryUser({ id: parsed.id, role: parsed.role })
          } else {
            removeAuthToken()
            clearStoredUser()
          }
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    init()
    return () => { cancelled = true }
  }, [])

  const login = async (email: string, password: string): Promise<boolean> => {
    setError(null)
    setConcurrentSession(false)
    setIsLoading(true)
    try {
      const loginResult = await attemptLogin(email, password)
      if (!loginResult) {
        setError(t('auth.loginFailed'))
        return false
      }

      const { token: authToken, user: authenticatedUser } = loginResult

      // Enforce admin-only access
      if (!isAdminRole(authenticatedUser.role)) {
        setError(t('auth.adminOnly'))
        return false
      }
      setAuthToken(authToken)
      writeStoredUser(authenticatedUser)
      setUser(authenticatedUser)
      setSentryUser({ id: authenticatedUser.id, role: authenticatedUser.role })
      return true
    } catch (e) {
      if (e instanceof ExchangeFailedError) {
        setError(t('auth.exchangeFailed'))
        return false
      }
      if (e instanceof ApiError && e.status === 409) {
        setConcurrentSession(true)
        setError(t('auth.concurrentSession'))
        return false
      }
      setError(loginFailureMessage(t, e))
      return false
    } finally {
      setIsLoading(false)
    }
  }

  const loginAsDemo = async (): Promise<boolean> => {
    if (IAM_ENABLED) {
      // When IAM is active, demo login uses the IAM flow with default admin credentials
      return login('admin@example.com', 'admin1234')
    }
    // Fallback: reactor native demo login endpoint
    setError(null)
    setConcurrentSession(false)
    setIsLoading(true)
    try {
      const response = await authApi.demoLogin()
      if (!response.token || !response.user) {
        setError(t('auth.loginFailed'))
        return false
      }
      if (!isAdminRole(response.user.role)) {
        setError(t('auth.adminOnly'))
        return false
      }
      setAuthToken(response.token)
      writeStoredUser(response.user)
      setUser(response.user)
      setSentryUser({ id: response.user.id, role: response.user.role })
      return true
    } catch (e) {
      setError(loginFailureMessage(t, e))
      return false
    } finally {
      setIsLoading(false)
    }
  }

  const clearSession = () => {
    removeAuthToken()
    clearStoredUser()
    queryClient.clear()
    setUser(null)
    setError(null)
    clearSentryUser()
  }

  const logout = async () => {
    try {
      if (getAuthToken()) {
        await authApi.logout()
      }
    } catch {
      // Local session must still be cleared even if revoke API fails.
    } finally {
      clearSession()
    }
  }

  const handleUnauthorized = () => {
    // Surface both the in-app toast (immediate feedback) and the login-page
    // banner (post-redirect context). Belt-and-braces — if the user was on a
    // page when 401 fired, the toast tells them; once they land back on
    // /login, the banner explains why.
    useToastStore.getState().addToast({ type: 'warning', message: t('auth.sessionExpired') })
    setLogoutReason('session-expired')
    clearSession()
  }

  useEffect(() => {
    setOnUnauthorized(handleUnauthorized)
    return () => setOnUnauthorized(null)
  }, [handleUnauthorized])

  // Cross-tab sync: detect token removal or change in another tab
  useEffect(() => {
    function handleStorageChange(e: StorageEvent) {
      if (e.key === 'reactor-admin-token') {
        if (e.newValue === null) {
          // Token removed in another tab — flag the reason so the login page
          // can show a friendly banner instead of bouncing silently.
          setLogoutReason('cross-tab')
          clearSession()
        } else if (e.newValue !== e.oldValue) {
          // Different token = different user logged in on another tab.
          // Same banner reason — from the *current* tab's perspective the
          // session was invalidated by another tab's activity.
          setLogoutReason('cross-tab')
          clearSession()
          window.location.reload()
        }
      }
    }
    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  useSessionExpiry(user)

  const clearError = () => setError(null)

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isAdmin: isAdminRole(user?.role),
        isAuthRequired: AUTH_REQUIRED,
        isLoading,
        error,
        concurrentSession,
        login,
        loginAsDemo,
        logout,
        clearError,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
