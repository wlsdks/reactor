import { beforeEach, describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { Header } from '../Header'

const { logoutMock, openPasswordMock, toggleViewAsManagerMock } = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  openPasswordMock: vi.fn(),
  toggleViewAsManagerMock: vi.fn(),
}))

vi.mock('../../../features/auth', () => ({
  useAuth: () => ({
    user: { name: 'Test User', role: 'ADMIN' },
    isAuthenticated: true,
    isAdmin: true,
    logout: logoutMock,
  }),
}))

// GlobalStatusStrip pulls dashboard / issue-center data — stub both here so
// the Header renders deterministically without firing real queries.
vi.mock('../../../features/dashboard/useDashboardData', () => ({
  useDashboardData: () => ({
    data: {
      generatedAt: Date.now(),
      ragEnabled: false,
      mcp: { total: 12, statusCounts: { CONNECTED: 12 } },
      scheduler: {
        totalJobs: 0, enabledJobs: 0, runningJobs: 0, failedJobs: 0,
        attentionBacklog: 0, agentJobs: 0,
      },
      recentSchedulerExecutions: [],
      approvals: { pendingCount: 0 },
      responseTrust: {
        unverifiedResponses: 0, outputGuardRejected: 0,
        outputGuardModified: 0, boundaryFailures: 0,
      },
      employeeValue: {
        observedResponses: 0, groundedResponses: 0, groundedRatePercent: 0,
        blockedResponses: 0, interactiveResponses: 0, scheduledResponses: 0,
        answerModes: {}, channels: [], lanes: [], toolFamilies: [],
        topMissingQueries: [],
      },
      recentTrustEvents: [],
      metrics: [],
    },
    metricNames: [],
    readinessSummary: null,
    platformReadiness: null,
    reactorConnection: null,
    projectConnections: [],
    extraMcpServers: [],
    isLoading: false,
    isFetching: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

vi.mock('../../../features/issues', () => ({
  useIssueCenterSnapshot: () => ({
    data: {
      generatedAt: Date.now(),
      total: 0,
      criticalCount: 0,
      warningCount: 0,
      sources: [],
      items: [],
    },
    isError: false,
  }),
}))

vi.mock('../../../features/auth/useChangePassword', () => ({
  useChangePassword: () => ({
    open: openPasswordMock,
    close: vi.fn(),
    isOpen: false,
  }),
}))

vi.mock('../../../features/auth/ui/ChangePasswordModal', () => ({
  ChangePasswordModal: () => null,
}))

vi.mock('../../../features/workspace', () => ({
  useRoleVisibility: () => ({
    role: 'ADMIN',
    effectiveRole: 'ADMIN',
    canToggleViewAs: true,
    viewAsManager: false,
    toggleViewAsManager: toggleViewAsManagerMock,
  }),
}))

// Stub the global health hook so the header renders deterministically.
vi.mock('../../../features/health', () => ({
  useGlobalHealth: () => ({
    summary: {
      summary: 'ok',
      status: 'OK',
      generatedAt: new Date().toISOString(),
      allHealthy: true,
    },
    report: undefined,
    isLoading: false,
    isError: false,
    error: undefined,
    passed: 5,
    total: 5,
    criticalCount: 0,
    warnCount: 0,
    generatedAt: new Date().toISOString(),
  }),
}))

describe('Header', () => {
  beforeEach(() => {
    logoutMock.mockReset()
    openPasswordMock.mockReset()
    toggleViewAsManagerMock.mockReset()
  })

  it('mounts the HeaderHealthBadge in the right cluster', () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    )

    // The badge is the only element with data-status; presence proves the
    // health badge is wired into the global header.
    const badge = document.querySelector('.header-health-badge')
    expect(badge).not.toBeNull()
    expect(badge?.getAttribute('data-status')).toBe('ok')

    // It also renders the localized status word.
    expect(screen.getAllByText(/header\.health\.statusOk/)[0]).toBeInTheDocument()
  })

  it('keeps account commands in one accessible menu', () => {
    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: 'auth.changePassword' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'auth.logout' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'header.account.openMenu' }))

    expect(screen.getByRole('menu', { name: 'header.account.menuLabel' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('menuitem', { name: 'auth.changePassword' }))
    expect(openPasswordMock).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: 'header.account.openMenu' }))
    fireEvent.click(screen.getByRole('menuitem', { name: 'auth.logout' }))
    expect(logoutMock).toHaveBeenCalledTimes(1)
  })
})
