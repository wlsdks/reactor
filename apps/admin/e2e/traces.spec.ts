import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/traces',
  '/api/auth/login',
  '/api/auth/me',
]

const TRACES = [
  {
    trace_id: 'trace-1',
    run_id: '11111111-aaaa-bbbb-cccc-1234567890ab',
    time: 1714000000000,
    success: true,
    total_duration_ms: 320,
    span_count: 4,
  },
  {
    trace_id: 'trace-2',
    run_id: '22222222-aaaa-bbbb-cccc-1234567890ab',
    time: 1714003600000,
    success: false,
    total_duration_ms: 1850,
    span_count: 6,
  },
  {
    trace_id: 'trace-3',
    run_id: '33333333-aaaa-bbbb-cccc-1234567890ab',
    time: 1714007200000,
    success: true,
    total_duration_ms: 540,
    span_count: 5,
  },
]

test.describe('/traces viewer', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem(
        'reactor-admin-feature-availability-v2',
        JSON.stringify({
          mode: 'manifest',
          endpoints: paths,
          timestamp: Date.now(),
        }),
      )
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url())
      if (!requestUrl.pathname.startsWith('/api/')) {
        await route.continue()
        return
      }

      const pathname = requestUrl.pathname

      if (pathname.includes('/auth/me')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USER),
        })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
        })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
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
      if (pathname === '/api/admin/traces') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(TRACES),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

    await page.goto('/traces')
  })

  test('renders the traces table with the mocked trace rows', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '실행 트레이스' })).toBeVisible()

    // Three trace rows should be rendered (header row excluded by tbody scope).
    await expect(page.locator('table tbody tr')).toHaveCount(3)
  })

  test('shows the four trace stat cards (total / error rate / avg / p95)', async ({ page }) => {
    const stats = page.locator('.stat-card')
    await expect(stats).toHaveCount(4)

    // The total trace stat card should reflect the mocked row count.
    await expect(page.locator('.stat-card', { hasText: '전체 트레이스' })).toContainText('3')
  })

  test('exposes the days and status filters', async ({ page }) => {
    await expect(page.getByLabel('기간 (일)')).toBeVisible()
    await expect(page.getByLabel('상태별 필터')).toBeVisible()
  })

  test('renders the DataTable export menu button', async ({ page }) => {
    // DataTable.exportable adds a CSV/JSON export trigger; copy lives in i18n.
    await expect(page.getByRole('button', { name: '내보내기' })).toBeVisible()
  })
})
