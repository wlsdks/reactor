import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/auth/login',
  '/api/auth/me',
]

test.describe('/approvals operator console', () => {
  test('shows a recovery runbook when the approvals contract is unavailable', async ({ page }) => {
    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: paths,
        timestamp: Date.now(),
      }))
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

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
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (url.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: CAPABILITY_PATHS }),
        })
        return
      }
      if (requestUrl.pathname === '/api/approvals') {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Not found' }),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/approvals')

    await expect(page.getByRole('heading', { name: '승인 준비 상태' })).toBeVisible()
    await expect(page.getByText(/승인 엔드포인트 호출이 실패했어요.*이 페이지의 데이터가 오래됐을 수 있어요/)).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('heading', { name: '문제 해결 가이드' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Integrations 열기' })).toBeVisible()
  })

  test('shows stale approvals and operator note for timed-out requests', async ({ page }) => {
    await page.addInitScript((token: string) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: [
          '/api/admin/capabilities',
          '/api/auth/login',
          '/api/auth/me',
          '/api/approvals',
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
      const method = route.request().method()

      if (url.includes('/auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
        return
      }
      if (url.includes('/auth/login')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (url.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            generatedAt: Date.now(),
            source: 'playwright-mock',
            paths: ['/api/admin/capabilities', '/api/auth/login', '/api/auth/me', '/api/approvals'],
          }),
        })
        return
      }
      if (requestUrl.pathname === '/api/approvals' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'approval-1',
              runId: 'run-1',
              toolName: 'jira_write',
              arguments: { issueKey: 'OPS-1' },
              requestedAt: '2024-01-01T10:00:00Z',
              status: 'TIMED_OUT',
            },
            {
              id: 'approval-2',
              runId: 'run-2',
              toolName: 'confluence_write',
              arguments: { pageId: '123' },
              requestedAt: '2024-01-01T11:00:00Z',
              status: 'PENDING',
            },
          ]),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/approvals')

    await expect(page.getByText('주의 큐')).toBeVisible()
    await expect(page.locator('.split-left table tbody tr')).toHaveCount(2)
    await page.getByRole('button', { name: '만료' }).click()
    await expect(page.locator('.split-left table tbody tr')).toHaveCount(1)
    await expect(page.getByRole('cell', { name: 'jira_write' }).getByRole('code')).toBeVisible()
    await page.getByRole('button', { name: '상세 열기' }).first().click()
    await expect(page.getByText('관리자 메모')).toBeVisible()
    await expect(page.locator('.split-right').getByText(/timeout|pending/)).toBeVisible()
  })
})
