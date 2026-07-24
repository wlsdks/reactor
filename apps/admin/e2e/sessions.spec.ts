import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const DEFAULT_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/admin/sessions',
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

interface SetupOptions {
  capabilityPaths?: string[]
  handleApi: (url: string, method: string) => { status?: number; body: string }
  path?: string
}

async function setupPage(page: Page, options: SetupOptions) {
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

  await page.goto(options.path ?? '/sessions')
}

// ---- Mock data factories ----

function makeOverviewData() {
  return {
    totalSessions: 150,
    todaySessions: 12,
    avgMessagesPerSession: 6.3,
    activeUsers: 20,
    trustIssues: 5,
    negativeFeedback: 3,
    changes: {
      totalSessions: 0.12,
      todaySessions: -0.05,
      avgMessagesPerSession: 0.03,
      activeUsers: 0.08,
      trustIssues: -0.15,
      negativeFeedback: 0.0,
    },
    trend: [
      { date: '2026-04-01', count: 45 },
      { date: '2026-04-02', count: 52 },
    ],
    channelMix: [
      { channel: 'web', count: 100 },
      { channel: 'slack', count: 50 },
    ],
    topUsers: [
      { userId: 'user_001', sessionCount: 15, messageCount: 120 },
    ],
    personaUsage: [
      { personaId: 'p1', name: 'Default', percentage: 65.0 },
    ],
    recentSessions: [],
    trustEvents: [],
  }
}

function makeSessionList(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    sessionId: `sess_${i + 1}`,
    userId: `user_${String((i % 5) + 1).padStart(3, '0')}`,
    channel: (['web', 'slack', 'teams'] as const)[i % 3],
    personaId: 'p1',
    personaName: 'Default',
    messageCount: 3 + i,
    preview: `Session ${i + 1} preview`,
    lastActivity: NOW - i * HOUR,
    duration: 60000 + i * 1000,
    trust: i % 7 === 0 ? ('flagged' as const) : ('clean' as const),
    feedback: i % 3 === 0 ? ('positive' as const) : null,
    tags: [],
  }))
}

function makeSessionDetail(sessionId: string) {
  return {
    sessionId,
    userId: 'user_001',
    channel: 'web',
    personaId: 'p1',
    personaName: 'Default',
    model: null,
    messageCount: 3,
    duration: 60000,
    startedAt: NOW - HOUR,
    lastActivity: NOW,
    trust: 'clean',
    feedback: 'positive',
    tags: [],
    messages: [
      { id: 1, role: 'user', content: 'Hello, how can I set up the integration?', timestamp: NOW - HOUR },
      { id: 2, role: 'assistant', content: 'To set up the integration, navigate to MCP Servers and register a new server.', timestamp: NOW - HOUR + 2000, model: 'gpt-4', durationMs: 1500 },
      { id: 3, role: 'user', content: 'Thanks for the help!', timestamp: NOW - HOUR + 5000 },
    ],
  }
}

function makeUserList(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    userId: `user_${String(i + 1).padStart(3, '0')}`,
    sessionCount: 10 - i,
    totalMessages: 100 - i * 5,
    lastActive: NOW - i * 86400000,
    firstSeen: NOW - 30 * 86400000,
    trustIssueCount: i % 5 === 0 ? 2 : 0,
    negativeFeedbackCount: i % 3 === 0 ? 1 : 0,
    positiveFeedbackCount: 5,
  }))
}

// Utility to extract pathname from a full URL for cleaner matching
function pathname(url: string): string {
  try {
    return new URL(url).pathname
  } catch {
    return url
  }
}

// Default handler that covers all session-related routes
function defaultSessionHandler(url: string, method: string): { status?: number; body: string } {
  const path = pathname(url)

  if (path === '/api/admin/sessions/overview' && method === 'GET') {
    return { body: JSON.stringify(makeOverviewData()) }
  }
  if (path.match(/^\/api\/admin\/sessions\/[^/]+\/export$/) && method === 'GET') {
    return { body: JSON.stringify({ sessionId: 'sess_1', exportedAt: NOW, messages: [] }) }
  }
  if (path.match(/^\/api\/admin\/sessions\/[^/]+\/tags/) && method === 'POST') {
    return { body: JSON.stringify({ id: `tag_${NOW}`, label: 'test-tag', comment: null, createdBy: 'admin', createdAt: NOW }) }
  }
  if (path.match(/^\/api\/admin\/sessions\/[^/]+$/) && method === 'DELETE') {
    return { status: 204, body: '' }
  }
  // Session detail — must come after /overview, /export, /tags checks
  if (path.match(/^\/api\/admin\/sessions\/[^/]+$/) && method === 'GET') {
    const match = path.match(/^\/api\/admin\/sessions\/([^/]+)$/)
    const sessionId = match ? match[1] : 'sess_1'
    return { body: JSON.stringify(makeSessionDetail(sessionId)) }
  }
  // Session list
  if (path === '/api/admin/sessions' && method === 'GET') {
    const urlObj = new URL(url)
    const offset = Number(urlObj.searchParams.get('offset') ?? 0)
    const limit = Number(urlObj.searchParams.get('limit') ?? 30)
    const sessions = makeSessionList(50)
    return {
      body: JSON.stringify({
        items: sessions.slice(offset, offset + limit),
        total: sessions.length,
        offset,
        limit,
      }),
    }
  }
  // User sessions
  if (path.match(/^\/api\/admin\/users\/[^/]+\/sessions$/) && method === 'GET') {
    const urlObj = new URL(url)
    const offset = Number(urlObj.searchParams.get('offset') ?? 0)
    const limit = Number(urlObj.searchParams.get('limit') ?? 30)
    const items = makeSessionList(5)
    return {
      body: JSON.stringify({ items: items.slice(offset, offset + limit), total: items.length, offset, limit }),
    }
  }
  // User list
  if (path === '/api/admin/users' && method === 'GET') {
    const urlObj = new URL(url)
    const offset = Number(urlObj.searchParams.get('offset') ?? 0)
    const limit = Number(urlObj.searchParams.get('limit') ?? 30)
    const users = makeUserList(20)
    return {
      body: JSON.stringify({
        items: users.slice(offset, offset + limit),
        total: users.length,
        offset,
        limit,
      }),
    }
  }
  return { body: '[]' }
}


test.describe('/sessions overview page', () => {
  test('renders overview stat cards and charts', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
    })

    // Overview page shows the title
    await expect(page.getByRole('heading', { name: '대화 기록' })).toBeVisible()

    // Stat cards with overview numbers
    await expect(page.getByText('150')).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '12' })).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '20' })).toBeVisible()
  })

  test('shows period selector and changes period', async ({ page }) => {
    let receivedPeriod = ''

    await setupPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/admin/sessions/overview') && method === 'GET') {
          const urlObj = new URL(url)
          receivedPeriod = urlObj.searchParams.get('period') ?? ''
          return { body: JSON.stringify(makeOverviewData()) }
        }
        return defaultSessionHandler(url, method)
      },
    })

    await expect(page.getByRole('heading', { name: '대화 기록' })).toBeVisible()

    // Change period to 30d
    await page.locator('.overview-period-select').selectOption('30d')

    await expect.poll(() => receivedPeriod).toBe('30d')
  })

  test('shows error state and retry button on API failure', async ({ page }) => {
    let callCount = 0
    let shouldSucceed = false

    await setupPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/admin/sessions/overview') && method === 'GET') {
          callCount++
          if (shouldSucceed) {
            return { body: JSON.stringify(makeOverviewData()) }
          }
          return { status: 500, body: JSON.stringify({ error: 'Server error' }) }
        }
        return defaultSessionHandler(url, method)
      },
    })

    // Error state visible after TanStack Query exhausts retries
    await expect(page.getByText('데이터를 불러올 수 없어요. 연결 상태를 확인하고 다시 시도해 주세요.')).toBeVisible({ timeout: 15000 })

    // Retry button works — allow success on next call
    shouldSucceed = true
    await page.getByRole('button', { name: '재시도' }).click()
    await expect.poll(() => callCount).toBeGreaterThanOrEqual(4)
  })
})


test.describe('/sessions/feed session list', () => {
  test('loads and displays session feed with session rows', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
      path: '/sessions/feed',
    })

    // Breadcrumb shows
    await expect(page.getByText('세션', { exact: true })).toBeVisible()

    // Sessions count header
    await expect(page.getByText('50건 세션')).toBeVisible()

    // At least one session row is rendered
    await expect(page.getByText('Session 1 preview')).toBeVisible()
  })

  test('navigates to session detail when clicking a session', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
      path: '/sessions/feed',
    })

    await expect(page.getByText('Session 1 preview')).toBeVisible()

    // Click the first session row
    await page.getByText('Session 1 preview').click()

    // URL should change to session detail
    await expect(page).toHaveURL(/\/sessions\/sess_1/)
  })

  test('shows empty state when no sessions exist', async ({ page }) => {
    await setupPage(page, {
      handleApi: (url, method) => {
        const p = pathname(url)
        if (p === '/api/admin/sessions' && method === 'GET') {
          return {
            body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 30 }),
          }
        }
        return defaultSessionHandler(url, method)
      },
      path: '/sessions/feed',
    })

    // Empty state message
    await expect(page.getByText('대화 데이터가 없습니다')).toBeVisible()
  })

  test('shows no-results state when filters yield no matches', async ({ page }) => {
    await setupPage(page, {
      handleApi: (url, method) => {
        const p = pathname(url)
        if (p === '/api/admin/sessions' && method === 'GET') {
          const urlObj = new URL(url)
          const channels = urlObj.searchParams.getAll('channel')
          if (channels.includes('discord')) {
            return {
              body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 30 }),
            }
          }
        }
        return defaultSessionHandler(url, method)
      },
      path: '/sessions/feed?channel=discord',
    })

    // Empty filter state message
    await expect(page.getByText('필터 조건에 맞는 세션이 없습니다')).toBeVisible()
    await expect(page.getByText('필터 초기화')).toBeVisible()
  })

  test('shows feature unavailable state when sessions endpoint is not in capabilities', async ({ page }) => {
    await setupPage(page, {
      capabilityPaths: DEFAULT_CAPABILITY_PATHS.filter((p) => p !== '/api/admin/sessions'),
      handleApi: defaultSessionHandler,
      path: '/sessions/feed',
    })

    await expect(page.getByText('이 기능은 현재 서버에서 사용할 수 없어요. 관리자에게 문의해 주세요.')).toBeVisible()
  })
})


test.describe('/sessions/:sessionId detail page', () => {
  test('displays session detail with messages', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
      path: '/sessions/sess_1',
    })

    // Breadcrumb
    await expect(page.getByText('대화 상세')).toBeVisible()

    // Session metadata visible
    await expect(page.getByText('user_001')).toBeVisible()
    await expect(page.getByText('3건 메시지')).toBeVisible()

    // Chat messages rendered
    await expect(page.getByText('Hello, how can I set up the integration?')).toBeVisible()
    await expect(page.getByText('To set up the integration, navigate to MCP Servers and register a new server.')).toBeVisible()
    await expect(page.getByText('Thanks for the help!')).toBeVisible()

    // End of conversation marker
    await expect(page.getByText('대화 종료')).toBeVisible()
  })

  test('shows action buttons: Flag, Export, Open in Inspector, Delete', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
      path: '/sessions/sess_1',
    })

    await expect(page.getByRole('button', { name: '플래그' })).toBeVisible()
    await expect(page.getByRole('button', { name: /내보내기/ })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Inspector에서 열기' })).toBeVisible()
    await expect(page.getByRole('button', { name: '삭제' })).toBeVisible()
  })

  test('delete confirmation dialog appears and confirms deletion', async ({ page }) => {
    let deleteRequested = false

    await setupPage(page, {
      handleApi: (url, method) => {
        const p = pathname(url)
        if (p === '/api/admin/sessions/sess_1' && method === 'DELETE') {
          deleteRequested = true
          return { status: 204, body: '' }
        }
        return defaultSessionHandler(url, method)
      },
      path: '/sessions/sess_1',
    })

    await page.getByRole('button', { name: '삭제' }).click()

    // Confirm dialog visible
    await expect(page.getByText('"sess_1" 세션을 삭제할까요? 이 작업은 되돌릴 수 없어요.')).toBeVisible()

    // Confirm. Scope to the dialog so we don't pick up the header
    // HealthBadge ("상태 · 확인 중") that also matches /확인/i.
    await page.getByRole('dialog').getByRole('button', { name: '확인', exact: true }).click()

    await expect.poll(() => deleteRequested).toBe(true)
  })

  test('shows error state for non-existent session', async ({ page }) => {
    await setupPage(page, {
      handleApi: (url, method) => {
        const p = pathname(url)
        if (p === '/api/admin/sessions/nonexistent' && method === 'GET') {
          return { status: 404, body: JSON.stringify({ error: 'Not found' }) }
        }
        return defaultSessionHandler(url, method)
      },
      path: '/sessions/nonexistent',
    })

    // The ky client throws an HTTPError on 404, which TanStack Query catches
    // and renders an error state via the error boundary or error display
    await expect(page.locator('.error-state')).toBeVisible({ timeout: 10000 })
  })
})


test.describe('/sessions/users user list', () => {
  test('displays user list with user rows', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
      path: '/sessions/users',
    })

    // Users breadcrumb
    await expect(page.getByText('사용자', { exact: true })).toBeVisible()

    // User count
    await expect(page.getByText('20명')).toBeVisible()

    // At least one user row
    await expect(page.getByText('user_001')).toBeVisible()
  })

  test('sort and period dropdowns are present', async ({ page }) => {
    await setupPage(page, {
      handleApi: defaultSessionHandler,
      path: '/sessions/users',
    })

    // Sort dropdown exists and has options
    const sortSelect = page.locator('select').filter({ hasText: '활동순' })
    await expect(sortSelect).toBeVisible()

    // Period dropdown exists
    const periodSelect = page.locator('select').filter({ hasText: '7일' })
    await expect(periodSelect).toBeVisible()
  })
})
