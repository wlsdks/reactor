import { expect, test, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const DEFAULT_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/admin/input-guard/pipeline',
  '/api/admin/input-guard/rules',
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

const sampleRule = {
  id: 'rule-1',
  name: 'My PII rule',
  pattern: '\\d{3}-\\d{2}-\\d{4}',
  patternType: 'regex',
  action: 'block',
  priority: 10,
  category: 'pii',
  description: 'Blocks SSN-like patterns.',
  enabled: true,
  createdAt: '2026-04-01T09:00:00Z',
  updatedAt: '2026-04-20T14:30:00Z',
}

interface RuleDetailRouteOptions {
  capabilityPaths?: string[]
  detailResponse?: { status?: number; body: string }
}

async function setupInputGuardPage(page: Page, options: RuleDetailRouteOptions = {}) {
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

    // Stub the global dashboard call so GlobalStatusStrip in the header can mount.
    if (pathname === '/api/ops/dashboard' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          ragEnabled: true,
          mcp: { total: 0, statusCounts: { CONNECTED: 0, DISCONNECTED: 0 } },
          scheduler: { totalJobs: 0, enabledJobs: 0, runningJobs: 0, failedJobs: 0, attentionBacklog: 0, agentJobs: 0 },
          recentSchedulerExecutions: [],
          approvals: { pendingCount: 0, oldestPendingAge: null, attention: [] },
          metrics: {},
          retention: { ttlDays: 30 },
          recentTrustEvents: [],
          employeeValue: { topMissingQueries: [] },
        }),
      })
      return
    }

    if (pathname === '/api/admin/input-guard/pipeline' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          { name: 'rate-limit', order: 1, enabled: true, className: 'com.reactor.guard.RateLimitStage', runtimeOverride: false },
        ]),
      })
      return
    }

    if (pathname === '/api/admin/input-guard/rules' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ rules: [sampleRule], total: 1 }),
      })
      return
    }

    if (pathname.startsWith('/api/admin/input-guard/rules/') && method === 'GET') {
      const detailResponse = options.detailResponse ?? { body: JSON.stringify(sampleRule) }
      await route.fulfill({
        status: detailResponse.status ?? 200,
        contentType: 'application/json',
        body: detailResponse.body,
      })
      return
    }

    if (pathname.startsWith('/api/admin/input-guard/rules/') && method === 'OPTIONS') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
      return
    }

    // Fallback
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/input-guard')
}

test.describe('input-guard — rule detail', () => {
  test('View detail opens read-mode modal with Edit toggle', async ({ page }) => {
    await setupInputGuardPage(page)

    // Switch to the Rules tab
    await page.getByRole('tab', { name: '규칙' }).click()

    const viewBtn = page.getByRole('button', { name: /My PII rule 규칙 상세 보기/ })
    await expect(viewBtn).toBeVisible()
    await viewBtn.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('My PII rule')).toBeVisible()

    // Edit toggle visible in read-mode
    const editToggle = dialog.getByRole('button', { name: '편집' })
    await expect(editToggle).toBeVisible()

    // Toggle to edit mode → form input appears
    await editToggle.click()
    await expect(dialog.getByLabel('이름', { exact: false })).toBeVisible()
  })

  test('shows "rule no longer exists" when detail fetch returns 404', async ({ page }) => {
    await setupInputGuardPage(page, {
      detailResponse: { status: 404, body: '{}' },
    })

    await page.getByRole('tab', { name: '규칙' }).click()

    const viewBtn = page.getByRole('button', { name: /My PII rule 규칙 상세 보기/ })
    await viewBtn.click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('이 규칙은 더 이상 존재하지 않습니다.')).toBeVisible()
  })
})
