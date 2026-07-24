import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_ENDPOINTS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/admin/slack/channels',
  '/api/admin/slack-bots',
  '/api/admin/slack-activity/channels',
  '/api/approvals',
  '/api/auth/login',
  '/api/auth/me',
  '/api/error-report',
  '/api/mcp/security',
  '/api/mcp/servers',
  '/api/ops/dashboard',
  '/api/proactive-channels',
  '/api/scheduler/jobs',
  '/api/slack/commands',
  '/api/slack/events',
]

interface MockChannel {
  channelId: string
  channelName?: string
  enabled: boolean
  autoReplyMode: 'OFF' | 'AUTO' | 'SUGGEST'
  confidenceThreshold: number
  daysBack: number
  reIngestIntervalHours: number
  createdAt: number
  updatedAt: number
  lastIngestedAt?: number
}

const INITIAL_CHANNEL: MockChannel = {
  channelId: 'C-FAQ-DEMO',
  channelName: 'general',
  enabled: true,
  autoReplyMode: 'AUTO',
  confidenceThreshold: 0.7,
  daysBack: 30,
  reIngestIntervalHours: 24,
  createdAt: 1700000000000,
  updatedAt: 1700100000000,
  lastIngestedAt: 1700200000000,
}

const ORG_STATS = {
  totalChannels: 1,
  totalQueries7d: 42,
  avgHitRate7d: 0.66,
}

const SCHEDULER_HEALTH = { enabled: true, status: 'OK' }

const CHANNEL_STATS = (channelId: string) => ({
  channelId,
  totalQueries: 12,
  matchedQueries: 9,
  avgConfidence: 0.84,
  hitRate: 0.75,
  windowDays: 7,
})

const PROBE_RESULT = (query: string) => ({
  query,
  matches: [
    { faqId: 'F-1', title: 'Reset password', confidence: 0.92 },
    { faqId: 'F-2', title: 'Forgot password', body: 'Use the reset flow', confidence: 0.71 },
  ],
})

async function setupSlackFaqPage(page: Page) {
  // Mutable channel registry per test for create / delete flows.
  const channels = new Map<string, MockChannel>()
  channels.set(INITIAL_CHANNEL.channelId, { ...INITIAL_CHANNEL })

  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem(
      'reactor-admin-feature-availability-v2',
      JSON.stringify({
        mode: 'manifest',
        endpoints: [
          '/api/admin/audits',
          '/api/admin/capabilities',
          '/api/admin/slack/channels',
          '/api/admin/slack-bots',
          '/api/admin/slack-activity/channels',
          '/api/approvals',
          '/api/auth/login',
          '/api/auth/me',
          '/api/error-report',
          '/api/mcp/security',
          '/api/mcp/servers',
          '/api/ops/dashboard',
          '/api/proactive-channels',
          '/api/scheduler/jobs',
          '/api/slack/commands',
          '/api/slack/events',
        ],
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
    const path = requestUrl.pathname
    const method = route.request().method()

    if (path === '/api/auth/me') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_USER),
      })
      return
    }
    if (path === '/api/auth/login') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
      })
      return
    }
    if (path === '/api/admin/capabilities') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          source: 'playwright-mock',
          paths: CAPABILITY_ENDPOINTS,
        }),
      })
      return
    }

    // GlobalStatusStrip dereferences `data.mcp.total` directly — empty `[]`
    // payload would crash the layout. Provide a minimal valid dashboard.
    if (path === '/api/ops/dashboard') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          generatedAt: Date.now(),
          ragEnabled: false,
          mcp: { total: 0, statusCounts: {} },
          scheduler: { totalJobs: 0, totalExecutions: 0 },
          approvals: { pendingCount: 0 },
        }),
      })
      return
    }

    // ── Slack FAQ endpoints ───────────────────────────────────────────
    if (path === '/api/admin/slack/channels/faq' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([...channels.values()]),
      })
      return
    }
    if (path === '/api/admin/slack/channels/faq/scheduler/health' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SCHEDULER_HEALTH),
      })
      return
    }
    if (path === '/api/admin/slack/channels/faq/stats' && method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ...ORG_STATS, totalChannels: channels.size }),
      })
      return
    }
    if (path === '/api/admin/slack/channels/faq' && method === 'POST') {
      const body = JSON.parse((await route.request().postData()) ?? '{}') as Partial<MockChannel>
      const created: MockChannel = {
        channelId: body.channelId ?? 'C-NEW',
        channelName: body.channelName,
        enabled: body.enabled ?? true,
        autoReplyMode: body.autoReplyMode ?? 'OFF',
        confidenceThreshold: body.confidenceThreshold ?? 0.7,
        daysBack: body.daysBack ?? 30,
        reIngestIntervalHours: body.reIngestIntervalHours ?? 24,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      }
      channels.set(created.channelId, created)
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(created),
      })
      return
    }

    // /api/admin/slack/channels/faq/<channelId>...
    const channelMatch = path.match(/^\/api\/admin\/slack\/channels\/faq\/([^/]+)(\/(.*))?$/)
    if (channelMatch) {
      const channelId = decodeURIComponent(channelMatch[1])
      const sub = channelMatch[3] ?? ''
      const ch = channels.get(channelId)

      if (sub === '' && method === 'GET') {
        if (!ch) {
          await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
          return
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(ch),
        })
        return
      }
      if (sub === '' && method === 'PATCH') {
        if (!ch) {
          await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
          return
        }
        const body = JSON.parse((await route.request().postData()) ?? '{}') as Partial<MockChannel>
        const updated = { ...ch, ...body, updatedAt: Date.now() }
        channels.set(channelId, updated)
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(updated),
        })
        return
      }
      if (sub === '' && method === 'DELETE') {
        channels.delete(channelId)
        await route.fulfill({ status: 204, body: '' })
        return
      }
      if (sub === 'stats' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(CHANNEL_STATS(channelId)),
        })
        return
      }
      if (sub === 'events' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: 'ev-1',
              ts: 1700300000000,
              userId: 'U-001',
              query: 'how to reset password',
              matchedFaqId: 'F-1',
              confidence: 0.92,
              outcome: 'MATCH',
            },
          ]),
        })
        return
      }
      if (sub === 'feedback' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
        return
      }
      if (sub === 'ingest' && method === 'POST') {
        await route.fulfill({ status: 202, body: '' })
        return
      }
      if (sub === 'probe' && method === 'POST') {
        const body = JSON.parse((await route.request().postData()) ?? '{}') as { query?: string }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(PROBE_RESULT(body.query ?? '')),
        })
        return
      }
      if (sub === 'dry-run' && method === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            decision: 'WOULD_REPLY',
            reason: 'High confidence match',
            match: { faqId: 'F-1', title: 'Reset password', confidence: 0.92 },
          }),
        })
        return
      }
    }

    // Default: empty payload for any other admin probe.
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/integrations')
  // Activate the FAQ tab.
  await page.getByRole('tab', { name: 'Slack FAQ' }).click()
}

test.describe('/integrations Slack FAQ tab', () => {
  test('renders org overview with stat cards when no channel selected', async ({ page }) => {
    await setupSlackFaqPage(page)
    // No channel selected by default — org overview should appear.
    await expect(page.getByTestId('slack-faq-org-overview')).toBeVisible()
    await expect(page.locator('.stat-card-value').filter({ hasText: '1' }).first()).toBeVisible()
  })

  test('selecting a channel reveals the detail pane with all 7 sections', async ({ page }) => {
    await setupSlackFaqPage(page)
    await page.getByTestId('faq-channel-row-C-FAQ-DEMO').click()
    await expect(page.getByTestId('faq-detail-pane')).toBeVisible()
    // Expand the probe section to confirm orchestrator wiring; default-open
    // sections should already be visible.
    await expect(page.getByText('개요').first()).toBeVisible()
    await expect(page.getByText('최근 이벤트').first()).toBeVisible()
    await expect(page.getByText('피드백').first()).toBeVisible()
    await expect(page.getByText('탐색 쿼리').first()).toBeVisible()
    await expect(page.getByText('Dry-run').first()).toBeVisible()
    await expect(page.getByText('재수집').first()).toBeVisible()
    await expect(page.getByText('위험 구역').first()).toBeVisible()
  })

  test('runs a probe and shows ranked matches', async ({ page }) => {
    await setupSlackFaqPage(page)
    await page.getByTestId('faq-channel-row-C-FAQ-DEMO').click()
    await page.getByText('탐색 쿼리').first().click()
    const queryInput = page.locator('#faq-probe-query')
    await queryInput.fill('reset password')
    await page.getByRole('button', { name: '탐색 실행' }).click()
    await expect(page.getByText('Reset password').first()).toBeVisible()
  })

  test('triggers re-index without error', async ({ page }) => {
    await setupSlackFaqPage(page)
    await page.getByTestId('faq-channel-row-C-FAQ-DEMO').click()
    // Use exact match so we only target the "재수집" section header — the
    // open Overview section also contains "재수집 주기(시간)" which would
    // otherwise match the substring search and resolve the click to a non
    // -interactive <dt> element instead of the collapsible header.
    const reindexHeader = page
      .locator('button.collapsible-header')
      .filter({ has: page.getByText('재수집', { exact: true }) })
    await reindexHeader.click()
    await expect(reindexHeader).toHaveAttribute('aria-expanded', 'true')
    await page.getByTestId('faq-reindex-btn').click()
    // Mocked 202 — no error toast surface; the button should be re-enabled.
    await expect(page.getByTestId('faq-reindex-btn')).toBeEnabled({ timeout: 5000 })
  })

  test('deletes channel with type-to-confirm and clears selection', async ({ page }) => {
    await setupSlackFaqPage(page)
    await page.getByTestId('faq-channel-row-C-FAQ-DEMO').click()
    await page.getByText('위험 구역').first().click()
    await page.getByTestId('faq-danger-delete-btn').click()
    // ConfirmDialog with type-to-confirm — type the channel ID exactly.
    const confirmInput = page.locator('input[type="text"]').last()
    await confirmInput.fill('C-FAQ-DEMO')
    await page.getByRole('button', { name: '확인', exact: true }).click()
    // Channel disappears from left rail and detail pane closes.
    await expect(page.getByTestId('faq-channel-row-C-FAQ-DEMO')).not.toBeVisible({ timeout: 5000 })
  })
})
