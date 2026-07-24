import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/auth/login',
  '/api/auth/me',
]

test.describe('/scheduler operator console', () => {
  test('shows a recovery runbook when the scheduler contract is unavailable', async ({ page }) => {
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

      const pathname = requestUrl.pathname
      if (pathname.includes('/auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: CAPABILITY_PATHS }),
        })
        return
      }
      if (pathname === '/api/scheduler/jobs') {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Not found' }),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/scheduler')

    await expect(page.getByRole('heading', { name: '스케줄러 준비 상태' })).toBeVisible()
    await expect(page.getByText(/스케줄러 엔드포인트 호출이 실패했어요.*이 페이지의 데이터가 오래됐을 수 있어요/)).toBeVisible()
    await expect(page.getByRole('heading', { name: '문제 해결 가이드' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Integrations 열기' })).toBeVisible()
  })

  test('shows attention jobs and operator note for failing automation', async ({ page }) => {
    await page.addInitScript((token: string) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: [
          '/api/admin/capabilities',
          '/api/auth/login',
          '/api/auth/me',
          '/api/scheduler/jobs',
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

      const pathname = requestUrl.pathname
      const method = route.request().method()

      if (pathname.includes('/auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            generatedAt: Date.now(),
            source: 'playwright-mock',
            paths: ['/api/admin/capabilities', '/api/auth/login', '/api/auth/me', '/api/scheduler/jobs'],
          }),
        })
        return
      }
      if (pathname === '/api/scheduler/jobs' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'job-1',
              name: 'Nightly sync',
              description: 'Synchronize records',
              cronExpression: '0 * * * *',
              timezone: 'Asia/Seoul',
              jobType: 'AGENT',
              mcpServerName: null,
              toolName: null,
              toolArguments: {},
              agentPrompt: 'Sync records',
              personaId: null,
              agentSystemPrompt: null,
              agentModel: 'gpt-5',
              agentMaxToolCalls: 5,
              slackChannelId: null,
              teamsWebhookUrl: null,
              retryOnFailure: false,
              maxRetryCount: 0,
              executionTimeoutMs: 120000,
              enabled: true,
              lastRunAt: 1710000000000,
              lastStatus: 'FAILED',
              lastResult: null,
              lastResultPreview: null,
              lastFailureReason: 'queue offline',
              createdAt: 1710000000000,
              updatedAt: 1710000000000,
            },
            {
              id: 'job-2',
              name: 'Healthy digest',
              description: 'Daily summary',
              cronExpression: '0 9 * * *',
              timezone: 'Asia/Seoul',
              jobType: 'AGENT',
              mcpServerName: null,
              toolName: null,
              toolArguments: {},
              agentPrompt: 'Summarize operations',
              personaId: null,
              agentSystemPrompt: null,
              agentModel: 'gpt-5',
              agentMaxToolCalls: 5,
              slackChannelId: null,
              teamsWebhookUrl: null,
              retryOnFailure: true,
              maxRetryCount: 1,
              executionTimeoutMs: 120000,
              enabled: true,
              lastRunAt: 1710003600000,
              lastStatus: 'SUCCESS',
              lastResult: 'ok',
              lastResultPreview: 'ok',
              lastFailureReason: null,
              createdAt: 1710000000000,
              updatedAt: 1710003600000,
            },
          ]),
        })
        return
      }
      if (pathname.includes('/api/scheduler/jobs/job-1/executions') && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'exec-1',
              jobId: 'job-1',
              jobName: 'Nightly sync',
              status: 'FAILED',
              result: 'queue offline',
              resultPreview: 'queue offline',
              failureReason: 'queue offline',
              durationMs: 1200,
              dryRun: false,
              startedAt: 1710000000000,
              completedAt: 1710000001200,
            },
          ]),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/scheduler')

    await expect(page.getByText('주의 큐')).toBeVisible()
    await expect(page.locator('.split-left table tbody tr')).toHaveCount(2)
    await page.getByRole('button', { name: '재시도 없음' }).click()
    await expect(page.locator('.split-left table tbody tr')).toHaveCount(1)
    await expect(page.getByRole('strong').filter({ hasText: 'Nightly sync' })).toBeVisible()
    await page.getByRole('button', { name: '작업 상세 열기' }).click()
    await expect(page.getByText('관리자 메모')).toBeVisible()
    await expect(page.locator('.split-right').getByText(/수동 복구/)).toBeVisible()
    await expect(page.getByText('실행 상세')).toBeVisible()
  })

  test('blocks saving MCP tool jobs when tool arguments are not a JSON object', async ({ page }) => {
    await page.addInitScript((token: string) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: [
          '/api/admin/capabilities',
          '/api/auth/login',
          '/api/auth/me',
          '/api/scheduler/jobs',
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

      const pathname = requestUrl.pathname
      const method = route.request().method()

      if (pathname.includes('/auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            generatedAt: Date.now(),
            source: 'playwright-mock',
            paths: ['/api/admin/capabilities', '/api/auth/login', '/api/auth/me', '/api/scheduler/jobs'],
          }),
        })
        return
      }
      if (pathname === '/api/scheduler/jobs' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
        return
      }
      if (pathname === '/api/scheduler/jobs' && method === 'POST') {
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'job-created' }),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/scheduler')

    await page.getByRole('button', { name: '작업 생성' }).click()
    const modal = page.locator('.modal')
    await modal.locator('select').first().selectOption('MCP_TOOL')
    await modal.locator('xpath=.//label[normalize-space()="이름"]/following-sibling::input').fill('Tool sync')
    await modal.locator('xpath=.//label[normalize-space()="MCP 서버"]/following-sibling::input').fill('atlassian')
    await modal.locator('xpath=.//label[normalize-space()="도구 이름"]/following-sibling::input').fill('jira_search')
    await modal.locator('xpath=.//label[normalize-space()="도구 인수"]/following-sibling::textarea').fill('[]')
    await modal.getByRole('button', { name: '저장' }).click()

    await expect(modal.locator('.alert.alert-error')).toContainText('도구 인수는 JSON object여야 합니다')
  })
})
