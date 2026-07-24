import { expect, test, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const DEFAULT_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/admin/input-guard/pipeline',
  '/api/admin/input-guard/rules/{id}',
  '/api/approvals',
  '/api/auth/login',
  '/api/auth/me',
  '/api/auth/register',
  '/api/chat',
  '/api/documents',
  '/api/feedback',
  '/api/intents',
  '/api/mcp/servers',
  '/api/ops/dashboard',
  '/api/output-guard/rules',
  '/api/personas',
  '/api/prompt-lab/experiments',
  '/api/prompt-templates',
  '/api/rag-ingestion/candidates',
  '/api/scheduler/jobs',
  '/api/sessions',
  '/api/tool-policy',
]

interface OutputGuardRouteOptions {
  capabilityPaths?: string[]
  handleApi: (pathname: string, method: string) => { status?: number; body: string }
}

async function setupOutputGuardPage(page: Page, options: OutputGuardRouteOptions) {
  const capabilityPaths = options.capabilityPaths ?? DEFAULT_CAPABILITY_PATHS

  await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: paths,
      timestamp: Date.now(),
    }))
  }, { paths: capabilityPaths, token: MOCK_TOKEN })

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const pathname = requestUrl.pathname
    const method = route.request().method()

    if (pathname.includes('/auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
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
          paths: capabilityPaths,
        }),
      })
      return
    }

    const response = options.handleApi(pathname, method)
    await route.fulfill({
      status: response.status ?? 200,
      contentType: 'application/json',
      body: response.body,
    })
  })

  await page.goto('/output-guard')
}

test.describe('/output-guard operator console', () => {
  test('shows capability diagnostics when the output-guard endpoint is unavailable', async ({ page }) => {
    await setupOutputGuardPage(page, {
      capabilityPaths: DEFAULT_CAPABILITY_PATHS.filter((path) => path !== '/api/output-guard/rules'),
      handleApi: () => ({ body: '[]' }),
    })

    // /output-guard redirects to /safety-rules?tab=output-guard
    // The safety-rules route requires both /api/output-guard/rules AND /api/tool-policy
    await expect(page.getByRole('heading', { name: '안전 규칙' })).toBeVisible()
    await expect(page.getByText('이 기능은 현재 서버에서 사용할 수 없어요. 관리자에게 문의해 주세요.')).toBeVisible()

    await page.getByText('기술 정보 보기').click()

    await expect(page.getByText('/api/output-guard/rules')).toBeVisible()
    await expect(page.getByText('감지 방식: manifest')).toBeVisible()
  })

  test('renders operator summary, tolerates missing audits, and shows simulation feedback', async ({ page }) => {
    const rules = [
      {
        id: 'rule-1',
        name: 'Credit card blocker',
        pattern: '\\b\\d{4}-\\d{4}-\\d{4}-\\d{4}\\b',
        action: 'REJECT',
        priority: 10,
        enabled: true,
        createdAt: 1710000000000,
        updatedAt: 1710003600000,
      },
      {
        id: 'rule-2',
        name: 'Phone masker',
        pattern: '\\b\\d{3}-\\d{3}-\\d{4}\\b',
        action: 'MASK',
        priority: 100,
        enabled: false,
        createdAt: 1710000000000,
        updatedAt: 1710007200000,
      },
    ]
    let simulationCalls = 0

    await setupOutputGuardPage(page, {
      handleApi: (pathname, method) => {
        if (pathname === '/api/output-guard/rules' && method === 'GET') {
          return { body: JSON.stringify(rules) }
        }
        if (pathname.includes('/api/output-guard/rules/audits') && method === 'GET') {
          return { status: 503, body: JSON.stringify({ error: 'audit feed unavailable' }) }
        }
        if (pathname === '/api/output-guard/rules/simulate' && method === 'POST') {
          simulationCalls += 1
          return {
            body: JSON.stringify({
              originalContent: 'card number: 4111-1111-1111-1111',
              resultContent: 'card number: [redacted]',
              blocked: true,
              modified: true,
              blockedByRuleId: 'rule-1',
              blockedByRuleName: 'Credit card blocker',
              matchedRules: [
                {
                  ruleId: 'rule-1',
                  ruleName: 'Credit card blocker',
                  action: 'REJECT',
                  priority: 10,
                },
              ],
              invalidRules: [
                {
                  ruleId: 'rule-bad',
                  ruleName: 'Broken token detector',
                  reason: 'Unterminated group',
                },
              ],
            }),
          }
        }

        return { body: '[]' }
      },
    })

    await expect(page.getByRole('heading', { name: '응답 필터' })).toBeVisible()
    await expect(page.getByText(/규칙 수: 2/)).toBeVisible()
    await expect(page.getByText(/감사 수: 0/)).toBeVisible()
    await expect(page.getByText('전체 규칙')).toBeVisible()
    await expect(page.getByText('오류')).toBeVisible({ timeout: 30000 })
    await expect(page.getByText('감사 채널')).toBeVisible()

    await page.getByText('Phone masker').click()
    const detailPanel = page.locator('.split-right')
    await expect(detailPanel).toContainText('동작:')
    await expect(detailPanel).toContainText('마스킹')
    await expect(detailPanel).toContainText('우선순위: 100')

    await page.locator('textarea').first().fill('card number: 4111-1111-1111-1111')
    // Close the rule detail panel to prevent it from intercepting pointer events
    await page.getByRole('button', { name: '닫기' }).click()
    // Scroll to the simulation form and interact via JS to bypass sticky footer interception
    await page.evaluate(() => {
      const checkbox = document.getElementById('include-disabled') as HTMLInputElement | null
      if (checkbox && !checkbox.checked) checkbox.click()
    })
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'))
      const runBtn = buttons.find(b => b.textContent?.trim() === '시뮬레이션 실행')
      if (runBtn) runBtn.click()
    })

    await expect.poll(() => simulationCalls).toBe(1)
    await expect(page.getByText('시뮬레이션 결과')).toBeVisible()
    await expect(page.getByText('차단 여부: 예')).toBeVisible()
    await expect(page.getByText('수정 여부: 예')).toBeVisible()
    await expect(page.getByText('매칭 규칙 수: 1')).toBeVisible()
    await expect(page.getByText('오류 규칙 수: 1')).toBeVisible()
    await expect(page.getByText('차단 규칙: Credit card blocker')).toBeVisible()
    await expect(page.getByText('매칭 규칙 스택')).toBeVisible()
    await expect(page.getByText('Credit card blocker · 차단 · P10')).toBeVisible()
    await expect(page.getByText('오류 규칙 상세')).toBeVisible()
    await expect(page.getByText('Broken token detector')).toBeVisible()
    await expect(page.getByText('Unterminated group')).toBeVisible()
    await expect(page.getByText('card number: [redacted]')).toBeVisible()
  })
})
