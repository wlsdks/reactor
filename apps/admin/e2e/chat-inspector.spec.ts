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

const MOCK_PERSONAS = [
  { id: 'persona-1', name: 'Engineer Assistant', isActive: true, description: 'Helps with engineering' },
  { id: 'persona-2', name: 'HR Helper', isActive: true, description: 'Answers HR questions' },
  { id: 'persona-3', name: 'Inactive Bot', isActive: false, description: 'Deactivated' },
]

// Sessions /models endpoint returns wrapper shape (used by chat-inspector ConfigToolbar persona/model dropdowns)
const MOCK_MODELS = {
  models: [
    { name: 'claude-sonnet-4-20250514', isDefault: true },
    { name: 'claude-opus-4-20250514', isDefault: false },
  ],
}

// /api/admin/models registry endpoint returns bare ModelEntry[] (used by useModelPricing for cost calc)
const MOCK_MODELS_REGISTRY = [
  {
    name: 'claude-sonnet-4-20250514',
    inputPricePerMillionTokens: 3,
    outputPricePerMillionTokens: 15,
    isDefault: true,
  },
  {
    name: 'claude-opus-4-20250514',
    inputPricePerMillionTokens: 15,
    outputPricePerMillionTokens: 75,
    isDefault: false,
  },
]

const MOCK_TEMPLATES = [
  { id: 'tpl-1', name: 'Default QA Template', content: 'Answer the question: {{question}}' },
  { id: 'tpl-2', name: 'Summary Template', content: 'Summarize: {{text}}' },
]

const MOCK_CHAT_RESPONSE = {
  content: 'This is a test response from the AI assistant.',
  success: true,
  model: 'claude-sonnet-4-20250514',
  toolsUsed: ['jira_search', 'confluence_get_page'],
  durationMs: 1250,
  errorMessage: null,
  errorCode: null,
  grounded: true,
  verifiedSourceCount: 2,
  blockReason: null,
  metadata: {
    grounded: true,
    answerMode: 'grounded',
    verifiedSources: [
      { title: 'Jira Guide', url: 'https://example.com/jira-guide' },
      { title: 'Confluence Docs', url: 'https://example.com/confluence-docs' },
    ],
    tokenUsage: { promptTokens: 150, completionTokens: 85, totalTokens: 235 },
    toolSignals: [],
    outputGuard: null,
    blockReason: null,
  },
}

const MOCK_DASHBOARD = {
  generatedAt: Date.now(),
  ragEnabled: false,
  mcp: { total: 0, statusCounts: {} },
  scheduler: { totalJobs: 0, enabledJobs: 0, runningJobs: 0, failedJobs: 0, attentionBacklog: 0, agentJobs: 0 },
  recentSchedulerExecutions: [],
  approvals: { pendingCount: 0 },
  responseTrust: { unverifiedResponses: 0, outputGuardRejected: 0, outputGuardModified: 0, boundaryFailures: 0 },
  employeeValue: {
    observedResponses: 0, groundedResponses: 0, groundedRatePercent: 0, blockedResponses: 0,
    interactiveResponses: 0, scheduledResponses: 0, answerModes: {}, channels: [], lanes: [], toolFamilies: [], topMissingQueries: [],
  },
  recentTrustEvents: [],
  metrics: [],
}

interface ChatInspectorOptions {
  handleApi?: (url: string, method: string) => { status?: number; body: string } | null
}

async function setupChatInspectorPage(page: Page, options: ChatInspectorOptions = {}) {
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
        body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: MOCK_CAPABILITY_PATHS }),
      })
      return
    }
    if (url.includes('/ops/dashboard')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_DASHBOARD) })
      return
    }

    // ConfigToolbar dependencies
    if (url.includes('/personas') && method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_PERSONAS) })
      return
    }
    // useModelPricing hits /api/admin/models — return bare ModelEntry[] to satisfy .find()
    if (requestUrl.pathname === '/api/admin/models' && method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_MODELS_REGISTRY) })
      return
    }
    if (url.includes('/models') && method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_MODELS) })
      return
    }
    if (url.includes('/prompt-templates') && method === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_TEMPLATES) })
      return
    }

    // Custom handler override
    if (options.handleApi) {
      const response = options.handleApi(url, method)
      if (response) {
        await route.fulfill({
          status: response.status ?? 200,
          contentType: 'application/json',
          body: response.body,
        })
        return
      }
    }

    // Default chat API response
    if (requestUrl.pathname === '/api/chat' && method === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_CHAT_RESPONSE),
      })
      return
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/chat-inspector')
}

test.describe('/chat-inspector page', () => {
  test('loads with title, config toolbar, and message input on a single screen', async ({ page }) => {
    await setupChatInspectorPage(page)

    // Page title should be visible
    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Mode tabs (One-shot Request / Live Stream) live in the sidebar
    await expect(page.getByRole('tab', { name: '단일 요청' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '실시간 스트림' })).toBeVisible()

    // Config toolbar should show dropdowns for persona, model, and template
    await expect(page.locator('#ci-persona')).toBeVisible()
    await expect(page.locator('#ci-model')).toBeVisible()
    await expect(page.locator('#ci-template')).toBeVisible()

    // Message textarea + run button live on the same screen as configure (no wizard step)
    await expect(page.locator('#chat-inspector-message')).toBeVisible()
    await expect(page.getByRole('button', { name: '채팅 요청 실행' })).toBeVisible()
  })

  test('populates config toolbar dropdowns with persona, model, and template options', async ({ page }) => {
    await setupChatInspectorPage(page)

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Persona dropdown should have active personas only (2 of 3)
    const personaSelect = page.locator('#ci-persona')
    await expect(personaSelect.locator('option')).toHaveCount(3) // "None" + 2 active personas

    // Model dropdown should have models
    const modelSelect = page.locator('#ci-model')
    await expect(modelSelect.locator('option')).toHaveCount(3) // "None" + 2 models

    // Template dropdown should have templates
    const templateSelect = page.locator('#ci-template')
    await expect(templateSelect.locator('option')).toHaveCount(3) // "None" + 2 templates
  })

  test('sends a chat message and displays the response with trust details', async ({ page }) => {
    let chatRequestReceived = false

    await setupChatInspectorPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/api/chat') && method === 'POST' && !url.includes('/stream')) {
          chatRequestReceived = true
          return { body: JSON.stringify(MOCK_CHAT_RESPONSE) }
        }
        return null
      },
    })

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Type a message — message textarea lives on the same screen as configure
    await page.locator('#chat-inspector-message').fill('How do I set up Jira?')

    // Click the Run Chat Request button
    await page.getByRole('button', { name: '채팅 요청 실행' }).click()

    // Wait for the response
    await expect.poll(() => chatRequestReceived).toBe(true)

    // Response section should appear (use exact match to avoid matching raw JSON section too)
    await expect(page.getByText('This is a test response from the AI assistant.', { exact: true })).toBeVisible({ timeout: 10000 })

    // Model should be shown in the response meta grid
    await expect(page.locator('.meta-grid').getByText('claude-sonnet-4-20250514')).toBeVisible()

    // Tools used should be displayed as tags
    await expect(page.locator('.tag-list .tag').getByText('jira_search')).toBeVisible()
    await expect(page.locator('.tag-list .tag').getByText('confluence_get_page')).toBeVisible()
  })

  test('shows validation error when submitting empty message', async ({ page }) => {
    await setupChatInspectorPage(page)

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Click run without typing a message
    await page.getByRole('button', { name: '채팅 요청 실행' }).click()

    // Error alert should appear
    await expect(page.locator('.alert.alert-error')).toBeVisible()
  })

  test('shows error state when chat API returns an error', async ({ page }) => {
    await setupChatInspectorPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/api/chat') && method === 'POST') {
          return { status: 500, body: JSON.stringify({ error: 'Model is currently unavailable' }) }
        }
        return null
      },
    })

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Type a message and send
    await page.locator('#chat-inspector-message').fill('Test message')
    await page.getByRole('button', { name: '채팅 요청 실행' }).click()

    // Error should be displayed
    await expect(page.locator('.alert.alert-error')).toBeVisible({ timeout: 10000 })
  })

  test('can select a persona from the config toolbar dropdown', async ({ page }) => {
    await setupChatInspectorPage(page)

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Select a persona
    await page.locator('#ci-persona').selectOption('persona-1')
    await expect(page.locator('#ci-persona')).toHaveValue('persona-1')

    // Select a model
    await page.locator('#ci-model').selectOption('claude-opus-4-20250514')
    await expect(page.locator('#ci-model')).toHaveValue('claude-opus-4-20250514')
  })

  test('sends chat request with selected persona and model', async ({ page }) => {
    let capturedBody: Record<string, unknown> | null = null

    await setupChatInspectorPage(page, {
      handleApi: (url, method) => {
        if (url.includes('/api/chat') && method === 'POST' && !url.includes('/stream')) {
          return { body: JSON.stringify(MOCK_CHAT_RESPONSE) }
        }
        return null
      },
    })

    // Capture the chat POST request body via request event listener (no second route needed)
    page.on('request', (request) => {
      if (request.url().includes('/api/chat') && request.method() === 'POST') {
        capturedBody = request.postDataJSON()
      }
    })

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Select persona and model in the sidebar
    await page.locator('#ci-persona').selectOption('persona-1')
    await page.locator('#ci-model').selectOption('claude-opus-4-20250514')

    // Type and send message — message textarea is on the same screen
    await page.locator('#chat-inspector-message').fill('How do I set up Jira?')
    await page.getByRole('button', { name: '채팅 요청 실행' }).click()

    // Wait for request to be captured
    await expect.poll(() => capturedBody !== null).toBe(true)

    // Verify the request included persona and model
    expect(capturedBody!.personaId).toBe('persona-1')
    expect(capturedBody!.model).toBe('claude-opus-4-20250514')
    expect(capturedBody!.message).toBe('How do I set up Jira?')
  })

  test('switches between Chat and Stream mode tabs', async ({ page }) => {
    await setupChatInspectorPage(page)

    await expect(page.getByRole('heading', { name: '채팅 테스터' })).toBeVisible({ timeout: 15000 })

    // Chat mode should be active by default
    const chatTab = page.locator('.detail-tabs .tab-btn').first()
    await expect(chatTab).toHaveClass(/active/)

    // Switch to Stream mode
    const streamTab = page.locator('.detail-tabs .tab-btn').nth(1)
    await streamTab.click()
    await expect(streamTab).toHaveClass(/active/)

    // The run button text should reflect stream mode
    await expect(page.locator('.detail-actions .btn.btn-primary')).toBeVisible()

    // Switch back to Chat mode
    await chatTab.click()
    await expect(chatTab).toHaveClass(/active/)
  })
})
