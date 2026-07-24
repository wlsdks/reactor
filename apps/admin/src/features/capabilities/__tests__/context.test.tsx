import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '../../../test/utils'
import { server } from '../../../test/server'
import { http, HttpResponse } from 'msw'
import { AuthProvider } from '../../auth'
import { FeatureAvailabilityProvider, useFeatureAvailability } from '../context'
import { removeAuthToken, setAuthToken } from '../../../shared/api/client'

vi.mock('../api', () => ({
  getCapabilityManifest: vi.fn(),
}))

vi.mock('../../auth/api', () => ({
  directLogin: vi.fn(),
  iamLogin: vi.fn(),
  exchangeToken: vi.fn(),
  iamLogout: vi.fn(),
  IAM_ENABLED: false,
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  changePassword: vi.fn(),
}))

import { getCapabilityManifest } from '../api'
const getCapabilityManifestMock = vi.mocked(getCapabilityManifest)

/** Build a fake JWT that userFromToken() can parse. */
function fakeJwt(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: 'RS256', kid: 'test' }))
  const body = btoa(JSON.stringify(payload))
  return `${header}.${body}.fake-sig`
}

const adminToken = fakeJwt({
  sub: 'admin-id',
  roles: ['ROLE_USER', 'ROLE_ADMIN'],
  permissions: ['READ_PROFILE', 'MANAGE_USERS'],
  iss: 'reactor-iam',
  exp: 9999999999,
  iat: 1700000000,
  jti: 'test-jti',
})

function CapabilityStatus() {
  const { isLoading, mode, isRouteAvailable } = useFeatureAvailability()

  if (isLoading) return <div>loading</div>

  return (
    <div data-testid="capability-status">
      {mode}
      |{String(isRouteAvailable('/mcp-servers'))}
      |{String(isRouteAvailable('/documents'))}
      |{String(isRouteAvailable('/integrations'))}
    </div>
  )
}

describe('FeatureAvailabilityProvider', () => {
  beforeEach(() => {
    removeAuthToken()
    localStorage.clear()
    sessionStorage.clear()
    getCapabilityManifestMock.mockReset()
    window.history.replaceState({}, '', '/')
  })

  it('uses capability manifest without probing optional endpoints', async () => {
    let openApiCalls = 0
    let documentProbeCalls = 0

    // Mock getCapabilityManifest to return the expected manifest set
    getCapabilityManifestMock.mockResolvedValue(
      new Set(['/api/admin/capabilities', '/api/ops/dashboard', '/api/mcp/servers', '/api/proactive-channels', '/api/admin/slack-bots']),
    )

    server.use(
      http.get('/v3/api-docs', () => {
        openApiCalls += 1
        return HttpResponse.json({ error: 'should not be called' }, { status: 500 })
      }),
      http.get('/api/documents', () => {
        documentProbeCalls += 1
        return HttpResponse.json({ error: 'should not be probed' }, { status: 404 })
      }),
    )

    setAuthToken(adminToken)

    render(
      <AuthProvider>
        <FeatureAvailabilityProvider>
          <CapabilityStatus />
        </FeatureAvailabilityProvider>
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('capability-status').textContent).toBe('manifest|true|false|true')
    })

    expect(openApiCalls).toBe(0)
    expect(documentProbeCalls).toBe(0)
  })

  it('skips capability fetch on login route even with cached admin session', async () => {
    let capabilityCalls = 0
    window.history.replaceState({}, '', '/login')

    server.use(
      http.get('/api/admin/capabilities', () => {
        capabilityCalls += 1
        return HttpResponse.json({ error: 'should not be called' }, { status: 401 })
      }),
    )

    setAuthToken('stale-token')

    render(
      <AuthProvider>
        <FeatureAvailabilityProvider>
          <CapabilityStatus />
        </FeatureAvailabilityProvider>
      </AuthProvider>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('capability-status').textContent).toBe('none|true|true|true')
    })

    expect(capabilityCalls).toBe(0)
    window.history.replaceState({}, '', '/')
  })
})
