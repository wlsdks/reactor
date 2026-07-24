import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/settings',
  '/api/admin/retention',
  '/api/auth/login',
  '/api/auth/me',
]

const SETTINGS = [
  {
    key: 'reactor.feature.alpha',
    value: 'true',
    type: 'BOOLEAN',
    description: 'Enable alpha feature flag',
    updatedAt: '2026-04-01T00:00:00Z',
  },
  {
    key: 'reactor.timeout.ms',
    value: '5000',
    type: 'INTEGER',
    description: 'Default timeout in milliseconds',
    updatedAt: '2026-04-02T00:00:00Z',
  },
]

test.describe('/settings platform settings', () => {
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
      const method = route.request().method()

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
      if (pathname === '/api/admin/settings' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(SETTINGS),
        })
        return
      }
      if (pathname === '/api/admin/retention' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            sessionRetentionDays: 90,
            conversationRetentionDays: 365,
            auditRetentionDays: 730,
            metricRetentionDays: 180,
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

    await page.goto('/settings')
  })

  test('renders the settings table with the platform admin rows', async ({ page }) => {
    await expect(page.getByRole('heading', { level: 1, name: '플랫폼 정책' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '런타임 설정' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText('reactor.feature.alpha')).toBeVisible()
    await expect(page.getByText('reactor.timeout.ms')).toBeVisible()
  })

  test('opens data retention in the same platform policy workspace', async ({ page }) => {
    await page.getByRole('tab', { name: '데이터 보존' }).click()

    await expect(page).toHaveURL('/settings?tab=retention')
    await expect(page.getByRole('heading', { level: 2, name: '데이터 보존 정책' })).toBeVisible()
    await expect(page.getByLabel('세션 보존 기간')).toHaveValue('90')
  })

  test('redirects the legacy retention route to the canonical retention tab', async ({ page }) => {
    await page.goto('/retention')

    await expect(page).toHaveURL('/settings?tab=retention')
    await expect(page.getByRole('tab', { name: '데이터 보존' })).toHaveAttribute('aria-selected', 'true')
  })

  test('filters the settings list by key search', async ({ page }) => {
    const search = page.getByPlaceholder('키 이름으로 검색...')
    await expect(search).toBeVisible()

    await search.fill('timeout')

    await expect(page.getByText('reactor.timeout.ms')).toBeVisible()
    await expect(page.getByText('reactor.feature.alpha')).toBeHidden()
  })

  test('exposes the cache refresh action button', async ({ page }) => {
    await expect(page.getByRole('button', { name: '캐시 새로고침' })).toBeVisible()
  })
})
