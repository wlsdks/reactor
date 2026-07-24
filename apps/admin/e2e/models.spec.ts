import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/models',
  '/api/admin/platform/pricing',
  '/api/admin/platform/alerts/rules',
  '/api/admin/platform/alerts',
  '/api/auth/login',
  '/api/auth/me',
]

const MODELS = [
  {
    name: 'gpt-5',
    provider: 'OpenAI',
    inputPricePerMillionTokens: 5,
    outputPricePerMillionTokens: 15,
    contextLength: 128000,
    isDefault: true,
  },
  {
    name: 'claude-sonnet-4',
    provider: 'Anthropic',
    inputPricePerMillionTokens: 3,
    outputPricePerMillionTokens: 12,
    contextLength: 200000,
    isDefault: false,
  },
]

test.describe('/models registry', () => {
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
      if (pathname === '/api/admin/models') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MODELS),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

    await page.goto('/models')
  })

  test('renders the registry tab with model rows and the default badge', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'AI 모델' })).toBeVisible()

    // Both rows surface their model name in the data table; the default model
    // additionally appears inside the "기본 모델" stat card, so use first().
    await expect(page.getByText('gpt-5', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('claude-sonnet-4')).toBeVisible()

    // The default model row should carry the green "기본" badge.
    await expect(page.locator('table tbody').getByText('기본', { exact: true })).toBeVisible()
  })

  test('shows the total models stat card and surfaces the default model', async ({ page }) => {
    // StatCard labels render uppercase per CLAUDE.md convention; match by class.
    const stats = page.locator('.stat-card')
    await expect(stats).toHaveCount(2)

    // The "기본 모델" stat card should contain the default model name.
    await expect(page.locator('.stat-card', { hasText: '기본 모델' })).toContainText('gpt-5')
  })

  test('exposes the registry / pricing / alerts tabs', async ({ page }) => {
    await expect(page.getByRole('tab', { name: '레지스트리' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '가격' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '알림' })).toBeVisible()
  })
})
