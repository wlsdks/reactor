import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '../../test/utils'
import { AuthProvider } from '../../features/auth/context'
import { removeAuthToken } from '../../shared/api/client'
import {
  setLogoutReason,
  clearLogoutReason,
  readLogoutReason,
} from '../../features/auth/logoutReason'
import { LoginPage } from '../LoginPage'

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

vi.mock('../../features/auth/api', () => ({
  directLogin: vi.fn(),
  iamLogin: vi.fn(),
  exchangeToken: vi.fn(),
  iamLogout: vi.fn(),
  IAM_ENABLED: false,
  logout: vi.fn(),
  register: vi.fn(),
  changePassword: vi.fn(),
  demoLogin: vi.fn(),
}))

import * as authApi from '../../features/auth/api'
const directLoginMock = vi.mocked(authApi.directLogin)
const demoLoginMock = vi.mocked(authApi.demoLogin)

/** Build a fake JWT that userFromToken() can parse. */
function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', kid: 'test' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-sig`
}

const adminToken = fakeJwt({
  sub: 'user-1',
  roles: ['ROLE_USER', 'ROLE_ADMIN'],
  permissions: ['READ_PROFILE', 'MANAGE_USERS'],
  iss: 'reactor-iam',
  exp: 9999999999,
  iat: 1700000000,
  jti: 'test-jti',
})

function renderLoginPage() {
  return render(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    removeAuthToken()
    clearLogoutReason()
    mockNavigate.mockClear()
    window.history.pushState({}, '', '/login')
    directLoginMock.mockResolvedValue({
      token: adminToken,
      user: { id: 'user-1', email: 'admin@example.com', name: 'admin', role: 'ADMIN' },
      error: null,
    })
    demoLoginMock.mockResolvedValue({
      token: adminToken,
      user: { id: 'demo-user', email: 'demo@reactor.local', name: 'Demo Admin', role: 'ADMIN' },
      error: null,
    })
  })

  it('renders the login form', async () => {
    renderLoginPage()
    await waitFor(() => {
      expect(screen.getByLabelText('auth.email')).toBeInTheDocument()
      expect(screen.getByLabelText('auth.password')).toBeInTheDocument()
    })
  })

  it('shows one local demo login action in dev mode', async () => {
    renderLoginPage()
    await waitFor(() => {
      expect(screen.getByText('auth.demoLogin')).toBeInTheDocument()
    })
    expect(screen.queryByText('auth.devLogin')).not.toBeInTheDocument()
  })

  it('local demo login action uses the dedicated endpoint and navigates', async () => {
    renderLoginPage()
    await waitFor(() => {
      expect(screen.getByText('auth.demoLogin')).toBeInTheDocument()
    })

    await act(async () => {
      screen.getByText('auth.demoLogin').click()
    })

    await waitFor(() => {
      expect(demoLoginMock).toHaveBeenCalledOnce()
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
  })

  describe('logout reason banner', () => {
    it('shows the cross-tab banner when the reason flag is set', async () => {
      setLogoutReason('cross-tab')
      renderLoginPage()
      await waitFor(() => {
        expect(screen.getByTestId('logout-reason-banner')).toBeInTheDocument()
      })
      expect(screen.getByTestId('logout-reason-banner')).toHaveTextContent(
        'auth.logoutReason.crossTab',
      )
    })

    it('shows the session-expired banner when the reason flag is set', async () => {
      setLogoutReason('session-expired')
      renderLoginPage()
      await waitFor(() => {
        expect(screen.getByTestId('logout-reason-banner')).toBeInTheDocument()
      })
      expect(screen.getByTestId('logout-reason-banner')).toHaveTextContent(
        'auth.logoutReason.sessionExpired',
      )
    })

    it('clears the reason flag once the banner is rendered', async () => {
      setLogoutReason('cross-tab')
      renderLoginPage()
      await waitFor(() => {
        expect(screen.getByTestId('logout-reason-banner')).toBeInTheDocument()
      })
      // The flag is consumed on mount so it does not leak across remounts.
      expect(readLogoutReason()).toBeNull()
    })

    it('renders no banner when no reason flag is set', async () => {
      renderLoginPage()
      await waitFor(() => {
        expect(screen.getByLabelText('auth.email')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('logout-reason-banner')).not.toBeInTheDocument()
    })
  })
})
