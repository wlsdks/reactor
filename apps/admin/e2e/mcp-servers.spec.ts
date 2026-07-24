import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const MOCK_CAPABILITY_PATHS = [
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

async function setupAuthenticatedMcpPage(
  page: Page,
  handleApi: (url: string, method: string) => { status?: number; body: string },
) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits', '/api/admin/capabilities', '/api/approvals', '/api/auth/login',
        '/api/auth/me', '/api/auth/register', '/api/chat', '/api/documents', '/api/feedback',
        '/api/intents', '/api/mcp/servers', '/api/ops/dashboard', '/api/output-guard/rules',
        '/api/personas', '/api/prompt-lab/experiments', '/api/prompt-templates',
        '/api/rag-ingestion/candidates', '/api/scheduler/jobs', '/api/sessions', '/api/tool-policy',
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

    const response = handleApi(requestUrl.pathname, method)
    await route.fulfill({
      status: response.status ?? 200,
      contentType: 'application/json',
      body: response.body,
    })
  })

  await page.goto('/mcp-servers')
  await expect(page.getByRole('heading', { name: 'MCP 서버' })).toBeVisible()
}

test.describe('/mcp-servers operator actions', () => {
  test('bulk reconnect shows fleet feedback after reconnecting disconnected servers', async ({ page }) => {
    const connectCalls: string[] = []
    const disconnectedServers = [
      {
        id: 'server-1',
        name: 'atlassian',
        description: 'Atlassian MCP',
        transportType: 'SSE',
        autoConnect: true,
        status: 'DISCONNECTED',
        toolCount: 12,
        createdAt: 1710000000000,
        updatedAt: 1710000000000,
      },
      {
        id: 'server-2',
        name: 'swagger',
        description: 'Swagger MCP',
        transportType: 'SSE',
        autoConnect: true,
        status: 'DISCONNECTED',
        toolCount: 4,
        createdAt: 1710000000000,
        updatedAt: 1710000000000,
      },
    ]
    const connectedServers = [
      {
        id: 'server-1',
        name: 'atlassian',
        description: 'Atlassian MCP',
        transportType: 'SSE',
        autoConnect: true,
        status: 'CONNECTED',
        toolCount: 12,
        createdAt: 1710000000000,
        updatedAt: 1710000000000,
      },
      {
        id: 'server-2',
        name: 'swagger',
        description: 'Swagger MCP',
        transportType: 'SSE',
        autoConnect: true,
        status: 'CONNECTED',
        toolCount: 4,
        createdAt: 1710000000000,
        updatedAt: 1710000000000,
      },
    ]

    await setupAuthenticatedMcpPage(page, (url, method) => {
      if (url.endsWith('/api/mcp/servers') && method === 'GET') {
        return {
          body: JSON.stringify(connectCalls.length === 2 ? connectedServers : disconnectedServers),
        }
      }

      if (url.endsWith('/api/mcp/servers/atlassian/connect') && method === 'POST') {
        connectCalls.push('atlassian')
        return { body: JSON.stringify({ status: 'CONNECTED', tools: [] }) }
      }

      if (url.endsWith('/api/mcp/servers/swagger/connect') && method === 'POST') {
        connectCalls.push('swagger')
        return { body: JSON.stringify({ status: 'CONNECTED', tools: [] }) }
      }

      return { body: '[]' }
    })

    await expect(page.getByRole('button', { name: '미연결 서버 전체 연결' })).toBeEnabled()
    await page.getByRole('button', { name: '미연결 서버 전체 연결' }).click()

    // Confirm the action in the confirmation dialog. Scope to the dialog so
    // we don't pick up the header HealthBadge ("상태 · 확인 중") that also
    // matches /확인/i.
    await page.getByRole('dialog').getByRole('button', { name: '확인', exact: true }).click()

    await expect.poll(() => connectCalls.join(',')).toBe('atlassian,swagger')
    await expect(page.getByText('2/2개 서버 연결 완료, 0개 실패')).toBeVisible()
  })

  test('navigates to server detail and runs readiness check', async ({ page }) => {
    let preflightCalls = 0

    await setupAuthenticatedMcpPage(page, (url, method) => {
      if (url.endsWith('/api/mcp/servers') && method === 'GET') {
        return {
          body: JSON.stringify([
            {
              id: 'server-1',
              name: 'swagger',
              description: 'Swagger MCP',
              transportType: 'SSE',
              autoConnect: true,
              status: 'CONNECTED',
              toolCount: 4,
              createdAt: 1710000000000,
              updatedAt: 1710000000000,
            },
          ]),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger') && method === 'GET') {
        return {
          body: JSON.stringify({
            id: 'server-1',
            name: 'swagger',
            description: 'Swagger MCP',
            transportType: 'SSE',
            config: { url: 'http://localhost:8081/sse' },
            version: '1.0.0',
            autoConnect: true,
            status: 'CONNECTED',
            tools: ['spec_list', 'catalog_refresh'],
            createdAt: 1710000000000,
            updatedAt: 1710000000000,
          }),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger/access-policy') && method === 'GET') {
        return {
          body: JSON.stringify({
            allowedJiraProjectKeys: [],
            allowedConfluenceSpaceKeys: [],
            allowedBitbucketRepositories: [],
            allowedSourceNames: ['payments'],
            allowPreviewReads: true,
            allowPreviewWrites: false,
            allowDirectUrlLoads: false,
            publishedOnly: true,
            policySource: 'dynamic',
            dynamicEnabled: true,
          }),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger/preflight') && method === 'GET') {
        preflightCalls += 1
        return {
          body: JSON.stringify({
            ok: true,
            readyForProduction: preflightCalls === 1,
            policySource: 'dynamic',
            checkedAt: '2026-03-10T09:00:00Z',
            kind: 'generic',
            summary: {
              passCount: preflightCalls === 1 ? 3 : 2,
              warnCount: preflightCalls === 1 ? 0 : 1,
              failCount: 0,
            },
            checks: preflightCalls === 1
              ? []
              : [{ name: 'source_sync', status: 'WARN', message: 'One source is stale.' }],
          }),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger/swagger/sources') && method === 'GET') {
        return { body: '[]' }
      }

      return { body: '[]' }
    })

    // Click the server row to navigate to detail page
    await page.getByText('swagger').first().click()
    await expect(page).toHaveURL(/\/mcp-servers\/swagger/)

    // The detail page shows a Readiness Check card with a "Run Check" button
    await expect(page.getByText('사전 점검')).toBeVisible()
    await page.getByRole('button', { name: '점검 실행' }).click()

    await expect.poll(() => preflightCalls).toBeGreaterThanOrEqual(1)
  })

  test('shows access policy details on server detail page', async ({ page }) => {
    await setupAuthenticatedMcpPage(page, (url, method) => {
      if (url.endsWith('/api/mcp/servers') && method === 'GET') {
        return {
          body: JSON.stringify([
            {
              id: 'server-1',
              name: 'swagger',
              description: 'Swagger MCP',
              transportType: 'SSE',
              autoConnect: true,
              status: 'CONNECTED',
              toolCount: 4,
              createdAt: 1710000000000,
              updatedAt: 1710000000000,
            },
          ]),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger') && method === 'GET') {
        return {
          body: JSON.stringify({
            id: 'server-1',
            name: 'swagger',
            description: 'Swagger MCP',
            transportType: 'SSE',
            config: { url: 'http://localhost:8081/sse' },
            version: '1.0.0',
            autoConnect: true,
            status: 'CONNECTED',
            tools: ['spec_list', 'catalog_refresh'],
            createdAt: 1710000000000,
            updatedAt: 1710000000000,
          }),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger/access-policy') && method === 'GET') {
        return {
          body: JSON.stringify({
            allowedJiraProjectKeys: [],
            allowedConfluenceSpaceKeys: [],
            allowedBitbucketRepositories: [],
            allowedSourceNames: ['payments', 'billing'],
            allowPreviewReads: true,
            allowPreviewWrites: true,
            allowDirectUrlLoads: false,
            publishedOnly: false,
            policySource: 'dynamic',
            dynamicEnabled: true,
            dynamicPolicy: {
              allowedJiraProjectKeys: [],
              allowedConfluenceSpaceKeys: [],
              allowedBitbucketRepositories: [],
              allowedSourceNames: ['payments'],
              allowPreviewReads: false,
              allowPreviewWrites: false,
              allowDirectUrlLoads: false,
              publishedOnly: true,
            },
          }),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger/preflight') && method === 'GET') {
        return {
          body: JSON.stringify({
            ok: true,
            readyForProduction: true,
            policySource: 'dynamic',
            checkedAt: '2026-03-10T09:00:00Z',
            kind: 'generic',
            summary: {
              passCount: 3,
              warnCount: 0,
              failCount: 0,
            },
            checks: [],
          }),
        }
      }

      if (url.endsWith('/api/mcp/servers/swagger/swagger/sources') && method === 'GET') {
        return { body: '[]' }
      }

      return { body: '[]' }
    })

    // Click the server row to navigate to detail page
    await page.getByText('swagger').first().click()
    await expect(page).toHaveURL(/\/mcp-servers\/swagger/)

    // Access Policy card is visible with policy details
    await expect(page.getByText('접근 정책')).toBeVisible()
    await expect(page.getByText('preview 범위 읽기 허용')).toBeVisible()
    await expect(page.getByText(/preview 쓰기 허용/)).toBeVisible()
  })
})
