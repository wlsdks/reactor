import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/intents',
  '/api/auth/login',
  '/api/auth/me',
]

const INTENTS = [
  {
    name: 'support_request',
    description: 'Customer support intake intent',
    examples: ['help me reset my password', 'I cannot log in'],
    keywords: ['help', 'support', 'reset'],
    profile: {},
    enabled: true,
    createdAt: 1714000000000,
    updatedAt: 1714003600000,
  },
  {
    name: 'sales_inquiry',
    description: 'Pre-sales product question intent',
    examples: ['what is the price'],
    keywords: ['price', 'pricing'],
    profile: {},
    enabled: false,
    createdAt: 1714007200000,
    updatedAt: 1714010800000,
  },
]

test.describe('/intents catalogue', () => {
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
      if (pathname === '/api/intents') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(INTENTS),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

    await page.goto('/intents')
  })

  test('renders the intents page header and the two seeded rows', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '인텐트 규칙' })).toBeVisible()

    // Both intent names are rendered as <code> in the name column.
    await expect(page.getByText('support_request')).toBeVisible()
    await expect(page.getByText('sales_inquiry')).toBeVisible()
  })

  test('shows the total / enabled stat cards reflecting the seeded intents', async ({ page }) => {
    // StatCard labels render uppercase per CLAUDE.md convention; match by class.
    const stats = page.locator('.stat-card')
    await expect(stats).toHaveCount(2)

    // The "전체 규칙" card reflects the two seeded intents.
    await expect(page.locator('.stat-card', { hasText: '전체 규칙' })).toContainText('2')
    // The "활성" card reflects the single enabled intent.
    await expect(page.locator('.stat-card', { hasText: '활성' })).toContainText('1')
  })

  test('exposes the new-intent action button in the page header', async ({ page }) => {
    await expect(page.getByRole('button', { name: '새 인텐트' })).toBeVisible()
  })
})
