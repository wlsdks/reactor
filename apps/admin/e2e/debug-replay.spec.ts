import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/debug/replay',
  '/api/admin/debug/replay/{id}',
  '/api/auth/login',
  '/api/auth/me',
  '/api/ops/dashboard',
]

// GlobalStatusStrip in the header reads `data.mcp.total`,
// `data.approvals.pendingCount`, etc. — needs a properly shaped payload even
// when this page does not consume it.
const MOCK_DASHBOARD = {
  generatedAt: Date.now(),
  ragEnabled: false,
  mcp: { total: 0, statusCounts: { CONNECTED: 0, DISCONNECTED: 0 } },
  scheduler: {
    totalJobs: 0,
    enabledJobs: 0,
    runningJobs: 0,
    failedJobs: 0,
    attentionBacklog: 0,
    agentJobs: 0,
  },
  recentSchedulerExecutions: [],
  approvals: { pendingCount: 0 },
  responseTrust: { unverifiedResponses: 0 },
}

const NOW_ISO = '2026-04-25T10:00:00Z'
const EXPIRES_ISO = '2026-05-02T10:00:00Z'

const MOCK_CAPTURES = [
  {
    id: 'cap-rate',
    tenantId: 'default',
    userHash: 'a1b2c3d4e5f6',
    capturedAt: NOW_ISO,
    userPrompt: 'Why is my latest deploy stuck on staging? Need a quick triage.',
    errorCode: 'RATE_LIMITED',
    errorMessage: 'Too many requests in the last minute',
    modelId: 'claude-sonnet-4-20250514',
    toolsAttempted: 'jira_search,confluence_get_page',
    expiresAt: EXPIRES_ISO,
  },
  {
    id: 'cap-circuit',
    tenantId: 'default',
    userHash: '0f1e2d3c4b5a',
    capturedAt: NOW_ISO,
    userPrompt: 'Show me the outage runbook for prod gateway',
    errorCode: 'CIRCUIT_BREAKER_OPEN',
    errorMessage: 'Circuit breaker open for downstream service',
    modelId: 'claude-opus-4-20250514',
    toolsAttempted: null,
    expiresAt: EXPIRES_ISO,
  },
  {
    id: 'cap-tool',
    tenantId: 'default',
    userHash: 'feedfacecafef00d',
    capturedAt: NOW_ISO,
    userPrompt: 'Refresh search index',
    errorCode: 'TOOL_ERROR',
    errorMessage: 'Tool call failed',
    modelId: null,
    toolsAttempted: 'fs.write',
    expiresAt: EXPIRES_ISO,
  },
]

test.describe('/debug-replay page', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(
      ({ paths, token }: { paths: string[]; token: string }) => {
        localStorage.setItem('reactor-admin-token', token)
        sessionStorage.setItem(
          'reactor-admin-feature-availability-v2',
          JSON.stringify({
            mode: 'manifest',
            endpoints: paths,
            timestamp: Date.now(),
          }),
        )
      },
      { paths: CAPABILITY_PATHS, token: MOCK_TOKEN },
    )

    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url())
      if (!requestUrl.pathname.startsWith('/api/')) {
        await route.continue()
        return
      }

      const { pathname } = requestUrl

      if (pathname.endsWith('/auth/me')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USER),
        })
        return
      }
      if (pathname.endsWith('/auth/login')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
        })
        return
      }
      if (pathname.endsWith('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            generatedAt: Date.now(),
            source: 'playwright-mock',
            paths: CAPABILITY_PATHS,
          }),
        })
        return
      }
      if (pathname === '/api/ops/dashboard') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_DASHBOARD),
        })
        return
      }
      if (pathname === '/api/admin/debug/replay') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_CAPTURES),
        })
        return
      }
      if (pathname.startsWith('/api/admin/debug/replay/')) {
        const id = pathname.split('/').pop()
        const capture = MOCK_CAPTURES.find((c) => c.id === id) ?? MOCK_CAPTURES[0]
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(capture),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })
  })

  test('renders the page header and the seeded capture rows', async ({ page }) => {
    await page.goto('/debug-replay')

    await expect(page.getByRole('heading', { name: 'Debug Replay' })).toBeVisible()

    // All three captured prompts are rendered in the table body.
    await expect(
      page.getByText('Why is my latest deploy stuck on staging? Need a quick triage.'),
    ).toBeVisible()
    await expect(page.getByText('Show me the outage runbook for prod gateway')).toBeVisible()
    await expect(page.getByText('Refresh search index')).toBeVisible()
  })

  test('localizes known error codes in Korean while keeping the original code as title', async ({
    page,
  }) => {
    await page.goto('/debug-replay')

    // Wait for the table to render.
    await expect(page.getByText('Refresh search index')).toBeVisible()

    // Each known error code maps to a Korean label per `debugReplay.errors.*`.
    await expect(page.getByText('요청 한도 초과').first()).toBeVisible()
    await expect(page.getByText('회로 차단기 작동').first()).toBeVisible()
    await expect(page.getByText('도구 오류').first()).toBeVisible()

    // The localized cell preserves the raw code as a `title` attribute so
    // operators can hover to recover the backend constant.
    const rateLimitedCell = page.getByText('요청 한도 초과').first()
    await expect(rateLimitedCell).toHaveAttribute('title', 'RATE_LIMITED')
  })

  test('selecting a row reveals the detail panel with anonymized user hash', async ({
    page,
  }) => {
    await page.goto('/debug-replay')

    // Click the first row (the prompt cell is a stable click target).
    await page.getByText('Why is my latest deploy stuck on staging? Need a quick triage.').click()

    // Detail panel appears with the field list.
    await expect(page.getByText('상세', { exact: true })).toBeVisible()
    await expect(page.getByText('a1b2c3d4e5f6')).toBeVisible()
    await expect(page.getByText('Too many requests in the last minute')).toBeVisible()
  })

  test('shows the empty state when no captures exist', async ({ page }) => {
    await page.route('**/api/admin/debug/replay**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

    await page.goto('/debug-replay')

    await expect(page.getByText('캡처된 실패 요청이 없습니다')).toBeVisible()
  })
})
