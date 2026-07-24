import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/input-guard/pipeline',
  '/api/admin/input-guard/rules/{id}',
  '/api/output-guard/rules',
  '/api/output-guard/rules/audits',
  '/api/tool-policy',
  '/api/auth/login',
  '/api/auth/me',
]

// Generate ten output-guard rules so the table reflects a realistic operator
// workload and the totalRules stat card surfaces a recognizable count.
const OUTPUT_GUARD_RULES = Array.from({ length: 10 }, (_, idx) => {
  const i = idx + 1
  return {
    id: `rule-${i}`,
    name: `Filter Rule ${i}`,
    pattern: `pattern_${i}`,
    action: i % 2 === 0 ? 'MASK' : 'REJECT',
    priority: i,
    enabled: i !== 5, // one disabled row exercises the status badge variant
    createdAt: 1714000000000 + i * 1000,
    updatedAt: 1714003600000 + i * 1000,
  }
})

test.describe('/safety-rules tabs', () => {
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
      if (pathname === '/api/output-guard/rules') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(OUTPUT_GUARD_RULES),
        })
        return
      }
      if (pathname === '/api/output-guard/rules/audits') {
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

    await page.goto('/safety-rules?tab=output-guard')
  })

  test('exposes the three addressable safety boundaries', async ({ page }) => {
    const inputGuardTab = page.getByRole('tab', { name: '입력 가드' })
    const outputGuardTab = page.getByRole('tab', { name: '응답 필터' })
    const toolPolicyTab = page.getByRole('tab', { name: '도구 정책' })

    await expect(inputGuardTab).toBeVisible()
    await expect(outputGuardTab).toBeVisible()
    await expect(toolPolicyTab).toBeVisible()
    await expect(outputGuardTab).toHaveAttribute('aria-selected', 'true')

    await toolPolicyTab.click()
    await expect(page).toHaveURL(/\/safety-rules\?tab=tool-policy$/)
    await expect(toolPolicyTab).toHaveAttribute('aria-selected', 'true')
  })

  test('starts the safety workflow at input guard', async ({ page }) => {
    await page.goto('/safety-rules')

    await expect(page.getByRole('heading', { level: 1, name: '안전 정책' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '입력 가드' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('heading', { level: 2, name: '입력 가드' })).toBeVisible()
  })

  test('keeps the workspace available when input guard APIs are not advertised', async ({ page }) => {
    await page.addInitScript(({ paths }: { paths: string[] }) => {
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: paths.filter((path) => !path.includes('/input-guard/')),
        timestamp: Date.now(),
      }))
    }, { paths: CAPABILITY_PATHS })

    await page.goto('/safety-rules')

    await expect(page.getByRole('heading', { level: 1, name: '안전 정책' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '입력 가드' })).toHaveAttribute('aria-selected', 'true')
  })

  test('renders all 10 seeded response-filter rules in the table', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '응답 필터' })).toBeVisible()

    // The data table exposes one <tr> per rule under tbody.
    await expect(page.locator('table tbody tr')).toHaveCount(10)

    // Spot-check the first and last rule names so we know the seeded payload
    // round-trips through the rendering pipeline.
    await expect(page.getByText('Filter Rule 1', { exact: true })).toBeVisible()
    await expect(page.getByText('Filter Rule 10', { exact: true })).toBeVisible()
  })

  test('renders the response-filter stat cards reflecting seeded counts', async ({ page }) => {
    // Four stat cards: total / active / reject / audit channel.
    await expect(page.locator('.stat-card')).toHaveCount(4)

    await expect(page.locator('.stat-card', { hasText: '전체 규칙' })).toContainText('10')
    // 9 active (one disabled). The "차단 규칙" stat counts ENABLED REJECT rules
    // only (see `summarizeOutputGuardOps`). Of REJECT rules at i=1,3,5,7,9 the
    // disabled rule i=5 is excluded, leaving 4.
    await expect(page.locator('.stat-card', { hasText: '활성 규칙' })).toContainText('9')
    await expect(page.locator('.stat-card', { hasText: '차단 규칙' })).toContainText('4')
  })
})
