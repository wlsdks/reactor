import { expect, test, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const POST_ONLY_PROBE_PATHS = new Set([
  '/api/slack/commands',
  '/api/slack/events',
  '/api/error-report',
])

const BASE_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/approvals',
  '/api/auth/login',
  '/api/auth/me',
  '/api/error-report',
  '/api/mcp/security',
  '/api/mcp/servers',
  '/api/ops/dashboard',
  '/api/ops/metrics/names',
  '/api/proactive-channels',
  '/api/scheduler/jobs',
  '/api/slack/commands',
  '/api/slack/events',
]

async function seedAdminSession(page: Page, capabilityPaths: string[]) {
  await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: paths,
      timestamp: Date.now(),
    }))
  }, { paths: capabilityPaths, token: MOCK_TOKEN })
}

async function setupRecoveryPage(page: Page) {
  await seedAdminSession(page, BASE_CAPABILITY_PATHS)

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    if (requestUrl.pathname === '/api/auth/me') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (requestUrl.pathname === '/api/auth/login') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
      })
      return
    }
    if (requestUrl.pathname === '/api/admin/capabilities') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          source: 'playwright-mock',
          paths: BASE_CAPABILITY_PATHS,
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
    if (requestUrl.pathname === '/api/mcp/security') {
      await route.abort('failed')
      return
    }
    if (POST_ONLY_PROBE_PATHS.has(requestUrl.pathname) && route.request().method() === 'GET') {
      await route.fulfill({
        status: 405,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Method not allowed' }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    })
  })

  await page.goto('/integrations')
}

async function setupManualDiagnosticsPage(page: Page) {
  const capabilityPaths = [...BASE_CAPABILITY_PATHS, '/api/tool-policy']
  const observed = {
    command: { headers: {} as Record<string, string>, body: '' },
    event: { headers: {} as Record<string, string>, body: '' },
    error: { headers: {} as Record<string, string>, body: '' },
  }

  await seedAdminSession(page, capabilityPaths)

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    if (requestUrl.pathname === '/api/auth/me') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (requestUrl.pathname === '/api/auth/login') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
      })
      return
    }
    if (requestUrl.pathname === '/api/admin/capabilities') {
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
    if (requestUrl.pathname === '/api/tool-policy') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          configEnabled: true,
          dynamicEnabled: false,
          effective: {
            writeToolNames: [],
            denyWriteChannels: [],
          },
        }),
      })
      return
    }
    if (requestUrl.pathname === '/api/mcp/security') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          effective: {
            allowedServerNames: ['swagger', 'atlassian'],
            maxToolOutputLength: 1024,
          },
        }),
      })
      return
    }
    if (POST_ONLY_PROBE_PATHS.has(requestUrl.pathname) && route.request().method() === 'GET') {
      await route.fulfill({
        status: 405,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Method not allowed' }),
      })
      return
    }
    if (requestUrl.pathname === '/api/slack/commands' && route.request().method() === 'POST') {
      observed.command = {
        headers: route.request().headers(),
        body: route.request().postData() ?? '',
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, mode: 'command', echoed: 'slash-command' }),
      })
      return
    }
    if (requestUrl.pathname === '/api/slack/events' && route.request().method() === 'POST') {
      observed.event = {
        headers: route.request().headers(),
        body: route.request().postData() ?? '',
      }
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, mode: 'event', accepted: true }),
      })
      return
    }
    if (requestUrl.pathname === '/api/error-report' && route.request().method() === 'POST') {
      observed.error = {
        headers: route.request().headers(),
        body: route.request().postData() ?? '',
      }
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, mode: 'error', alert: 'queued' }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    })
  })

  await page.goto('/integrations')
  return observed
}

function formControl(page: Page, label: string, role: 'textbox' = 'textbox') {
  return page.locator('.form-group').filter({ hasText: label }).getByRole(role)
}

test.describe('/integrations contract recovery', () => {
  test('surfaces missing tool-policy and broken mcp security contracts before deeper testing', async ({ page }) => {
    await setupRecoveryPage(page)

    await expect(page.getByRole('heading', { name: '엔드포인트 복구 콘솔' })).toBeVisible()
    await expect(page.getByText('MCP 보안 정책').first()).toBeVisible()
    // transportFailure recovery surfaces probeDirect / inspectProxy / reopenConsole
    // (controlPlaneRecovery.ts:101-104 — checkManifest is intentionally skipped here)
    await expect(page.getByText('엔드포인트 직접 probe').first()).toBeVisible()
    await expect(page.getByText('backend / proxy 로그 확인').first()).toBeVisible()
    await expect(page.getByRole('link', { name: '복구 콘솔 열기' }).first()).toBeVisible()
  })

  test('submits command, event, and error-report diagnostics through the frontend', async ({ page }) => {
    const observed = await setupManualDiagnosticsPage(page)

    await formControl(page, '명령 텍스트').fill('Run the integration smoke')
    await page.getByRole('button', { name: '명령 테스트 전송' }).click()
    await expect(page.locator('.split-right pre')).toContainText('"mode": "command"')
    expect(observed.command.headers.authorization).toBe(`Bearer ${MOCK_TOKEN}`)
    expect(observed.command.headers['content-type']).toContain('application/x-www-form-urlencoded')
    expect(observed.command.body).toContain('command=%2Fask')
    expect(observed.command.body).toContain('text=Run+the+integration+smoke')

    await page.getByRole('tab', { name: 'Slack 이벤트' }).click()
    await formControl(page, '이벤트 Payload JSON').fill(JSON.stringify({
      type: 'app_mention',
      event: { type: 'app_mention', text: '@bot run smoke' },
    }, null, 2))
    await page.getByRole('button', { name: '이벤트 테스트 전송' }).click()
    await expect(page.locator('.split-right pre')).toContainText('"mode": "event"')
    expect(observed.event.headers.authorization).toBe(`Bearer ${MOCK_TOKEN}`)
    expect(observed.event.headers['content-type']).toContain('application/json')
    expect(JSON.parse(observed.event.body)).toMatchObject({
      type: 'app_mention',
      event: { type: 'app_mention', text: '@bot run smoke' },
    })

    await page.getByRole('tab', { name: '에러 리포팅' }).click()
    await formControl(page, '스택 트레이스').fill('java.lang.RuntimeException: integration smoke')
    await page.getByRole('button', { name: '에러 리포트 테스트 전송' }).click()
    await expect(page.locator('.split-right pre')).toContainText('"mode": "error"')
    expect(observed.error.headers.authorization).toBe(`Bearer ${MOCK_TOKEN}`)
    expect(observed.error.headers['content-type']).toContain('application/json')
    expect(JSON.parse(observed.error.body)).toMatchObject({
      stackTrace: 'java.lang.RuntimeException: integration smoke',
      serviceName: 'reactor-admin',
      repoSlug: 'reactor/admin',
      slackChannel: 'C0123456789',
      environment: 'production',
      metadata: { host: 'admin-dev-01' },
    })
  })
})
