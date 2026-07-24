import { expect, test, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

async function setupAndNavigate(page: Page, path = '/issues') {
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits',
        '/api/admin/capabilities',
        '/api/approvals',
        '/api/auth/login',
        '/api/auth/me',
        '/api/error-report',
        '/api/mcp/servers',
        '/api/ops/dashboard',
        '/api/ops/metrics/names',
        '/api/output-guard/rules',
        '/api/scheduler/jobs',
        '/api/slack/commands',
        '/api/slack/events',
        '/api/tool-policy',
        '/api/mcp/security',
      ],
      timestamp: Date.now(),
    }))
  }, MOCK_TOKEN)

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url())
    if (!url.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    if (url.pathname === '/api/auth/me') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (url.pathname === '/api/auth/login') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
      return
    }
    if (url.pathname === '/api/admin/capabilities') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          source: 'playwright-mock',
          paths: [
            '/api/admin/capabilities',
            '/api/mcp/servers',
            '/api/approvals',
            '/api/output-guard/rules',
            '/api/admin/audits',
            '/api/error-report',
            '/api/ops/dashboard',
            '/api/ops/metrics/names',
            '/api/scheduler/jobs',
            '/api/slack/commands',
            '/api/slack/events',
            '/api/tool-policy',
            '/api/mcp/security',
          ],
        }),
      })
      return
    }
    if (url.pathname === '/api/ops/dashboard') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          ragEnabled: false,
          mcp: { total: 0, statusCounts: {} },
          scheduler: { totalJobs: 0, enabledJobs: 0, runningJobs: 0, failedJobs: 0, attentionBacklog: 0, agentJobs: 0 },
          recentSchedulerExecutions: [],
          approvals: { pendingCount: 0 },
          responseTrust: { unverifiedResponses: 0, outputGuardRejected: 0, outputGuardModified: 0, boundaryFailures: 0 },
          employeeValue: {
            observedResponses: 0,
            groundedResponses: 0,
            groundedRatePercent: 0,
            blockedResponses: 0,
            interactiveResponses: 0,
            scheduledResponses: 0,
            answerModes: {},
            channels: [],
            lanes: [],
            toolFamilies: [],
            topMissingQueries: [],
          },
          recentTrustEvents: [],
          metrics: [],
        }),
      })
      return
    }
    if (url.pathname === '/api/mcp/servers') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    if (
      (url.pathname === '/api/slack/commands' ||
        url.pathname === '/api/slack/events' ||
        url.pathname === '/api/error-report') &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({ status: 405, contentType: 'application/json', body: JSON.stringify({ error: 'Method not allowed' }) })
      return
    }
    if (url.pathname === '/api/mcp/security' || url.pathname === '/api/tool-policy') {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'HTTP 404' }) })
      return
    }
    if (url.pathname === '/api/output-guard/rules') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }
    if (url.pathname === '/api/output-guard/rules/audits') {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'socket hang up' }) })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto(path)
  await page.waitForSelector('.sidenav .sidenav-item', { timeout: 15_000 })
}

test.describe('/issues operator console', () => {
  test('aggregates cross-console issues and keeps service relationships list-first', async ({ page }) => {
    await setupAndNavigate(page)

    await expect(page.getByText('전체 모듈의 시스템 상태 및 이슈 추적')).toBeVisible()
    // The page uses a topology map with severity buttons
    await expect(page.getByRole('button', { name: /전체/ }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /심각/ }).first()).toBeVisible()
    await expect(page.getByRole('button', { name: /경고/ }).first()).toBeVisible()

    // Click Critical filter and verify issue items appear
    await page.getByRole('button', { name: /심각/ }).first().click()
    // /tool-policy 404 → degradedRoutes path → control-plane issue with title
    // 'Tool Policy' (integrationsPage.probes.toolPolicy is intentionally
    // English-cased even in KO i18n, per ko.json:2034). Tolerant regex
    // also matches '도구 정책' if the label is ever localized.
    await expect(page.getByRole('button', { name: /Tool Policy|도구 정책/ })).toBeVisible()
  })

  test('opens a still relationship map only when the operator asks for it', async ({ page }) => {
    await setupAndNavigate(page)

    await expect(page.getByRole('tab', { name: /list|목록/i })).toHaveAttribute('aria-selected', 'true')
    await expect(page.locator('.system-topology')).toHaveCount(0)

    await page.getByRole('tab', { name: /graph|시각화/i }).click()
    await expect(page.locator('.system-topology')).toBeVisible()
    await expect(page.locator('.topo-rf-center__orbit')).toHaveCount(0)
    await expect(page.locator('.topo-rf-edge__flow')).toHaveCount(0)
  })
})
