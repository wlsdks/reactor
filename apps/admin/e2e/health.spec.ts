import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/platform/alerts/evaluate',
  '/api/admin/platform/cache/invalidate',
  '/api/admin/platform/health',
  '/api/admin/platform/tenants/analytics',
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

const MOCK_HEALTH = {
  services: [
    { name: 'postgres', status: 'UP' },
    { name: 'redis', status: 'UP' },
    { name: 'kafka', status: 'DEGRADED' },
  ],
  pipelineBufferUsage: 42,
  pipelineDropRate: 3,
  pipelineWriteLatencyMs: 18,
  activeAlerts: 7,
  cacheExactHits: 1234,
  cacheSemanticHits: 567,
  cacheMisses: 89,
}

test.describe('/health page', () => {
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
      if (pathname === '/api/admin/platform/health') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_HEALTH),
        })
        return
      }
      if (pathname === '/api/admin/platform/tenants/analytics') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: '[]',
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

  test('renders the page header and the three top stat cards', async ({ page }) => {
    await page.goto('/health')

    await expect(page.getByRole('heading', { name: '플랫폼 헬스' })).toBeVisible()

    // Stat cards are rendered via the shared StatCard component (uppercase
    // labels per CLAUDE.md convention). Match by class to avoid case issues.
    const stats = page.locator('.stat-card')
    await expect(stats).toHaveCount(3)

    // 상태 → "정상" (since `health` is non-null)
    await expect(page.locator('.stat-card', { hasText: '상태' })).toContainText('정상')
    // 활성 알림 → 7
    await expect(page.locator('.stat-card', { hasText: '활성 알림' })).toContainText('7')
    // 대기 용량 → "42%"
    await expect(page.locator('.stat-card', { hasText: '대기 용량' })).toContainText('42%')
  })

  test('renders the platform health panel with pipeline metrics and connected services', async ({
    page,
  }) => {
    await page.goto('/health')

    // Panel title.
    await expect(page.getByRole('heading', { name: '플랫폼 상태' })).toBeVisible()

    // Pipeline metrics (meta grid renders inline labels with values).
    await expect(page.getByText('쓰기 지연: 18ms')).toBeVisible()
    await expect(page.getByText('누락 건수: 3')).toBeVisible()
    await expect(page.getByText('정확 캐시 히트: 1234')).toBeVisible()
    await expect(page.getByText('유사 검색 캐시: 567')).toBeVisible()
    await expect(page.getByText('캐시 미스: 89')).toBeVisible()

    // Connected services list.
    await expect(page.getByRole('heading', { name: '연결된 서비스' })).toBeVisible()
    await expect(page.getByText('postgres:')).toBeVisible()
    await expect(page.getByText('redis:')).toBeVisible()
    await expect(page.getByText('kafka:')).toBeVisible()
  })

  test('exposes the evaluate-alerts and invalidate-cache action buttons', async ({ page }) => {
    await page.goto('/health')

    await expect(page.getByRole('heading', { name: '플랫폼 헬스' })).toBeVisible()

    await expect(page.getByRole('button', { name: '알림 평가' })).toBeVisible()
    await expect(page.getByRole('button', { name: '캐시 무효화' })).toBeVisible()
  })

  test('shows the empty-services state when no services are connected', async ({ page }) => {
    await page.route('**/api/admin/platform/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...MOCK_HEALTH, services: [] }),
      })
    })

    await page.goto('/health')

    await expect(page.getByText('연결된 서비스 없음')).toBeVisible()
  })
})
