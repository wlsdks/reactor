import { test, expect, type Page } from '@playwright/test'
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

const NOW = Date.now()
const HOUR = 3_600_000
const DAY = 86_400_000

interface SetupOptions {
  capabilityPaths?: string[]
  handleApi: (url: string, method: string) => { status?: number; body: string }
}

async function setupFeedbackPage(page: Page, options: SetupOptions) {
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

  await page.goto('/feedback')
}

// ---- Mock data ----

function makeFeedbackList() {
  return [
    {
      feedbackId: 'fb-1',
      query: 'How do I create a new Jira ticket?',
      response: 'You can create a new Jira ticket using the jira_create_issue tool.',
      rating: 'thumbs_up',
      timestamp: new Date(NOW - 3 * HOUR).toISOString(),
      comment: 'Clear and helpful instructions',
      runId: 'run-101',
      intent: 'jira_create',
      domain: 'project_management',
      model: 'claude-sonnet-4-20250514',
      promptVersion: 2,
      toolsUsed: ['jira_create_issue'],
      durationMs: 1250,
      tags: ['jira', 'tools'],
      templateId: 'template-support',
      reviewStatus: 'inbox',
      reviewTags: [],
      reviewedBy: null,
      reviewedAt: null,
      reviewNote: null,
      version: 1,
      updatedAt: new Date(NOW - 3 * HOUR).toISOString(),
    },
    {
      feedbackId: 'fb-2',
      query: 'Summarize the latest sprint retrospective notes',
      response: 'The key takeaways from the sprint retrospective are: improved build times.',
      rating: 'thumbs_up',
      timestamp: new Date(NOW - 6 * HOUR).toISOString(),
      comment: null,
      runId: 'run-102',
      intent: 'content_summary',
      domain: 'knowledge_base',
      model: 'claude-sonnet-4-20250514',
      promptVersion: 2,
      toolsUsed: ['confluence_get_page'],
      durationMs: 3400,
      tags: ['confluence', 'summary'],
      templateId: 'template-support',
      reviewStatus: 'done',
      reviewTags: [],
      reviewedBy: 'admin@example.com',
      reviewedAt: new Date(NOW - 5 * HOUR).toISOString(),
      reviewNote: null,
      version: 1,
      updatedAt: new Date(NOW - 5 * HOUR).toISOString(),
    },
    {
      feedbackId: 'fb-3',
      query: 'What is the current deployment status?',
      response: 'I was unable to retrieve the deployment status.',
      rating: 'thumbs_down',
      timestamp: new Date(NOW - DAY).toISOString(),
      comment: 'Should have retried or shown cached data',
      runId: 'run-103',
      intent: 'status_check',
      domain: 'devops',
      model: 'claude-sonnet-4-20250514',
      promptVersion: 1,
      toolsUsed: [],
      durationMs: 820,
      tags: ['monitoring', 'error'],
      templateId: null,
      reviewStatus: 'inbox',
      reviewTags: [],
      reviewedBy: null,
      reviewedAt: null,
      reviewNote: null,
      version: 1,
      updatedAt: new Date(NOW - DAY).toISOString(),
    },
    {
      feedbackId: 'fb-4',
      query: 'Calculate the cost breakdown for tenant acme-corp',
      response: 'The cost breakdown for acme-corp this month: Total: $2,150.30',
      rating: 'thumbs_up',
      timestamp: new Date(NOW - 2 * DAY).toISOString(),
      comment: 'Accurate numbers',
      runId: 'run-104',
      intent: 'cost_analysis',
      domain: 'billing',
      model: 'claude-opus-4-20250514',
      promptVersion: 3,
      toolsUsed: ['billing_query', 'calculator'],
      durationMs: 5200,
      tags: ['billing', 'analytics'],
      templateId: 'template-sales',
      reviewStatus: 'done',
      reviewTags: [],
      reviewedBy: 'admin@example.com',
      reviewedAt: new Date(NOW - DAY).toISOString(),
      reviewNote: null,
      version: 1,
      updatedAt: new Date(NOW - DAY).toISOString(),
    },
  ]
}

function defaultFeedbackHandler(url: string, method: string): { status?: number; body: string } {
  const requestUrl = new URL(url)
  if (requestUrl.pathname === '/api/feedback/stats') {
    return {
      body: JSON.stringify({
        period: { from: new Date(NOW - 7 * DAY).toISOString(), to: new Date(NOW).toISOString() },
        total: 12,
        positive: 8,
        negative: 4,
        negativeThisPeriod: 4,
        previousPeriodNegative: 3,
        negativeChange: 1,
        positiveRate: 0.67,
        previousPeriodRate: 0.6,
        commentRate: 0.5,
        byDay: [],
        topNegativeDomains: [],
        topNegativeIntents: [],
        topNegativeTools: [],
        inboxCount: 4,
        doneCount: 8,
      }),
    }
  }
  if (requestUrl.pathname === '/api/feedback/unreviewed-count') {
    return { body: JSON.stringify({ count: 0 }) }
  }
  if (requestUrl.pathname === '/api/admin/followup-suggestions/stats') {
    return {
      body: JSON.stringify({
        windowHours: 24,
        totalImpressions: 0,
        totalClicks: 0,
        ctr: 0,
        byCategory: [],
      }),
    }
  }
  if (url.includes('/feedback/export') && method === 'GET') {
    return {
      body: JSON.stringify({
        version: 1,
        exportedAt: new Date().toISOString(),
        source: 'reactor-admin',
        items: makeFeedbackList(),
      }),
    }
  }
  if (url.match(/\/feedback\/[^/]+$/) && method === 'GET') {
    const match = url.match(/\/feedback\/([^/?]+)/)
    const id = match ? match[1] : 'fb-1'
    const entry = makeFeedbackList().find((f) => f.feedbackId === id)
    if (!entry) {
      return { status: 404, body: JSON.stringify({ error: 'Not found' }) }
    }
    return { body: JSON.stringify(entry) }
  }
  if (url.match(/\/feedback\/[^/]+$/) && method === 'DELETE') {
    return { body: JSON.stringify({}) }
  }
  if (url.includes('/feedback') && method === 'GET') {
    const urlObj = new URL(url)
    const rating = urlObj.searchParams.get('rating')
    let items = makeFeedbackList()
    if (rating) {
      items = items.filter((f) => f.rating === rating)
    }
    return {
      body: JSON.stringify({
        items,
        nextCursor: null,
        prevCursor: null,
        approximateTotal: items.length,
      }),
    }
  }
  return { body: '[]' }
}


test.describe('/feedback page', () => {
  test('loads and displays feedback list with stat cards', async ({ page }) => {
    await setupFeedbackPage(page, {
      handleApi: defaultFeedbackHandler,
    })

    // Page title
    await expect(page.getByRole('heading', { name: '피드백' })).toBeVisible()

    // Stat cards — Total Feedback, Positive, Negative (inside collapsed stats panel header surfaced text)
    await expect(page.getByText('전체 피드백')).toBeVisible()
    await expect(page.getByText('긍정', { exact: true })).toBeVisible()
    await expect(page.getByText('부정', { exact: true })).toBeVisible()

    // Table data — query text from mock entries visible
    await expect(page.getByText('How do I create a new Jira ticket?')).toBeVisible()
    await expect(page.getByText('What is the current deployment status?')).toBeVisible()

    // Rating badges (use .badge to avoid matching hidden <option> elements)
    await expect(page.locator('.badge', { hasText: 'thumbs_up' }).first()).toBeVisible()
    await expect(page.locator('.badge', { hasText: 'thumbs_down' }).first()).toBeVisible()
  })

  test('opens feedback detail panel when clicking a row', async ({ page }) => {
    await setupFeedbackPage(page, {
      handleApi: defaultFeedbackHandler,
    })

    // Click on feedback row (target the query cell text)
    await page.getByText('How do I create a new Jira ticket?').click()

    // Detail panel opens with query/response/metadata headings
    await expect(page.getByRole('heading', { name: '질의' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '응답' })).toBeVisible()
    await expect(page.getByRole('heading', { name: '메타데이터' })).toBeVisible()
    await expect(page.getByText('How do I create a new Jira ticket?').first()).toBeVisible()
  })

  test('filters feedback by rating', async ({ page }) => {
    let lastRatingFilter = ''

    await setupFeedbackPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/feedback') && method === 'GET' && !url.includes('/export') && !url.match(/\/feedback\/[^/]+$/) && !url.includes('/feedback/stats') && !url.includes('/feedback/unreviewed-count')) {
          const urlObj = new URL(url)
          lastRatingFilter = urlObj.searchParams.get('rating') ?? ''
          const rating = urlObj.searchParams.get('rating')
          let items = makeFeedbackList()
          if (rating) {
            items = items.filter((f) => f.rating === rating)
          }
          return {
            body: JSON.stringify({
              items,
              nextCursor: null,
              prevCursor: null,
              approximateTotal: items.length,
            }),
          }
        }
        return defaultFeedbackHandler(url, method)
      },
    })

    // Wait for initial load
    await expect(page.getByText('How do I create a new Jira ticket?')).toBeVisible()

    // Select thumbs_down filter
    await page.locator('select').first().selectOption('thumbs_down')

    await expect.poll(() => lastRatingFilter).toBe('thumbs_down')

    // Only thumbs_down entries visible (fb-3 query)
    await expect(page.getByText('What is the current deployment status?')).toBeVisible()
  })

  test('export button triggers download', async ({ page }) => {
    let exportCalled = false

    await setupFeedbackPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/feedback/export') && method === 'GET') {
          exportCalled = true
          return {
            body: JSON.stringify({
              version: 1,
              exportedAt: new Date().toISOString(),
              source: 'reactor-admin',
              items: makeFeedbackList(),
            }),
          }
        }
        return defaultFeedbackHandler(url, method)
      },
    })

    await expect(page.getByText('How do I create a new Jira ticket?')).toBeVisible()

    // Click the page-level export button. Scope to the page header — the
    // DataTable also exposes a "내보내기▾" menu trigger with the same
    // accessible name (chevron is aria-hidden), so we cannot rely on exact-name
    // matching alone.
    await page
      .locator('.page-header')
      .getByRole('button', { name: '내보내기' })
      .click()

    await expect.poll(() => exportCalled).toBe(true)
  })

  test('delete feedback shows confirmation and deletes', async ({ page }) => {
    let deleteCalled = false

    await setupFeedbackPage(page, {
      handleApi: (url, method) => {
        if (url.match(/\/feedback\/fb-1$/) && method === 'DELETE') {
          deleteCalled = true
          return { body: JSON.stringify({}) }
        }
        return defaultFeedbackHandler(url, method)
      },
    })

    // Open detail panel (click on query text in row)
    await page.getByText('How do I create a new Jira ticket?').click()
    await expect(page.getByRole('heading', { name: '질의' })).toBeVisible()

    // Click delete
    await page.getByRole('button', { name: '삭제' }).click()

    // Confirm dialog. Scope the click to the dialog so we don't pick up the
    // header HealthBadge button (aria-label "상태 · 확인 중") that also matches /확인/i.
    await expect(page.getByText('"fb-1" 피드백을 삭제할까요?')).toBeVisible()
    await page.getByRole('dialog').getByRole('button', { name: '확인', exact: true }).click()

    await expect.poll(() => deleteCalled).toBe(true)
  })

  test('shows empty state when no feedback data', async ({ page }) => {
    await setupFeedbackPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/feedback') && method === 'GET' && !url.includes('/export') && !url.includes('/feedback/stats') && !url.includes('/feedback/unreviewed-count') && !url.match(/\/feedback\/[^/]+$/)) {
          return {
            body: JSON.stringify({
              items: [],
              nextCursor: null,
              prevCursor: null,
              approximateTotal: 0,
            }),
          }
        }
        return defaultFeedbackHandler(url, method)
      },
    })

    await expect(page.getByText('피드백이 없습니다', { exact: true })).toBeVisible()
  })

  test('shows feature unavailable state when feedback endpoint is not in capabilities', async ({ page }) => {
    await setupFeedbackPage(page, {
      capabilityPaths: DEFAULT_CAPABILITY_PATHS.filter((p) => p !== '/api/feedback'),
      handleApi: defaultFeedbackHandler,
    })

    await expect(page.getByText('이 기능은 현재 서버에서 사용할 수 없어요. 관리자에게 문의해 주세요.')).toBeVisible()
  })

  test('shows error state with retry on API failure', async ({ page }) => {
    let shouldSucceed = false

    await setupFeedbackPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/feedback') && method === 'GET' && !url.includes('/export') && !url.match(/\/feedback\/[^/]+$/) && !url.includes('/feedback/stats') && !url.includes('/feedback/unreviewed-count')) {
          if (!shouldSucceed) {
            return { status: 500, body: JSON.stringify({ error: 'Internal error' }) }
          }
          const items = makeFeedbackList()
          return {
            body: JSON.stringify({
              items,
              nextCursor: null,
              prevCursor: null,
              approximateTotal: items.length,
            }),
          }
        }
        return defaultFeedbackHandler(url, method)
      },
    })

    // Error alert visible after TanStack Query exhausts retries
    await expect(page.locator('.alert-error')).toBeVisible({ timeout: 15000 })

    // Refresh button — allow success on next call (FeedbackManager re-fetches via invalidate)
    shouldSucceed = true
    await page.getByRole('button', { name: '새로고침' }).click()

    // After refresh, data should load
    await expect(page.getByText('How do I create a new Jira ticket?')).toBeVisible()
  })

  test('refresh button reloads data', async ({ page }) => {
    let loadCount = 0

    await setupFeedbackPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/feedback') && method === 'GET' && !url.includes('/export') && !url.match(/\/feedback\/[^/]+$/) && !url.includes('/feedback/stats') && !url.includes('/feedback/unreviewed-count')) {
          loadCount++
          const items = makeFeedbackList()
          return {
            body: JSON.stringify({
              items,
              nextCursor: null,
              prevCursor: null,
              approximateTotal: items.length,
            }),
          }
        }
        return defaultFeedbackHandler(url, method)
      },
    })

    await expect(page.getByText('How do I create a new Jira ticket?')).toBeVisible()
    const loadsBefore = loadCount

    await page.getByRole('button', { name: '새로고침' }).click()

    await expect.poll(() => loadCount).toBeGreaterThan(loadsBefore)
  })
})
