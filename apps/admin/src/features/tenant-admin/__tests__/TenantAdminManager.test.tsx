import { describe, it, expect, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor, fireEvent, within } from '../../../test/utils'
import { TenantAdminManager } from '../ui/TenantAdminManager'
import * as api from '../api'

vi.mock('../api', () => ({
  getOverview: vi.fn(),
  getUsage: vi.fn(),
  getQuality: vi.fn(),
  getTools: vi.fn(),
  getCost: vi.fn(),
  getSlo: vi.fn(),
  getTenantAlerts: vi.fn(),
  getQuota: vi.fn(),
  exportExecutionsCsv: vi.fn(),
  exportToolsCsv: vi.fn(),
}))

vi.mock('../../workspace', () => ({
  useRoleVisibility: vi.fn().mockReturnValue({
    role: 'ADMIN',
    effectiveRole: 'ADMIN',
    viewAsManager: false,
    canToggleViewAs: true,
    toggleViewAsManager: vi.fn(),
    isRouteVisible: vi.fn().mockReturnValue(true),
    getVisibleNavGroups: vi.fn().mockReturnValue([]),
  }),
}))

vi.mock('../../workspace/RoleVisibilityProvider', () => ({
  useRoleVisibility: vi.fn().mockReturnValue({
    role: 'ADMIN',
    effectiveRole: 'ADMIN',
    viewAsManager: false,
    canToggleViewAs: true,
    toggleViewAsManager: vi.fn(),
    isRouteVisible: vi.fn().mockReturnValue(true),
    getVisibleNavGroups: vi.fn().mockReturnValue([]),
  }),
}))

const getOverviewMock = vi.mocked(api.getOverview)
const getUsageMock = vi.mocked(api.getUsage)
const getQualityMock = vi.mocked(api.getQuality)
const getToolsMock = vi.mocked(api.getTools)
const getCostMock = vi.mocked(api.getCost)
const getSloMock = vi.mocked(api.getSlo)
const getTenantAlertsMock = vi.mocked(api.getTenantAlerts)
const getQuotaMock = vi.mocked(api.getQuota)

describe('TenantAdminManager', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title and tenant scope form on initial render', () => {
    render(<MemoryRouter><TenantAdminManager /></MemoryRouter>)
    expect(screen.getByText('Tenant Analytics')).toBeInTheDocument()
    expect(screen.getByText('Tenant Scope')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Load Tenant Dashboards' })).toBeInTheDocument()
  })

  it('shows one scoped empty state before data is loaded', () => {
    render(<TenantAdminManager />)
    expect(screen.getByText('tenantAdminPage.selectScope')).toBeInTheDocument()
    expect(screen.queryByText('No overview data')).not.toBeInTheDocument()
    expect(screen.queryByText('Raw JSON')).not.toBeInTheDocument()
  })

  it('hides export actions until a verified report has been requested', () => {
    render(<TenantAdminManager />)
    expect(screen.queryByRole('button', { name: 'Export Executions CSV' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export Tool Calls CSV' })).not.toBeInTheDocument()
  })

  it('shows overview data after Load button clicked and data resolves', async () => {
    getOverviewMock.mockResolvedValue({ totalRequests: 1234, successRate: 0.98, avgResponseTimeMs: 230, apdexScore: 0.93, sloAvailability: 0.999, errorBudgetRemaining: 0.82, monthlyCost: '12.5', activeAlerts: 0 })
    getUsageMock.mockResolvedValue({ timeSeries: [], channelDistribution: {}, topUsers: [], avgTurnsPerSession: 3.2, sessionAbandonRate: 0.04, sessionResolveRate: 0.91 })
    getQualityMock.mockResolvedValue({ successRateTrend: [], apdexTrend: [], latencyP50: 180, latencyP95: 420, latencyP99: 800, errorDistribution: {} })
    getToolsMock.mockResolvedValue({ toolRanking: [], slowestTools: [], statusCounts: {} })
    getCostMock.mockResolvedValue({ monthlyCost: '12.5', dailyCostTrend: [], costByModel: {}, costPerResolution: '0.2', cachedTokenRatio: 0.3, budgetUsagePercent: 12.5 })
    getSloMock.mockResolvedValue({ tenantId: 'default', sloAvailability: 0.999, sloLatencyP99Ms: 1000, currentAvailability: 0.9995, latencyP99Ms: 800, errorBudgetRemaining: 0.82 })
    getTenantAlertsMock.mockResolvedValue([])
    getQuotaMock.mockResolvedValue({ tenantId: 'default', quota: { maxRequestsPerMonth: 10000, maxTokensPerMonth: 1000000, maxUsers: 20, maxAgents: 10, maxMcpServers: 10 }, usage: { requests: 1234, tokens: 50000, costUsd: '12.5' }, requestUsagePercent: 12.34, tokenUsagePercent: 5 })

    render(<MemoryRouter><TenantAdminManager /></MemoryRouter>)
    fireEvent.change(screen.getByRole('textbox', { name: 'tenantAdminPage.tenantId' }), { target: { value: 'default' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load Tenant Dashboards' }))

    await waitFor(() => {
      expect(screen.getByText('1,234')).toBeInTheDocument()
    })
    expect(screen.queryByText('Raw JSON')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export Executions CSV' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Export Tool Calls CSV' })).toBeInTheDocument()
  })

  it('keeps a failed organization load actionable and technical details closed', async () => {
    getOverviewMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getUsageMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getQualityMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getToolsMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getCostMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getSloMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getTenantAlertsMock.mockRejectedValueOnce(new Error('Tenant not found'))
    getQuotaMock.mockRejectedValueOnce(new Error('Tenant not found'))

    render(<TenantAdminManager />)
    fireEvent.change(screen.getByRole('textbox', { name: 'tenantAdminPage.tenantId' }), { target: { value: 'missing' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load Tenant Dashboards' }))

    await waitFor(() => {
      expect(screen.getByText('tenantAdminPage.loadErrorTitle')).toBeInTheDocument()
    })
    expect(screen.getByText('tenantAdminPage.loadErrorDescription')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Export Executions CSV' })).not.toBeInTheDocument()
    expect(screen.queryByText('tenantAdminPage.noActiveAlerts')).not.toBeInTheDocument()
    const details = document.querySelector('.tenant-operations__load-error details')
    expect(details).not.toHaveAttribute('open')
    expect(within(details as HTMLElement).getByText('Tenant not found')).toBeInTheDocument()
  })

  it('does not show internal labels as organization operations copy', async () => {
    getOverviewMock.mockResolvedValue({ totalRequests: 12, successRate: 0.98, avgResponseTimeMs: 230, apdexScore: 0.93, sloAvailability: 0.999, errorBudgetRemaining: 0.82, monthlyCost: '12.5', activeAlerts: 1 })
    getUsageMock.mockResolvedValue({ timeSeries: [], channelDistribution: { INTERNAL_SOCKET: 3 }, topUsers: [], avgTurnsPerSession: 3.2, sessionAbandonRate: 0.04, sessionResolveRate: 0.91 })
    getQualityMock.mockResolvedValue({ successRateTrend: [], apdexTrend: [], latencyP50: 180, latencyP95: 420, latencyP99: 800, errorDistribution: { BACKEND_UNKNOWN: 2 } })
    getToolsMock.mockResolvedValue({ toolRanking: [{ toolName: 'private_worker', mcpServerName: 'private-server', calls: 5, successRate: 1, avgDurationMs: 120, p95DurationMs: 220 }], slowestTools: [], statusCounts: {} })
    getCostMock.mockResolvedValue({ monthlyCost: '12.5', dailyCostTrend: [], costByModel: {}, costPerResolution: '0.2', cachedTokenRatio: 0.3, budgetUsagePercent: 12.5 })
    getSloMock.mockResolvedValue({ tenantId: 'default', sloAvailability: 0.999, sloLatencyP99Ms: 1000, currentAvailability: 0.9995, latencyP99Ms: 800, errorBudgetRemaining: 0.82 })
    getTenantAlertsMock.mockResolvedValue([{ id: 'alert-1', severity: 'SEV1_INTERNAL', message: '확인이 필요한 알림', status: 'PENDING_SYNC', firedAt: '2026-07-13T10:00:00Z' }])
    getQuotaMock.mockResolvedValue({ tenantId: 'default', quota: { maxRequestsPerMonth: 10000, maxTokensPerMonth: 1000000, maxUsers: 20, maxAgents: 10, maxMcpServers: 10 }, usage: { requests: 12, tokens: 500, costUsd: '12.5' }, requestUsagePercent: 0.12, tokenUsagePercent: 0.05 })

    render(<MemoryRouter><TenantAdminManager /></MemoryRouter>)
    fireEvent.change(screen.getByRole('textbox', { name: 'tenantAdminPage.tenantId' }), { target: { value: 'default' } })
    fireEvent.click(screen.getByRole('button', { name: 'Load Tenant Dashboards' }))

    await waitFor(() => {
      expect(screen.getByText('tenantAdminPage.channelLabels.unknown')).toBeInTheDocument()
    })
    expect(screen.getByText('tenantAdminPage.errorLabels.unknown')).toBeInTheDocument()
    expect(screen.getByText('확인할 수 없는 외부 도구')).toBeInTheDocument()
    expect(screen.getByText('tenantAdminPage.externalTool')).toBeInTheDocument()
    expect(screen.getByText('tenantAdminPage.alertSeverity.unknown')).toBeInTheDocument()
    expect(screen.getByText('tenantAdminPage.alertStatus.unknown')).toBeInTheDocument()
    expect(screen.queryByText('INTERNAL_SOCKET')).not.toBeInTheDocument()
    expect(screen.queryByText('BACKEND_UNKNOWN')).not.toBeInTheDocument()
    expect(screen.queryByText('private_worker')).not.toBeInTheDocument()
    expect(screen.queryByText('PENDING_SYNC')).not.toBeInTheDocument()
  })

  it('does not invent a default tenant ID', () => {
    render(<TenantAdminManager />)
    const tenantInput = screen.getByRole('textbox', { name: 'tenantAdminPage.tenantId' })
    expect(tenantInput).toHaveValue('')
  })

  it('cost bar chart sources its colors from the shared CHART_PALETTE / ChartConfig (CB-safe migration)', () => {
    // The Cost section bar chart used to pull from the legacy `chartColors`
    // module — this guard mirrors the EvalScoreTrendChart pattern so a
    // future regression that re-introduces hardcoded hex / chartColors lookups
    // fails CI rather than drifting silently.
    const source = readFileSync(
      resolve(__dirname, '../ui/TenantAdminManager.tsx'),
      'utf8',
    )
    expect(source).toContain('paletteColor(')
    expect(source).toContain('CHART_GRID_STYLE')
    expect(source).toContain('CHART_AXIS_STYLE')
    expect(source).not.toMatch(/chartColors\./)
  })
})
