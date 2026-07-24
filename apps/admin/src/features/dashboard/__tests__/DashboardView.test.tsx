import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { DashboardView } from '../ui/DashboardView'
import { useDashboardData } from '../useDashboardData'

vi.mock('../useDashboardData', () => ({ useDashboardData: vi.fn() }))
vi.mock('../../issues', () => ({ useIssueCenterSnapshot: () => ({ data: undefined }) }))
vi.mock('../../workspace/RoleVisibilityProvider', () => ({ useRoleVisibility: () => ({ effectiveRole: 'SUPER_ADMIN' }) }))
vi.mock('../../capabilities', () => ({ useFeatureAvailability: () => ({ isDurable: true }) }))
vi.mock('../../../shared/lib/usePageHelp', () => ({ usePageHelp: vi.fn() }))
vi.mock('../../doctor', () => ({ DoctorBanner: () => <div data-testid="doctor-banner" /> }))
vi.mock('../../release-operations', () => ({ ReleaseOperationsSummary: () => null }))

const useDashboardDataMock = vi.mocked(useDashboardData)

describe('DashboardView', () => {
  it('renders one fail-closed recovery surface when dashboard data is unavailable', () => {
    const refetch = vi.fn()
    useDashboardDataMock.mockReturnValue({
      data: null,
      metricNames: [],
      platformReadiness: null,
      reactorConnection: null,
      projectConnections: [],
      extraMcpServers: [],
      isLoading: false,
      isFetching: false,
      error: 'HTTP 403: tenant context missing',
      errorHint: '이 작업은 ADMIN 권한이 필요해요',
      refetch,
      dataUpdatedAt: 0,
    } as never)

    render(<MemoryRouter><DashboardView /></MemoryRouter>)

    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('dashboard.unavailable.title')
    expect(alert).toHaveTextContent('이 작업은 ADMIN 권한이 필요해요')
    expect(alert).not.toHaveTextContent('common.loadError')
    expect(screen.queryByTestId('doctor-banner')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'dashboard.unavailable.openHealth' })).toHaveAttribute('href', '/health')
    expect(screen.getByText('dashboard.unavailable.technical').closest('details')).not.toHaveAttribute('open')

    fireEvent.click(screen.getByRole('button', { name: 'dashboard.unavailable.retry' }))
    expect(refetch).toHaveBeenCalledTimes(1)
  })

  it('keeps retry feedback pending until the request returns', () => {
    useDashboardDataMock.mockReturnValue({
      data: null,
      metricNames: [],
      platformReadiness: null,
      reactorConnection: null,
      projectConnections: [],
      extraMcpServers: [],
      isLoading: false,
      isFetching: true,
      error: 'HTTP 503',
      errorHint: null,
      refetch: vi.fn(),
      dataUpdatedAt: 0,
    } as never)

    render(<MemoryRouter><DashboardView /></MemoryRouter>)

    expect(screen.getByRole('button', { name: 'dashboard.unavailable.retrying' })).toBeDisabled()
    expect(screen.queryByText('common.toast.refreshed')).not.toBeInTheDocument()
  })
})
