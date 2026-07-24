import { expect, test, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const DEFAULT_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
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

interface AuditRouteOptions {
  capabilityPaths?: string[]
  handleApi: (url: string, method: string) => { status?: number; body: string }
}

async function setupAuditPage(page: Page, options: AuditRouteOptions) {
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

    const url = requestUrl.toString()
    const method = route.request().method()

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
          paths: capabilityPaths,
        }),
      })
      return
    }

    const response = options.handleApi(url, method)
    await route.fulfill({
      status: response.status ?? 200,
      contentType: 'application/json',
      body: response.body,
    })
  })

  await page.goto('/audit')
}

test.describe('/audit operator console', () => {
  test('shows capability diagnostics when the audit endpoint is unavailable', async ({ page }) => {
    await setupAuditPage(page, {
      capabilityPaths: DEFAULT_CAPABILITY_PATHS.filter((path) => path !== '/api/admin/audits'),
      handleApi: () => ({ body: '[]' }),
    })

    await expect(page.getByRole('heading', { name: '감사 로그', exact: true })).toBeVisible()
    await expect(page.getByText('이 기능은 현재 서버에서 사용할 수 없어요. 관리자에게 문의해 주세요.')).toBeVisible()

    await page.getByText('기술 정보 보기').click()

    await expect(page.getByText('/api/admin/audits')).toBeVisible()
    await expect(page.getByText('감지 방식: manifest')).toBeVisible()
  })

  test('renders rollback readiness and recovery routing from the latest audit rows', async ({ page }) => {
    const rows = [
      {
        id: 'audit-1',
        category: 'MCP_SERVER',
        action: 'UPDATE',
        actor: 'ops-admin',
        resourceType: 'server',
        resourceId: 'atlassian',
        detail: '{"before":{"status":"DISCONNECTED"},"after":{"status":"CONNECTED"},"changes":{"status":["DISCONNECTED","CONNECTED"]}}',
        createdAt: 1710000000000,
      },
      {
        id: 'audit-2',
        category: 'DASHBOARD',
        action: 'READ',
        actor: 'viewer',
        resourceType: null,
        resourceId: null,
        detail: 'opened dashboard',
        createdAt: 1710003600000,
      },
    ]

    await setupAuditPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/api/admin/audits') && method === 'GET') {
          return { body: JSON.stringify(rows) }
        }
        return { body: '[]' }
      },
    })

    await expect(page.getByRole('heading', { name: '감사 로그', exact: true })).toBeVisible()
    await expect(page.getByText('감사 로그 준비도')).toBeVisible()
    await expect(page.getByText('2행 중 2행 표시 중')).toBeVisible()

    await page.getByRole('button', { name: '위험 변경만' }).click()
    await expect(page.getByText('2행 중 1행 표시 중')).toBeVisible()
    await expect(page.getByText('MCP_SERVER', { exact: true })).toBeVisible()

    await page.getByText('MCP_SERVER', { exact: true }).click()

    await expect(page.getByText('이 변경은 관련 콘솔을 다시 열어 마지막 정상 상태와 비교하거나 재적용할 수 있을 만큼 문맥이 남아 있습니다.')).toBeVisible()
    await expect(page.getByText('복구 콘솔: MCP 서버 (/mcp-servers)').first()).toBeVisible()
    await expect(page.getByText('변경 필드')).toBeVisible()
    await expect(page.getByText('status', { exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: '복구 콘솔 열기' })).toHaveAttribute('href', '/mcp-servers')
  })

  test('shows recovery guidance when the audit feed itself fails', async ({ page }) => {
    await setupAuditPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/api/admin/audits') && method === 'GET') {
          // Use 500 (not 503) so ky does not retry internally
          return { status: 500, body: JSON.stringify({ error: 'audit feed unavailable' }) }
        }
        return { body: '[]' }
      },
    })

    await expect(page.getByRole('heading', { name: '감사 로그', exact: true })).toBeVisible()
    await expect(page.getByText(/감사 채널을 사용할 수 없어요.*변경 이력이 불완전할 수 있어요/)).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('문제 해결 가이드')).toBeVisible()
    await expect(page.getByText('1. 감사 endpoint 확인')).toBeVisible()
    await expect(page.getByText('감사 로그를 가져올 수 없어요')).toBeVisible()
  })
})
