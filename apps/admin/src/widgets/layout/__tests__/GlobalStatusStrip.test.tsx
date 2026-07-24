import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { GlobalStatusStrip } from '../GlobalStatusStrip'
import type { DashboardResponse } from '../../../features/dashboard/types'
import type { IssueCenterSnapshot } from '../../../features/issues'

// ── Mocks ─────────────────────────────────────────────────────────────────
type AuthMock = { isAuthenticated: boolean, isAdmin: boolean }
const mockAuth = vi.fn<[], AuthMock>()
vi.mock('../../../features/auth', () => ({
  useAuth: () => mockAuth(),
}))

type DashboardHookValue = {
  data: DashboardResponse | null
  error: string | null
  isLoading: boolean
  isFetching: boolean
}
const mockDashboard = vi.fn<[], DashboardHookValue>()
vi.mock('../../../features/dashboard/useDashboardData', () => ({
  useDashboardData: () => mockDashboard(),
}))

type IssuesHookValue = {
  data: IssueCenterSnapshot | undefined
  isError: boolean
}
const mockIssues = vi.fn<[], IssuesHookValue>()
vi.mock('../../../features/issues', () => ({
  useIssueCenterSnapshot: () => mockIssues(),
}))

// ── Builders ──────────────────────────────────────────────────────────────
function buildDashboard(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    generatedAt: new Date('2026-04-25T05:32:00Z').getTime(),
    ragEnabled: false,
    mcp: { total: 12, statusCounts: { CONNECTED: 12 } },
    scheduler: {
      totalJobs: 0,
      enabledJobs: 0,
      runningJobs: 0,
      failedJobs: 0,
      attentionBacklog: 0,
      agentJobs: 0,
    },
    recentSchedulerExecutions: [],
    approvals: { pendingCount: 5 },
    responseTrust: {
      unverifiedResponses: 0,
      outputGuardRejected: 0,
      outputGuardModified: 0,
      boundaryFailures: 0,
    },
    employeeValue: {
      observedResponses: 0,
      groundedResponses: 0,
      groundedRatePercent: 0,
      blockedResponses: 0,
      interactiveResponses: 0,
      scheduledResponses: 0,
      answerModes: {},
      channels: [],
      lanes: [],
      toolFamilies: [],
      topMissingQueries: [],
    },
    recentTrustEvents: [],
    metrics: [],
    ...overrides,
  }
}

function buildIssueSnapshot(overrides: Partial<IssueCenterSnapshot> = {}): IssueCenterSnapshot {
  return {
    generatedAt: Date.now(),
    total: 3,
    criticalCount: 1,
    warningCount: 2,
    sources: [],
    items: [],
    ...overrides,
  }
}

function renderStrip() {
  return render(
    <MemoryRouter>
      <GlobalStatusStrip />
    </MemoryRouter>,
  )
}

// ── Tests ─────────────────────────────────────────────────────────────────
describe('GlobalStatusStrip', () => {
  beforeEach(() => {
    mockAuth.mockReset()
    mockDashboard.mockReset()
    mockIssues.mockReset()
  })

  it('renders nothing when user is not authenticated', () => {
    mockAuth.mockReturnValue({ isAuthenticated: false, isAdmin: false })
    mockDashboard.mockReturnValue({ data: null, error: null, isLoading: false, isFetching: false })
    mockIssues.mockReturnValue({ data: undefined, isError: false })
    const { container } = renderStrip()
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing while both data sources are still loading', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({ data: null, error: null, isLoading: true, isFetching: true })
    mockIssues.mockReturnValue({ data: undefined, isError: false })
    const { container } = renderStrip()
    expect(container.firstChild).toBeNull()
  })

  it('renders all four chips when data is ready', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard(),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: buildIssueSnapshot(), isError: false })

    renderStrip()

    expect(document.querySelector('[data-chip="mcp"]')).not.toBeNull()
    expect(document.querySelector('[data-chip="issues"]')).not.toBeNull()
    expect(document.querySelector('[data-chip="approvals"]')).not.toBeNull()
    expect(document.querySelector('[data-chip="last-updated"]')).not.toBeNull()
  })

  it('renders MCP chip with ready/total ratio', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard({ mcp: { total: 12, statusCounts: { CONNECTED: 8 } } }),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: buildIssueSnapshot(), isError: false })

    renderStrip()

    const mcpChip = document.querySelector('[data-chip="mcp"]')
    expect(mcpChip?.textContent).toContain('8/12')
    expect(mcpChip?.getAttribute('href')).toBe('/mcp-servers')
  })

  it('hides MCP chip when total is 0', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard({ mcp: { total: 0, statusCounts: {} } }),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: buildIssueSnapshot(), isError: false })

    renderStrip()

    expect(document.querySelector('[data-chip="mcp"]')).toBeNull()
    // Other chips still render — strip degrades per-chip.
    expect(document.querySelector('[data-chip="issues"]')).not.toBeNull()
  })

  it('marks issue chip as active (amber) when count > 0', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard(),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({
      data: buildIssueSnapshot({ criticalCount: 1, warningCount: 2 }),
      isError: false,
    })

    renderStrip()

    const issuesChip = document.querySelector('[data-chip="issues"]')
    expect(issuesChip?.getAttribute('data-active')).toBe('true')
  })

  it('marks issue chip as inactive (muted) when count is 0', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard({ approvals: { pendingCount: 0 } }),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({
      data: buildIssueSnapshot({ criticalCount: 0, warningCount: 0, total: 0 }),
      isError: false,
    })

    renderStrip()

    expect(document.querySelector('[data-chip="issues"]')?.getAttribute('data-active')).toBe('false')
    expect(document.querySelector('[data-chip="approvals"]')?.getAttribute('data-active')).toBe('false')
  })

  it('chips that link out are anchors with valid href targets', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard(),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: buildIssueSnapshot(), isError: false })

    renderStrip()

    expect(document.querySelector('[data-chip="mcp"]')?.tagName).toBe('A')
    expect(document.querySelector('[data-chip="issues"]')?.getAttribute('href')).toBe('/issues')
    expect(document.querySelector('[data-chip="approvals"]')?.getAttribute('href')).toBe('/approvals')
    // Last-updated is informational only — not a link.
    expect(document.querySelector('[data-chip="last-updated"]')?.tagName).not.toBe('A')
  })

  it('hides issues chip when issues query is in error state', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard(),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: undefined, isError: true })

    renderStrip()

    expect(document.querySelector('[data-chip="issues"]')).toBeNull()
    // Dashboard-backed chips still render so the rest of the strip works.
    expect(document.querySelector('[data-chip="mcp"]')).not.toBeNull()
    expect(document.querySelector('[data-chip="approvals"]')).not.toBeNull()
  })

  it('hides MCP and approvals when dashboard is in error state', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: null,
      error: 'Network down',
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: buildIssueSnapshot(), isError: false })

    renderStrip()

    expect(document.querySelector('[data-chip="mcp"]')).toBeNull()
    expect(document.querySelector('[data-chip="approvals"]')).toBeNull()
    // Issue chip still works.
    expect(document.querySelector('[data-chip="issues"]')).not.toBeNull()
  })

  it('renders nothing when dashboard query is in error state and issues data is missing', () => {
    // Regression: an unmocked /api/ops/dashboard in an e2e spec must not tear
    // down the layout. With both data sources unavailable, the strip degrades
    // to silence rather than throwing on missing nested fields.
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: null,
      error: 'Network down',
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: undefined, isError: true })

    const { container } = renderStrip()
    expect(container.firstChild).toBeNull()
  })

  it('does not throw when dashboard data is partial / malformed', () => {
    // Some non-OK responses still parse as JSON but lack the expected shape
    // (e.g. proxied HTML page, or a 200 envelope without nested `mcp`/
    // `approvals`). All nested access must short-circuit to safe defaults.
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      // Cast: deliberately construct an incomplete shape to verify resilience.
      data: {} as DashboardResponse,
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: undefined, isError: false })

    expect(() => renderStrip()).not.toThrow()
    // MCP chip hidden because total coerces to 0; approvals hidden because
    // approvals key is missing; last-updated hidden because generatedAt is
    // absent. With every chip silenced, the wrapper renders nothing.
    expect(document.querySelector('[data-chip="mcp"]')).toBeNull()
    expect(document.querySelector('[data-chip="approvals"]')).toBeNull()
    expect(document.querySelector('[data-chip="last-updated"]')).toBeNull()
  })

  it('exposes group-level aria-label for screen readers', () => {
    mockAuth.mockReturnValue({ isAuthenticated: true, isAdmin: true })
    mockDashboard.mockReturnValue({
      data: buildDashboard(),
      error: null,
      isLoading: false,
      isFetching: false,
    })
    mockIssues.mockReturnValue({ data: buildIssueSnapshot(), isError: false })

    renderStrip()

    const group = screen.getByRole('group', { name: /global system status|전체 시스템 상태/i })
    expect(group).toBeInTheDocument()
  })
})
