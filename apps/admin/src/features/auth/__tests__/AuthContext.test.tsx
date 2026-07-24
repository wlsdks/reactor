import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '../../../test/utils'
import { AuthProvider, useAuth } from '../context'
import { removeAuthToken, setAuthToken } from '../../../shared/api/client'
import { ApiError, NetworkError } from '../../../shared/api/errors'
import { readLogoutReason, clearLogoutReason } from '../logoutReason'

vi.mock('../api', () => ({
  directLogin: vi.fn(),
  iamLogin: vi.fn(),
  exchangeToken: vi.fn(),
  iamLogout: vi.fn(),
  IAM_ENABLED: false,
  logout: vi.fn(),
  register: vi.fn(),
  changePassword: vi.fn(),
}))

import * as authApi from '../api'
const directLoginMock = vi.mocked(authApi.directLogin)
const logoutMock = vi.mocked(authApi.logout)

/** Build a fake JWT that userFromToken() can parse. */
function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', kid: 'test' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-sig`
}

const adminJwtPayload = {
  sub: 'user-1',
  roles: ['ROLE_USER', 'ROLE_ADMIN'],
  permissions: ['READ_PROFILE', 'MANAGE_USERS'],
  iss: 'reactor-iam',
  exp: 9999999999,
  iat: 1700000000,
  jti: 'test-jti',
}

const userJwtPayload = {
  sub: 'user-2',
  roles: ['ROLE_USER'],
  permissions: ['READ_PROFILE'],
  iss: 'reactor-iam',
  exp: 9999999999,
  iat: 1700000000,
  jti: 'test-jti-2',
}

const adminToken = fakeJwt(adminJwtPayload)
const userToken = fakeJwt(userJwtPayload)

// Simple consumer component
function AuthStatus() {
  const { isAuthenticated, isLoading, user, error } = useAuth()
  if (isLoading) return <div>loading...</div>
  if (error) return <div data-testid="error">{error}</div>
  if (isAuthenticated) {
    return <div data-testid="user">{user?.id}</div>
  }
  return <div data-testid="unauthenticated">not authenticated</div>
}

function LoginButton() {
  const { login, isLoading } = useAuth()
  return (
    <button
      onClick={() => login('admin@example.com', 'password')}
      disabled={isLoading}
    >
      Login
    </button>
  )
}

function LogoutButton() {
  const { logout } = useAuth()
  return <button onClick={logout}>Logout</button>
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    removeAuthToken()
    localStorage.clear()
    clearLogoutReason()
    window.history.pushState({}, '', '/')
    directLoginMock.mockResolvedValue({
      token: adminToken,
      user: { id: 'user-1', email: 'admin@example.com', name: 'admin', role: 'ADMIN' },
      error: null,
    })
    logoutMock.mockResolvedValue(undefined)
  })

  it('resolves loading state (not stuck loading)', async () => {
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.queryByText('loading...')).not.toBeInTheDocument()
    })
  })

  it('shows unauthenticated when no token', async () => {
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
  })

  it('auto-authenticates when valid token exists in localStorage', async () => {
    setAuthToken(adminToken)
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('user')).toBeInTheDocument()
      expect(screen.getByTestId('user').textContent).toBe('user-1')
    })
  })

  it('clears token and shows unauthenticated when token is unparseable', async () => {
    setAuthToken('garbage-token')
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
  })

  it('skips init on login route and shows unauthenticated', async () => {
    window.history.pushState({}, '', '/login')
    setAuthToken(adminToken)
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
  })

  it('logs in successfully and shows user', async () => {
    render(
      <AuthProvider>
        <AuthStatus />
        <LoginButton />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('user')).toBeInTheDocument()
    })
  })

  it('logs out and clears user', async () => {
    setAuthToken(adminToken)
    render(
      <AuthProvider>
        <AuthStatus />
        <LogoutButton />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('user')).toBeInTheDocument())

    await act(async () => {
      screen.getByText('Logout').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
  })

  it('shows error on login failure (wrong password)', async () => {
    directLoginMock.mockRejectedValueOnce(new Error('Invalid credentials'))

    function ErrorDisplay() {
      const { login, error } = useAuth()
      return (
        <>
          <button onClick={() => login('bad@example.com', 'wrong')}>Login</button>
          {error && <div data-testid="error">{error}</div>}
        </>
      )
    }

    render(
      <AuthProvider>
        <ErrorDisplay />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('error')).toBeInTheDocument()
    })
  })

  it('explains when the administrator login connection is unavailable', async () => {
    directLoginMock.mockRejectedValueOnce(
      ApiError.fromResponse(503, { detail: 'JWT authentication is not configured' }),
    )

    function ErrorDisplay() {
      const { login, error } = useAuth()
      return (
        <>
          <button onClick={() => login('admin@example.com', 'password')}>Login</button>
          {error && <div data-testid="error">{error}</div>}
        </>
      )
    }

    render(
      <AuthProvider>
        <ErrorDisplay />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Login connection unavailable')
    })
  })

  it('explains when the login server cannot be reached', async () => {
    directLoginMock.mockRejectedValueOnce(new NetworkError())

    function ErrorDisplay() {
      const { login, error } = useAuth()
      return (
        <>
          <button onClick={() => login('admin@example.com', 'password')}>Login</button>
          {error && <div data-testid="error">{error}</div>}
        </>
      )
    }

    render(
      <AuthProvider>
        <ErrorDisplay />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Login connection unavailable')
    })
  })

  it('shows error when directLogin returns no token', async () => {
    directLoginMock.mockResolvedValueOnce({
      token: null as unknown as string,
      user: null as unknown as import('../types').User,
      error: null,
    })

    function ErrorDisplay() {
      const { login, error } = useAuth()
      return (
        <>
          <button onClick={() => login('locked@example.com', 'password')}>Login</button>
          {error && <div data-testid="error">{error}</div>}
        </>
      )
    }

    render(
      <AuthProvider>
        <ErrorDisplay />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Login failed')
    })
  })

  it('rejects login for non-admin role', async () => {
    directLoginMock.mockResolvedValueOnce({
      token: userToken,
      user: { id: 'user-2', email: 'user@example.com', name: 'user', role: 'USER' },
      error: null,
    })

    function ErrorDisplay() {
      const { login, error } = useAuth()
      return (
        <>
          <button onClick={() => login('user@example.com', 'password')}>Login</button>
          {error && <div data-testid="error">{error}</div>}
        </>
      )
    }

    render(
      <AuthProvider>
        <ErrorDisplay />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('Admin only')
    })
  })

  it('clears error with clearError', async () => {
    directLoginMock.mockRejectedValueOnce(new Error('fail'))

    function ErrorDisplay() {
      const { login, error, clearError } = useAuth()
      return (
        <>
          <button onClick={() => login('bad@example.com', 'wrong')}>Login</button>
          <button onClick={clearError}>Clear</button>
          {error && <div data-testid="error">{error}</div>}
        </>
      )
    }

    render(
      <AuthProvider>
        <ErrorDisplay />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.queryByText('loading...')).not.toBeInTheDocument())

    await act(async () => {
      screen.getByText('Login').click()
    })
    await waitFor(() => expect(screen.getByTestId('error')).toBeInTheDocument())

    await act(async () => {
      screen.getByText('Clear').click()
    })
    expect(screen.queryByTestId('error')).not.toBeInTheDocument()
  })

  it('cross-tab sync: clears session when token is removed in another tab', async () => {
    setAuthToken(adminToken)
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('user')).toBeInTheDocument())

    // Simulate another tab removing the token
    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'reactor-admin-token',
          newValue: null,
        }),
      )
    })

    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
    // The logout reason flag must be set so the login banner can explain the
    // bounce — this is the BX fix for the silent-redirect blind spot.
    expect(readLogoutReason()).toBe('cross-tab')
  })

  it('cross-tab sync: ignores storage events for other keys', async () => {
    setAuthToken(adminToken)
    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('user')).toBeInTheDocument())

    // Dispatch a storage event for a different key
    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'some-other-key',
          newValue: null,
        }),
      )
    })

    // User should still be authenticated
    expect(screen.getByTestId('user')).toBeInTheDocument()
  })

  it('cross-tab sync: clears session and reloads when a different token is set in another tab', async () => {
    setAuthToken(adminToken)
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadMock },
      writable: true,
      configurable: true,
    })

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('user')).toBeInTheDocument())

    // Dispatch a storage event where a different token is set (different admin logged in)
    await act(async () => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: 'reactor-admin-token',
          oldValue: adminToken,
          newValue: 'different-token',
        }),
      )
    })

    // Session should be cleared
    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
    // Page should reload for the new session
    expect(reloadMock).toHaveBeenCalled()
    // Reason flag is also set when a different token replaces ours — the
    // banner gives the user a coherent explanation post-reload.
    expect(readLogoutReason()).toBe('cross-tab')
  })

  it('logout clears session even if API call fails', async () => {
    setAuthToken(adminToken)
    logoutMock.mockRejectedValueOnce(new Error('Network error'))

    render(
      <AuthProvider>
        <AuthStatus />
        <LogoutButton />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('user')).toBeInTheDocument())

    await act(async () => {
      screen.getByText('Logout').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
  })

  it('logout skips API call when no token exists', async () => {
    setAuthToken(adminToken)
    render(
      <AuthProvider>
        <AuthStatus />
        <LogoutButton />
      </AuthProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('user')).toBeInTheDocument())

    // Remove token before clicking logout
    removeAuthToken()

    await act(async () => {
      screen.getByText('Logout').click()
    })

    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
    // logout API should not have been called since token was removed
    expect(logoutMock).not.toHaveBeenCalled()
  })

  it('init: rejects non-admin user from JWT', async () => {
    setAuthToken(userToken)

    render(
      <AuthProvider>
        <AuthStatus />
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('unauthenticated')).toBeInTheDocument()
    })
  })

  it('throws when useAuth is called outside AuthProvider', () => {
    // Suppress console.error for the expected error
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    function Orphan() {
      useAuth()
      return null
    }

    expect(() => {
      render(<Orphan />)
    }).toThrow('useAuth must be used within AuthProvider')

    consoleSpy.mockRestore()
  })
})
