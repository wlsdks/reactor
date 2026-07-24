import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const MOCK_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/approvals',
  '/api/auth/login',
  '/api/auth/me',
  '/api/auth/register',
  '/api/chat',
  '/api/documents',
  '/api/feedback',
  '/api/intents',
  '/api/mcp/servers',
  '/api/ops/dashboard',
  '/api/ops/metrics/names',
  '/api/output-guard/rules',
  '/api/personas',
  '/api/prompt-lab/experiments',
  '/api/prompt-templates',
  '/api/rag-ingestion/candidates',
  '/api/scheduler/jobs',
  '/api/sessions',
  '/api/tool-policy',
]

const MOCK_DASHBOARD = {
  generatedAt: Date.now(),
  ragEnabled: true,
  mcp: {
    total: 3,
    statusCounts: { CONNECTED: 2, DISCONNECTED: 1 },
  },
  scheduler: {
    totalJobs: 5,
    enabledJobs: 3,
    runningJobs: 1,
    failedJobs: 0,
    attentionBacklog: 0,
    agentJobs: 2,
  },
  recentSchedulerExecutions: [
    {
      id: 'exec-1',
      jobId: 'job-1',
      jobName: 'Daily Digest',
      jobType: 'AGENT',
      status: 'SUCCESS',
      resultPreview: 'Generated digest',
      failureReason: null,
      dryRun: false,
      durationMs: 15400,
      startedAt: Date.now() - 3600000,
      completedAt: Date.now() - 3600000 + 15400,
    },
  ],
  approvals: { pendingCount: 2 },
  responseTrust: {
    unverifiedResponses: 3,
    outputGuardRejected: 1,
    outputGuardModified: 2,
    boundaryFailures: 0,
  },
  employeeValue: {
    observedResponses: 248,
    groundedResponses: 231,
    groundedRatePercent: 93.1,
    blockedResponses: 4,
    interactiveResponses: 195,
    scheduledResponses: 53,
    answerModes: { grounded: 231, blocked: 4, fallback: 13 },
    channels: [{ key: 'slack', count: 180 }],
    lanes: [],
    toolFamilies: [],
    topMissingQueries: [],
  },
  recentTrustEvents: [
    { occurredAt: Date.now() - 3600000, type: 'OUTPUT_GUARD_REJECT', severity: 'WARNING', action: 'REJECT', reason: 'PII detected', policy: 'pii-filter' },
  ],
  metrics: [
    { name: 'api.requests.total', meterCount: 1, measurements: { count: 1842, rate_1m: 2.3 } },
    { name: 'api.latency.p99', meterCount: 1, measurements: { value: 425 } },
  ],
}

const MOCK_TRENDS = {
  sessions: Array.from({ length: 24 }, (_, i) => ({
    hour: `${String(i).padStart(2, '0')}:00`,
    count: 15 + i,
  })),
  groundedRate: Array.from({ length: 24 }, (_, i) => ({
    hour: `${String(i).padStart(2, '0')}:00`,
    rate: 88 + Math.floor(i / 4),
  })),
}

const MOCK_METRIC_NAMES = [
  'api.requests.total',
  'api.latency.p99',
  'mcp.tool_calls.total',
  'tokens.consumed.total',
]

interface DashboardRouteOptions {
  dashboardResponse?: { status?: number; body: string }
  handleApi?: (url: string, method: string) => { status?: number; body: string }
}

async function setupDashboardPage(page: Page, options: DashboardRouteOptions = {}) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits', '/api/admin/capabilities', '/api/approvals', '/api/auth/login',
        '/api/auth/me', '/api/auth/register', '/api/chat', '/api/documents', '/api/feedback',
        '/api/intents', '/api/mcp/servers', '/api/ops/dashboard', '/api/ops/metrics/names',
        '/api/output-guard/rules', '/api/personas', '/api/prompt-lab/experiments',
        '/api/prompt-templates', '/api/rag-ingestion/candidates', '/api/scheduler/jobs',
        '/api/sessions', '/api/tool-policy',
      ],
      timestamp: Date.now(),
    }))
    localStorage.setItem('reactor-admin-v1-1-release-onboarding-completed', new Date().toISOString())
  }, MOCK_TOKEN)

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const url = requestUrl.toString()
    const method = route.request().method()

    if (url.includes('/auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (url.includes('/auth/login')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
      })
      return
    }
    if (url.includes('/admin/capabilities')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          source: 'playwright-mock',
          paths: MOCK_CAPABILITY_PATHS,
        }),
      })
      return
    }

    // Allow custom dashboard response override
    if (url.includes('/ops/dashboard/trends')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_TRENDS),
      })
      return
    }

    if (url.includes('/ops/metrics/names')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_METRIC_NAMES),
      })
      return
    }

    if (url.includes('/ops/dashboard') && method === 'GET') {
      if (options.dashboardResponse) {
        await route.fulfill({
          status: options.dashboardResponse.status ?? 200,
          contentType: 'application/json',
          body: options.dashboardResponse.body,
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_DASHBOARD),
      })
      return
    }

    if (options.handleApi) {
      const response = options.handleApi(url, method)
      await route.fulfill({
        status: response.status ?? 200,
        contentType: 'application/json',
        body: response.body,
      })
      return
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/')
}

test.describe('Dashboard page', () => {
  test('loads as the default route (/) and displays stat cards with metrics', async ({ page }) => {
    await setupDashboardPage(page)

    // The health bar should be visible
    await expect(page.locator('.health-bar')).toBeVisible({ timeout: 15000 })

    // Actionable operator work replaces the non-actionable health gauge and
    // stays ahead of the supporting metric cards in the page hierarchy.
    const prioritySection = page.locator('.dashboard-priority')
    await expect(prioritySection).toBeVisible()
    await expect(prioritySection.locator('.action-card--accent')).toBeVisible()

    // Stat cards section should show health/infrastructure/quality groups
    const statCards = page.locator('.dashboard-stats')
    await expect(statCards).toBeVisible()
    expect(await prioritySection.evaluate((element) => (
      Boolean(element.compareDocumentPosition(document.querySelector('.dashboard-stats')) & Node.DOCUMENT_POSITION_FOLLOWING)
    ))).toBe(true)

    // Verify stat card values from mock data
    // Health card: critical = 0 (from issueSnapshot which is empty), rejected = 1
    await expect(page.locator('.stat-group').first()).toBeVisible()

    // Infrastructure card shows connected count (2) and total servers (3)
    const infraCard = page.locator('.stat-group').nth(1)
    await expect(infraCard).toBeVisible()
    await expect(infraCard.locator('.stat-group-value', { hasText: '2' }).first()).toBeVisible()
    await expect(infraCard.locator('.stat-group-value', { hasText: '3' })).toBeVisible()

    // Quality card shows grounded rate (93.1%) and observed (248)
    const qualityCard = page.locator('.stat-group').nth(2)
    await expect(qualityCard).toBeVisible()
    await expect(qualityCard.locator('.stat-group-value', { hasText: '93.1%' })).toBeVisible()
    await expect(qualityCard.locator('.stat-group-value', { hasText: '248' })).toBeVisible()
  })

  // Trend charts were removed — backend has no /api/ops/dashboard/trends endpoint

  test('shows MCP server status in the infrastructure panel', async ({ page }) => {
    await setupDashboardPage(page)

    await expect(page.locator('.health-bar')).toBeVisible({ timeout: 15000 })

    // Infrastructure panel should be visible
    await expect(page.locator('.infra-panel')).toBeVisible()

    // MCP Servers section should list servers
    await expect(page.locator('.server-list')).toBeVisible()
  })

  test('shows action cards when there are pending approvals or guard rejections', async ({ page }) => {
    await setupDashboardPage(page)

    await expect(page.locator('.health-bar')).toBeVisible({ timeout: 15000 })

    // Since mock data has outputGuardRejected=1, outputGuardModified=2, pendingApprovals=2,
    // action cards should be displayed
    await expect(page.locator('.dashboard-action-cards, .action-cards')).toBeVisible()
  })

  test('shows developer mode action buttons (Employee Value, Operational Signals)', async ({ page }) => {
    await setupDashboardPage(page)

    await expect(page.locator('.health-bar')).toBeVisible({ timeout: 15000 })

    // Developer mode should show page-actions with two modal buttons
    const pageActions = page.locator('.page-actions')
    await expect(pageActions).toBeVisible()
    await expect(pageActions.locator('button')).toHaveCount(2)
  })

  test('displays error alert and retry button when dashboard API fails', async ({ page }) => {
    await setupDashboardPage(page, {
      dashboardResponse: {
        status: 500,
        body: JSON.stringify({ error: 'Internal server error' }),
      },
    })

    // Error alert should be visible
    await expect(page.locator('.alert-error')).toBeVisible({ timeout: 15000 })

    // Retry button should be visible within the error alert
    await expect(page.locator('.alert-error .btn')).toBeVisible()
  })

  test('shows health bar with MCP connected ratio and grounded percent', async ({ page }) => {
    await setupDashboardPage(page)

    const healthBar = page.locator('.health-bar')
    await expect(healthBar).toBeVisible({ timeout: 15000 })

    // Health bar should display MCP ratio (2/3 from mock)
    await expect(healthBar.getByText('MCP 2/3')).toBeVisible()

    // Health bar should display the localized grounded percent label.
    await expect(healthBar.getByText('93.1% 근거 정확도')).toBeVisible()
  })
})
