import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/platform/tenants',
  '/api/admin/platform/tenants/analytics',
  '/api/admin/tenant/overview',
  '/api/admin/tenant/usage',
  '/api/admin/tenant/quality',
  '/api/admin/tenant/tools',
  '/api/admin/tenant/cost',
  '/api/admin/tenant/slo',
  '/api/admin/tenant/alerts',
  '/api/admin/tenant/quota',
  '/api/auth/login',
  '/api/auth/me',
]

test.describe('/tenants console', () => {
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

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })
  })

  test('renders one owning header before the roster and operations tabs', async ({ page }) => {
    await page.goto('/tenants')

    await expect(page.getByRole('heading', { level: 1, name: '테넌트' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '테넌트 목록' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '선택 테넌트 운영' })).toBeVisible()

    const headingBox = await page.getByRole('heading', { level: 1, name: '테넌트' }).boundingBox()
    const tabsBox = await page.getByRole('tablist', { name: '테넌트 운영 워크스페이스' }).boundingBox()
    expect(headingBox?.y).toBeLessThan(tabsBox?.y ?? 0)
  })

  test('operations tab keeps the selected tenant in the URL and renders as an embedded section', async ({ page }) => {
    await page.goto('/tenants?tab=tenant&tenantId=tenant-42')

    await expect(page.getByRole('heading', { level: 1, name: '테넌트' })).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 2, name: '테넌트 운영' })).toBeVisible()
    await expect(page.getByLabel('테넌트 ID (X-Tenant-Id)')).toHaveValue('tenant-42')

    // The TenantAdminManager renders four empty-state panels until "테넌트 대시보드 로드" runs.
    await expect(page.getByText('개요 데이터 없음')).toBeVisible()
    await expect(page.getByText('사용량 데이터 없음')).toBeVisible()
    await expect(page.getByText('비용 데이터 없음')).toBeVisible()
    await expect(page.getByText('SLO 데이터 없음')).toBeVisible()

    await expect(page.getByRole('button', { name: '테넌트 대시보드 로드' })).toBeVisible()
  })
})
