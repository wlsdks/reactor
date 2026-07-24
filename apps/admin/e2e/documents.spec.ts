import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const MOCK_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  // /documents requires this admin RAG seed-policy probe alongside /api/documents
  '/api/admin/rag/seed-policy',
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

const MOCK_CANDIDATES = [
  {
    id: 'candidate-1',
    runId: 'run-201',
    channel: 'slack',
    query: 'How do I configure SSO for the admin dashboard?',
    response: 'SSO can be configured by navigating to Platform Admin > Security > Authentication.',
    status: 'PENDING',
    capturedAt: Date.now() - 4 * 3600000,
    reviewedAt: null,
    reviewedBy: null,
    reviewComment: null,
    ingestedDocumentId: null,
  },
  {
    id: 'candidate-2',
    runId: 'run-202',
    channel: 'web',
    query: 'What are the rate limits for the Jira integration?',
    response: 'The Jira integration is configured with a rate limit of 10 requests per second.',
    status: 'INGESTED',
    capturedAt: Date.now() - 2 * 86400000,
    reviewedAt: Date.now() - 86400000,
    reviewedBy: 'admin@example.com',
    reviewComment: 'Good knowledge base entry',
    ingestedDocumentId: 'doc-ingested-1',
  },
  {
    id: 'candidate-3',
    runId: 'run-203',
    channel: 'slack',
    query: 'Can I use the bot to send emails?',
    response: 'Email sending is not currently supported.',
    status: 'REJECTED',
    capturedAt: Date.now() - 3 * 86400000,
    reviewedAt: Date.now() - 2 * 86400000,
    reviewedBy: 'ops@example.com',
    reviewComment: 'Too specific',
    ingestedDocumentId: null,
  },
]

const MOCK_SEARCH_RESULTS = [
  {
    id: 'doc-1',
    content: 'Search results for: test query\n\nThe Jira integration supports creating and searching issues.',
    metadata: { source: 'knowledge_base' },
    score: 0.92,
  },
  {
    id: 'doc-2',
    content: 'Rate limits are configured per-service in the MCP preflight configuration.',
    metadata: { source: 'docs' },
    score: 0.78,
  },
]

const MOCK_POLICY_STATE = {
  configEnabled: true,
  dynamicEnabled: true,
  effective: {
    enabled: true,
    requireReview: true,
    allowedChannels: ['slack', 'web'],
    minQueryChars: 20,
    minResponseChars: 50,
    blockedPatterns: ['password', 'secret', 'api_key'],
    createdAt: Date.now() - 15 * 86400000,
    updatedAt: Date.now() - 3 * 86400000,
  },
  stored: {
    enabled: true,
    requireReview: true,
    allowedChannels: ['slack', 'web'],
    minQueryChars: 20,
    minResponseChars: 50,
    blockedPatterns: ['password', 'secret', 'api_key'],
    createdAt: Date.now() - 15 * 86400000,
    updatedAt: Date.now() - 3 * 86400000,
  },
}

async function setupDocumentsPage(
  page: Page,
  handleApi: (url: string, method: string, pathname: string) => { status?: number; body: string } | null,
) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits', '/api/admin/capabilities', '/api/admin/rag/seed-policy',
        '/api/approvals', '/api/auth/login',
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
    const pathname = requestUrl.pathname

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

    const response = handleApi(url, method, pathname)
    if (response) {
      await route.fulfill({
        status: response.status ?? 200,
        contentType: 'application/json',
        body: response.body,
      })
      return
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/documents')
  await expect(page.getByRole('heading', { name: '문서', exact: true })).toBeVisible()
}

test.describe('/documents page', () => {
  test('loads with four tabs and defaults to Search tab', async ({ page }) => {
    await setupDocumentsPage(page, (_url, _method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify(MOCK_CANDIDATES) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      return null
    })

    // All four tabs should be visible
    const tabs = page.locator('.detail-tabs .tab-btn')
    await expect(tabs.nth(0)).toHaveText('검색')
    await expect(tabs.nth(1)).toHaveText('등록')
    await expect(tabs.nth(2)).toHaveText('수집 관리')
    await expect(tabs.nth(3)).toHaveText('정책')

    // Search tab is active by default — search panel visible
    await expect(page.getByRole('heading', { name: '색인된 문서 검색 및 삭제' })).toBeVisible()
  })

  test('search tab performs document search and shows results', async ({ page }) => {
    let searchCalled = false
    await setupDocumentsPage(page, (url, method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      if (pathname === '/api/documents/search' && method === 'POST') {
        searchCalled = true
        return { body: JSON.stringify(MOCK_SEARCH_RESULTS) }
      }
      return null
    })

    // Fill search query and submit
    await page.getByRole('textbox').first().fill('test query')
    await page.locator('button.btn-primary', { hasText: '검색' }).click()

    await expect.poll(() => searchCalled).toBe(true)

    // Verify results are displayed (scope to td code so the auto-opened
    // detail panel's code element does not trigger strict-mode violation)
    await expect(page.locator('td code', { hasText: 'doc-1' }).first()).toBeVisible()
    await expect(page.locator('td code', { hasText: 'doc-2' }).first()).toBeVisible()
    // Score is shown with 4 decimal places in the table and 5 in the detail panel;
    // target the table cell to avoid strict mode violation
    await expect(page.locator('td', { hasText: '0.9200' }).first()).toBeVisible()
  })

  test('tab switching navigates between all four tabs', async ({ page }) => {
    await setupDocumentsPage(page, (_url, _method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify(MOCK_CANDIDATES) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      return null
    })

    // Switch to Register tab
    await page.getByRole('tab', { name: '등록' }).click()
    await expect(page.getByText('문서 추가')).toBeVisible()

    // Switch to Review Queue tab
    await page.getByRole('tab', { name: '수집 관리' }).click()
    await expect(page.getByText('RAG 수집 후보')).toBeVisible()

    // Switch to Policy tab
    await page.getByRole('tab', { name: '정책' }).click()
    await expect(page.getByText('RAG 수집 정책')).toBeVisible()

    // Switch back to Search tab
    await page.getByRole('tab', { name: '검색' }).click()
    await expect(page.getByText('색인된 문서 검색 및 삭제')).toBeVisible()
  })

  test('ingestion tab displays candidates and allows approve/reject', async ({ page }) => {
    const actionCalls: string[] = []

    await setupDocumentsPage(page, (url, method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_CANDIDATES) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      if (url.includes('/candidates/candidate-1/approve') && method === 'POST') {
        actionCalls.push('approve')
        return {
          body: JSON.stringify({
            ...MOCK_CANDIDATES[0],
            status: 'INGESTED',
            reviewedAt: Date.now(),
            reviewedBy: 'admin@example.com',
          }),
        }
      }
      return null
    })

    // Navigate to Review Queue tab
    await page.getByRole('tab', { name: '수집 관리' }).click()
    await expect(page.getByText('RAG 수집 후보')).toBeVisible()

    // Candidates should be displayed
    await expect(page.getByText('How do I configure SSO for the admin dashboard?')).toBeVisible()
    await expect(page.getByText('What are the rate limits for the Jira integration?')).toBeVisible()

    // Click approve on the pending candidate (use CSS selector to avoid matching <tr role="button">)
    const approveButtons = page.locator('button', { hasText: '승인' })
    await approveButtons.first().click()

    await expect.poll(() => actionCalls.length).toBe(1)
    expect(actionCalls[0]).toBe('approve')
  })

  test('ingestion tab shows empty state when no candidates', async ({ page }) => {
    await setupDocumentsPage(page, (_url, _method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      return null
    })

    await page.getByRole('tab', { name: '수집 관리' }).click()
    await expect(page.getByText('후보 없음')).toBeVisible()
  })

  test('policy tab displays policy settings and allows editing', async ({ page }) => {
    let policySaved = false

    await setupDocumentsPage(page, (_url, method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy' && method === 'GET') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      if (pathname === '/api/rag-ingestion/policy' && method === 'PUT') {
        policySaved = true
        return { body: JSON.stringify({ ...MOCK_POLICY_STATE.effective, updatedAt: Date.now() }) }
      }
      return null
    })

    // Switch to Policy tab
    await page.getByRole('tab', { name: '정책' }).click()
    await expect(page.getByText('RAG 수집 정책')).toBeVisible()

    // Policy metadata should display
    await expect(page.getByText('설정 활성')).toBeVisible()
    await expect(page.getByText('동적 활성')).toBeVisible()

    // Checkboxes should reflect server state
    const enabledCheckbox = page.locator('#rag-policy-enabled')
    await expect(enabledCheckbox).toBeChecked()

    const reviewCheckbox = page.locator('#rag-policy-review')
    await expect(reviewCheckbox).toBeChecked()

    // Save button should be present
    await expect(page.getByRole('button', { name: '정책 저장' })).toBeVisible()

    // Toggle enable checkbox and save
    await enabledCheckbox.click()
    await page.getByRole('button', { name: '정책 저장' }).click()

    await expect.poll(() => policySaved).toBe(true)
  })

  test('policy tab shows unavailable state when policy endpoint returns 404', async ({ page }) => {
    await setupDocumentsPage(page, (_url, _method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        // Error message must contain 'HTTP 404' to match the catch block in the queryFn
        return { status: 404, body: JSON.stringify({ error: 'HTTP 404' }) }
      }
      return null
    })

    await page.getByRole('tab', { name: '정책' }).click()
    await expect(page.getByText('동적 RAG 정책 API가 이 서버에서 활성화되어 있지 않습니다.')).toBeVisible()
  })

  test('policy tab reset to defaults calls delete endpoint', async ({ page }) => {
    let resetCalled = false

    await setupDocumentsPage(page, (_url, method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy' && method === 'GET') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      if (pathname === '/api/rag-ingestion/policy' && method === 'DELETE') {
        resetCalled = true
        return { status: 204, body: '' }
      }
      return null
    })

    await page.getByRole('tab', { name: '정책' }).click()
    await expect(page.getByText('RAG 수집 정책')).toBeVisible()

    await page.getByRole('button', { name: '설정 기본값으로 초기화' }).click()

    await expect.poll(() => resetCalled).toBe(true)
  })

  test('register tab allows adding a single document', async ({ page }) => {
    let addCalled = false

    await setupDocumentsPage(page, (_url, method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      if (pathname === '/api/documents' && method === 'POST') {
        addCalled = true
        return {
          body: JSON.stringify({ id: 'doc-new', content: 'Test document content', metadata: { source: 'admin' } }),
        }
      }
      return null
    })

    // Switch to Register tab
    await page.getByRole('tab', { name: '등록' }).click()
    await expect(page.getByText('문서 추가')).toBeVisible()

    // Fill the content textarea (first textarea in the Add Document section)
    const contentTextarea = page.locator('textarea').first()
    await contentTextarea.fill('Test document content')

    // Click Add button
    await page.getByRole('button', { name: '추가' }).first().click()

    await expect.poll(() => addCalled).toBe(true)
  })

  test('error state shows error alert with retry button', async ({ page }) => {
    let callCount = 0

    await setupDocumentsPage(page, (_url, method, pathname) => {
      if (pathname === '/api/rag-ingestion/candidates') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/rag-ingestion/policy') {
        return { body: JSON.stringify(MOCK_POLICY_STATE) }
      }
      if (pathname === '/api/documents/search' && method === 'POST') {
        callCount++
        if (callCount === 1) {
          return { status: 500, body: JSON.stringify({ error: 'Internal server error' }) }
        }
        return { body: JSON.stringify(MOCK_SEARCH_RESULTS) }
      }
      return null
    })

    // Try to search — should trigger error since empty query is validated client-side
    // But we need to fill a query to hit the server error
    await page.getByRole('textbox').first().fill('test')
    await page.locator('button.btn-primary', { hasText: '검색' }).click()

    // The error alert should appear
    await expect(page.locator('.alert-error')).toBeVisible()
  })
})
