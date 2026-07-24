import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AdminLayout } from '../AdminLayout'

// Auth: pretend we are a logged-in ADMIN so AdminLayout doesn't redirect to
// /login. The shell only cares about the truthy admin signal here.
vi.mock('../../../features/auth', () => ({
  useAuth: () => ({
    user: { name: 'Test User', role: 'ADMIN' },
    isAuthenticated: true,
    isAdmin: true,
    isAuthRequired: true,
    isLoading: false,
    logout: vi.fn(),
  }),
}))

vi.mock('../../../features/auth/useChangePassword', () => ({
  useChangePassword: () => ({ open: vi.fn(), close: vi.fn(), isOpen: false }),
}))

vi.mock('../../../features/auth/ui/ChangePasswordModal', () => ({
  ChangePasswordModal: () => null,
}))

vi.mock('../../../features/workspace', () => ({
  useRoleVisibility: () => ({
    role: 'ADMIN',
    effectiveRole: 'ADMIN',
    canToggleViewAs: false,
    viewAsManager: false,
    toggleViewAsManager: vi.fn(),
    isRouteVisible: () => true,
    getVisibleNavGroups: () => [],
  }),
}))

vi.mock('../../../features/capabilities', () => ({
  useFeatureAvailability: () => ({
    isRouteAvailable: () => true,
    isLoading: false,
  }),
}))

// Health badge depends on a network query; stub it so the layout renders
// deterministically.
vi.mock('../../../features/health', () => ({
  useGlobalHealth: () => ({
    summary: { summary: 'ok', status: 'OK', generatedAt: new Date().toISOString(), allHealthy: true },
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

vi.mock('../../../features/issues', () => ({
  useIssueCenterSnapshot: () => ({ data: null, isError: false }),
}))

// GlobalStatusStrip needs dashboard data — return null so the strip renders
// nothing during onboarding (which is what we want — focus stays on the tour).
vi.mock('../../../features/dashboard/useDashboardData', () => ({
  useDashboardData: () => ({
    data: null,
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

const STORAGE_KEY = 'reactor-admin-v1-1-release-onboarding-completed'

function renderShell(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<AdminLayout />}>
          <Route index element={<div>dashboard content</div>} />
          <Route path="other" element={<div>other content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('AdminLayout — onboarding tour mounting', () => {
  beforeEach(() => {
    window.localStorage.clear()
    document.body
      .querySelectorAll('[data-testid="onboarding-tour"]')
      .forEach((n) => n.remove())
  })

  it('mounts the onboarding tour on the dashboard route for first-time visitors', () => {
    renderShell('/')
    expect(screen.getByTestId('onboarding-tour')).toBeInTheDocument()
    // Step 1 introduces the v1.1 release workflow before generic navigation.
    expect(screen.getByText('릴리즈 운영 흐름')).toBeInTheDocument()
    expect(screen.getByText(/release cockpit에서 필수\/누락 리포트와 blocker/)).toBeInTheDocument()
    expect(screen.getByText(/feedback\/eval 승격/)).toBeInTheDocument()
  })

  it('does not mount the onboarding tour on non-dashboard routes', () => {
    renderShell('/other')
    expect(screen.queryByTestId('onboarding-tour')).not.toBeInTheDocument()
  })

  it('does not re-mount the tour after it has been dismissed', () => {
    window.localStorage.setItem(STORAGE_KEY, '2026-04-24T00:00:00.000Z')
    renderShell('/')
    expect(screen.queryByTestId('onboarding-tour')).not.toBeInTheDocument()
  })

  it('persists completion when the user clicks through every step', () => {
    renderShell('/')
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('1/4')
    fireEvent.click(screen.getByTestId('onboarding-tour-next'))
    fireEvent.click(screen.getByTestId('onboarding-tour-next'))
    fireEvent.click(screen.getByTestId('onboarding-tour-next'))
    expect(screen.getByTestId('onboarding-tour-counter')).toHaveTextContent('4/4')
    fireEvent.click(screen.getByTestId('onboarding-tour-next')) // 완료
    expect(screen.queryByTestId('onboarding-tour')).not.toBeInTheDocument()
    expect(window.localStorage.getItem(STORAGE_KEY)).not.toBeNull()
  })
})
