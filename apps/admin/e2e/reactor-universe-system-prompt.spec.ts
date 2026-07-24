import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

/* ------------------------------------------------------------------ */
/*  Shared mock data                                                   */
/* ------------------------------------------------------------------ */

const MOCK_AGENT_SPECS = [
  {
    id: 'spec-alpha',
    name: 'Alpha Agent',
    description: 'Alpha test agent',
    toolNames: ['tool_a', 'tool_b'],
    keywords: ['alpha', 'test'],
    systemPrompt: 'override',
    mode: 'REACT',
    enabled: true,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-10T00:00:00Z',
  },
]

const SYSTEM_PROMPT_BODY = 'You are a test agent. Be concise and helpful.'

/**
 * Counts the number of GETs to /api/admin/agent-specs/:id/system-prompt the
 * client has issued. The audit-pill / staleTime: Infinity contract requires
 * this counter to advance ONLY on first reveal and on each explicit Refresh
 * click — collapsing + re-expanding must NOT increment it.
 */
let systemPromptCallCount = 0

async function setupReactorUniversePage(page: Page) {
  systemPromptCallCount = 0

  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem(
      'reactor-admin-feature-availability-v2',
      JSON.stringify({
        mode: 'manifest',
        endpoints: ['/api/admin/agent-specs', '/api/admin/capabilities'],
        timestamp: Date.now(),
      }),
    )
  }, MOCK_TOKEN)

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const url = requestUrl.pathname
    const method = route.request().method()

    if (url.includes('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_USER),
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
          paths: ['/api/admin/agent-specs'],
        }),
      })
      return
    }

    if (url === '/api/admin/agent-specs' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_AGENT_SPECS),
      })
      return
    }

    // System-prompt endpoint — count every GET so the test can assert that
    // collapse + re-expand does not re-call it.
    if (
      url.startsWith('/api/admin/agent-specs/') &&
      url.endsWith('/system-prompt') &&
      method === 'GET'
    ) {
      systemPromptCallCount += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ systemPrompt: SYSTEM_PROMPT_BODY }),
      })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '[]',
    })
  })

  await page.goto('/reactor-universe')
  await expect(page.getByRole('heading', { name: 'Reactor Universe' })).toBeVisible({
    timeout: 15000,
  })
}

test.describe('/reactor-universe — system prompt reveal', () => {
  test('audit pill is visible inline on the toggle before the prompt is fetched', async ({ page }) => {
    await setupReactorUniversePage(page)

    // Open the edit modal on the only agent.
    // The agent-card edit button is no longer rendered with a title=
    // attribute (Tooltip primitive uses aria-describedby + portal). Match by
    // accessible name (aria-label) instead.
    await page.getByRole('button', { name: '수정', exact: true }).first().click()

    // Toggle and audit pill are present BEFORE expansion.
    await expect(
      page.getByRole('button', { name: /시스템 프롬프트 보기/ }),
    ).toBeVisible()
    await expect(page.getByText('감사 로그 기록됨')).toBeVisible()

    // No fetch should have happened yet.
    expect(systemPromptCallCount).toBe(0)
  })

  test('first expand fetches and renders the prompt; collapse + re-expand does NOT re-fetch', async ({
    page,
  }) => {
    await setupReactorUniversePage(page)

    // The agent-card edit button is no longer rendered with a title=
    // attribute (Tooltip primitive uses aria-describedby + portal). Match by
    // accessible name (aria-label) instead.
    await page.getByRole('button', { name: '수정', exact: true }).first().click()
    const toggle = page.getByRole('button', {
      name: /시스템 프롬프트 보기/,
    })

    // First expand → fetch.
    await toggle.click()
    await expect(page.getByText(SYSTEM_PROMPT_BODY)).toBeVisible()
    expect(systemPromptCallCount).toBe(1)

    // Region wraps the prompt body for keyboard scroll.
    const region = page.getByRole('region', { name: /시스템 프롬프트 본문/ })
    await expect(region).toHaveAttribute('tabindex', '0')

    // Collapse, then re-expand. Cache should serve, no new GET.
    await toggle.click()
    await toggle.click()
    await expect(page.getByText(SYSTEM_PROMPT_BODY)).toBeVisible()
    expect(systemPromptCallCount).toBe(1)
  })

  test('refresh button explicitly re-fetches and re-logs audit', async ({ page }) => {
    await setupReactorUniversePage(page)

    // The agent-card edit button is no longer rendered with a title=
    // attribute (Tooltip primitive uses aria-describedby + portal). Match by
    // accessible name (aria-label) instead.
    await page.getByRole('button', { name: '수정', exact: true }).first().click()
    await page
      .getByRole('button', { name: /시스템 프롬프트 보기/ })
      .click()
    await expect(page.getByText(SYSTEM_PROMPT_BODY)).toBeVisible()
    expect(systemPromptCallCount).toBe(1)

    await page
      .getByRole('button', { name: /최신 상태로 다시 불러오기/ })
      .click()

    await expect.poll(() => systemPromptCallCount).toBe(2)
  })
})
