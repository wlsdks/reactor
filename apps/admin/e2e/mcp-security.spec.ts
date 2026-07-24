import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/auth/login',
  '/api/auth/me',
  '/api/mcp/security',
  '/api/mcp/servers',
]

function buildSecurityState() {
  return {
    effective: {
      allowedServerNames: ['atlassian'],
      maxToolOutputLength: 250000,
      createdAt: 1710000000000,
      updatedAt: 1710003600000,
    },
    stored: {
      allowedServerNames: ['atlassian'],
      maxToolOutputLength: 250000,
      createdAt: 1710000000000,
      updatedAt: 1710000000000,
    },
    configDefault: {
      allowedServerNames: ['atlassian', 'swagger'],
      maxToolOutputLength: 50000,
      createdAt: 1710000000000,
      updatedAt: 1710000000000,
    },
  }
}

test.describe('/mcp-security operator console', () => {
  test('shows a recovery runbook when the contract returns 404 on first load', async ({ page }) => {
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
            paths: CAPABILITY_PATHS,
          }),
        })
        return
      }
      if (requestUrl.pathname === '/api/mcp/security') {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Not found' }),
        })
        return
      }
      if (requestUrl.pathname === '/api/mcp/servers') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: paths,
        timestamp: Date.now(),
      }))
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

    await page.goto('/mcp-security')

    await expect(page.getByRole('heading', { name: 'MCP 서버' })).toBeVisible()
    await expect(page.getByText('등록된 MCP 서버 없음')).toBeVisible()
  })

  test('redirects to mcp-servers and renders server list when data loads', async ({ page }) => {
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
            paths: CAPABILITY_PATHS,
          }),
        })
        return
      }
      if (requestUrl.pathname === '/api/mcp/security' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(buildSecurityState()),
        })
        return
      }
      if (requestUrl.pathname === '/api/mcp/servers') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: '1', name: 'atlassian', description: null, transportType: 'HTTP', autoConnect: true, status: 'CONNECTED', toolCount: 12, createdAt: 1, updatedAt: 1 },
            { id: '2', name: 'swagger', description: null, transportType: 'HTTP', autoConnect: false, status: 'DISCONNECTED', toolCount: 3, createdAt: 1, updatedAt: 1 },
          ]),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/mcp-security')

    // /mcp-security redirects to /mcp-servers
    await expect(page).toHaveURL(/\/mcp-servers/)
    await expect(page.getByRole('heading', { name: 'MCP 서버' })).toBeVisible()
    await expect(page.getByText('atlassian')).toBeVisible()
    await expect(page.getByText('swagger')).toBeVisible()
    await expect(page.locator('.badge').getByText('DISCONNECTED')).toBeVisible()
  })
})
