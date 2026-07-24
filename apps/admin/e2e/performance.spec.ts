import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/metrics/latency/summary',
  '/api/admin/metrics/latency/timeseries',
  '/api/admin/tools/accuracy',
  '/api/admin/tools/stats',
  '/api/auth/login',
  '/api/auth/me',
  '/api/ops/dashboard',
]

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

const MOCK_LATENCY_SUMMARY = { p50: 120, p95: 480, p99: 1250 }

const MOCK_LATENCY_TIMESERIES = Array.from({ length: 12 }, (_, i) => ({
  time: new Date(Date.UTC(2026, 3, 25, i * 2, 0, 0)).toISOString(),
  avgMs: 100 + i * 5,
  p95Ms: 250 + i * 10,
  count: 50 + i,
}))

test.describe('/performance — Latency segment', () => {
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
      if (pathname === '/api/admin/metrics/latency/summary') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_LATENCY_SUMMARY),
        })
        return
      }
      if (pathname === '/api/admin/metrics/latency/timeseries') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_LATENCY_TIMESERIES),
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

  test('renders the page header, segment tabs, and the three percentile stat cards', async ({
    page,
  }) => {
    await page.goto('/performance')

    await expect(page.getByRole('heading', { name: '성능' })).toBeVisible()

    // Two top-level segment tabs (Latency / Tools) plus the inner sub-tabs
    // (Latency / Conversations) — assert the two segment tabs by role+name.
    await expect(page.getByRole('tab', { name: '지연 시간' }).first()).toBeVisible()
    await expect(page.getByRole('tab', { name: '도구' })).toBeVisible()

    // Three latency stat cards rendered after the summary query resolves.
    // Values are formatted via formatMs(): <1000ms → "Xms", ≥1000ms → "X.Xs".
    await expect(page.locator('.stat-card', { hasText: '중앙값' })).toContainText('120ms')
    await expect(page.locator('.stat-card', { hasText: '상위 5%' })).toContainText('480ms')
    await expect(page.locator('.stat-card', { hasText: '상위 1%' })).toContainText('1.3s')
  })

  test('renders the latency-over-time chart heading after data loads', async ({ page }) => {
    await page.goto('/performance')

    // Wait for latency summary cards before checking the chart heading —
    // ensures the lazy PercentileChart bundle has had time to mount.
    await expect(page.locator('.stat-card', { hasText: '중앙값' })).toContainText('120ms')

    await expect(
      page.getByRole('heading', { name: '시간별 지연 시간' }),
    ).toBeVisible({ timeout: 10000 })
  })

  test('exposes the days selector with the documented period options', async ({ page }) => {
    await page.goto('/performance')

    // Days selector is labeled by `latencyPage.daysLabel` via aria-label.
    const daysSelector = page.getByLabel('기간 (일)')
    await expect(daysSelector).toBeVisible()

    // 4 documented options: 1 / 3 / 7 / 30 days.
    await expect(daysSelector.locator('option')).toHaveCount(4)
  })

  test('?seg=tools deep-link selects the Tools segment on mount', async ({ page }) => {
    await page.goto('/performance?seg=tools')

    // The outer Tabs component exposes both segment buttons as role=tab; the
    // selected one carries aria-selected=true.
    const toolsTab = page.getByRole('tab', { name: '도구' })
    await expect(toolsTab).toHaveAttribute('aria-selected', 'true')
  })
})
