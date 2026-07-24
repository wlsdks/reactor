import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const MOCK_CAPABILITY_PATHS = [
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
  '/api/error-report',
  '/api/feedback',
  '/api/intents',
  '/api/mcp/servers',
  '/api/ops/dashboard',
  '/api/ops/metrics/names',
  '/api/output-guard/rules',
  '/api/personas',
  '/api/proactive-channels',
  '/api/prompt-lab/experiments',
  '/api/prompt-templates',
  '/api/rag-ingestion/candidates',
  '/api/scheduler/jobs',
  '/api/sessions',
  '/api/slack/commands',
  '/api/slack/events',
  '/api/tool-policy',
]

async function setupGovernanceRecoveryPage(page: Page, path: string) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits', '/api/admin/capabilities', '/api/admin/input-guard/pipeline',
        '/api/admin/input-guard/rules/{id}', '/api/approvals', '/api/auth/login',
        '/api/auth/me', '/api/auth/register', '/api/chat', '/api/documents', '/api/error-report',
        '/api/feedback', '/api/intents', '/api/mcp/servers', '/api/ops/dashboard',
        '/api/ops/metrics/names', '/api/output-guard/rules', '/api/personas', '/api/proactive-channels',
        '/api/prompt-lab/experiments', '/api/prompt-templates', '/api/rag-ingestion/candidates',
        '/api/scheduler/jobs', '/api/sessions', '/api/slack/commands', '/api/slack/events', '/api/tool-policy',
      ],
      timestamp: Date.now(),
    }))
  }, MOCK_TOKEN)

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const url = requestUrl.toString()

    if (url.includes('/auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (url.includes('/auth/login')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
      })
      return
    }
    if (url.includes('/admin/capabilities')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          source: 'playwright-mock',
          paths: MOCK_CAPABILITY_PATHS,
        }),
      })
      return
    }
    if (requestUrl.pathname === '/api/tool-policy') {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Not found' }),
      })
      return
    }
    if (
      (requestUrl.pathname === '/api/slack/commands' ||
        requestUrl.pathname === '/api/slack/events' ||
        requestUrl.pathname === '/api/error-report') &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({
        status: 405,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Method not allowed' }),
      })
      return
    }
    if (requestUrl.pathname === '/api/mcp/security') {
      await route.abort('failed')
      return
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto(path)
}

test.describe('governance recovery console', () => {
  test('integrations page prioritizes policy and security recovery paths', async ({ page }) => {
    await setupGovernanceRecoveryPage(page, '/integrations')

    await expect(page.getByText('엔드포인트 복구 콘솔')).toBeVisible()
    await expect(page.getByText('MCP 보안 정책').first()).toBeVisible()
    await expect(page.getByText('엔드포인트 직접 probe').first()).toBeVisible()
    await expect(page.getByText('backend / proxy 로그 확인').first()).toBeVisible()
    await expect(page.getByText('엔드포인트 문제 해결 가이드')).toBeVisible()
  })

  test('tool policy page falls back to the recovery runbook when the endpoint returns 404', async ({ page }) => {
    await setupGovernanceRecoveryPage(page, '/tool-policy')

    await expect(page.getByText('도구 정책 준비도')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('정책 엔드포인트 오류')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('heading', { name: '문제 해결 가이드' })).toBeVisible()
    await expect(page.getByText('1. admin 엔드포인트 확인')).toBeVisible()
  })
})
