import { expect, test } from '@playwright/test'

import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/metrics/latency/summary',
  '/api/admin/tools/accuracy',
  '/api/admin/tools/stats',
  '/api/auth/login',
  '/api/auth/me',
  '/api/ops/dashboard',
]

// Minimal dashboard payload — GlobalStatusStrip in the global header reads
// `data.mcp.total`, `data.approvals.pendingCount`, etc., so the strip needs
// a properly shaped object even when the page under test does not.
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

const MOCK_STATS = {
  total: 100,
  accuracy: 0.85,
  byOutcome: { ok: 80, error: 15, timeout: 5 },
  byServer: { 'mcp-a': 63, 'mcp-b': 37 },
  byTool: [
    { tool: 'web.search', server: 'mcp-a', outcome: 'ok', count: 40 },
    { tool: 'web.search', server: 'mcp-a', outcome: 'error', count: 10 },
    { tool: 'web.search', server: 'mcp-b', outcome: 'ok', count: 20 },
    { tool: 'fs.read', server: 'mcp-b', outcome: 'ok', count: 30 },
  ],
}

const MOCK_ACCURACY = {
  total: 100,
  ok: 85,
  accuracy: 0.85,
  invalidCallRate: 0.02,
  timeoutRate: 0.05,
  notFoundRate: 0.08,
}

const MOCK_LATENCY_SUMMARY = { p50: 100, p95: 250, p99: 400 }

test.describe('/performance — Tools segment', () => {
  test.beforeEach(async ({ page }) => {
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
      if (pathname === '/api/admin/tools/stats') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_STATS),
        })
        return
      }
      if (pathname === '/api/admin/tools/accuracy') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_ACCURACY),
        })
        return
      }
      if (pathname === '/api/admin/metrics/latency/summary') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_LATENCY_SUMMARY),
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

      // Default — keep unrelated requests quiet with empty arrays so unrelated
      // route gates don't reject the page. GlobalStatusStrip reads from the
      // dashboard payload above; everything else stays empty.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

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
  })

  test('switching to the Tools tab shows aggregated stat cards and ranking', async ({
    page,
  }) => {
    await page.goto('/performance')

    // Default tab is Latency — switch to Tools.
    await page.getByRole('tab', { name: '도구' }).click()

    // Total calls hero card.
    await expect(page.getByText('100', { exact: true }).first()).toBeVisible()
    // Success rate card (80%).
    await expect(page.getByText('80%').first()).toBeVisible()
    // Ranking surfaces both aggregated tools.
    await expect(page.getByText('web.search')).toBeVisible()
    await expect(page.getByText('fs.read')).toBeVisible()
    // URL deep-links the segment.
    await expect(page).toHaveURL(/seg=tools/)
  })

  test('Tools segment View-traces row action links to /traces with tool filter', async ({
    page,
  }) => {
    await page.goto('/performance?seg=tools')

    const link = page.getByRole('link', { name: '트레이스 보기' }).first()
    await expect(link).toHaveAttribute('href', /\/traces\?tool=web\.search/)
  })

  test('?seg=tools deep-link selects the Tools tab on mount', async ({
    page,
  }) => {
    await page.goto('/performance?seg=tools')
    const toolsTab = page.getByRole('tab', { name: '도구' })
    await expect(toolsTab).toHaveAttribute('aria-selected', 'true')
  })
})
