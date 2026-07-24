import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

/* ------------------------------------------------------------------ */
/*  Shared mock data & bootstrap helper                               */
/* ------------------------------------------------------------------ */

const CAPABILITY_ENDPOINTS = [
  '/api/admin/audits', '/api/admin/capabilities', '/api/approvals', '/api/auth/login',
  '/api/auth/me', '/api/auth/register', '/api/chat', '/api/documents', '/api/feedback',
  '/api/intents', '/api/mcp/servers', '/api/ops/dashboard', '/api/output-guard/rules',
  '/api/personas', '/api/prompt-lab/experiments', '/api/prompt-templates',
  '/api/rag-ingestion/candidates', '/api/scheduler/jobs', '/api/sessions', '/api/tool-policy',
]

const MOCK_PERSONAS = [
  {
    id: 'persona-1',
    name: 'Support Bot',
    description: 'Customer support assistant',
    systemPrompt: 'You are a helpful support assistant.',
    responseGuideline: 'Always be polite and concise.',
    welcomeMessage: 'Hello! How can I help you today?',
    promptTemplateId: null,
    icon: '🤖',
    isDefault: true,
    isActive: true,
    createdAt: 1704067200000,
    updatedAt: 1704153600000,
  },
  {
    id: 'persona-2',
    name: 'Sales Bot',
    description: 'Sales assistant',
    systemPrompt: 'You are a helpful sales assistant.',
    responseGuideline: null,
    welcomeMessage: null,
    promptTemplateId: 'template-sales',
    icon: '📣',
    isDefault: false,
    isActive: true,
    createdAt: 1704240000000,
    updatedAt: 1704326400000,
  },
  {
    id: 'persona-3',
    name: 'Inactive Helper',
    description: 'An inactive test persona',
    systemPrompt: 'You are a test persona.',
    responseGuideline: null,
    welcomeMessage: null,
    promptTemplateId: null,
    icon: null,
    isDefault: false,
    isActive: false,
    createdAt: 1704412800000,
    updatedAt: 1704412800000,
  },
]

async function setupPersonasPage(
  page: Page,
  handleApi: (url: string, method: string, body?: string | null) => { status?: number; body: string },
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

    const url = requestUrl.pathname
    const method = route.request().method()

    if (url.includes('/auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (url.includes('/auth/login')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
      return
    }
    if (url.includes('/admin/capabilities')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: CAPABILITY_ENDPOINTS }),
      })
      return
    }

    let reqBody: string | null = null
    try { reqBody = await route.request().postData() } catch { /* no body */ }

    const response = handleApi(url, method, reqBody)
    await route.fulfill({
      status: response.status ?? 200,
      contentType: 'application/json',
      body: response.body,
    })
  })

  await page.goto('/personas')
  await expect(page.locator('.page-title')).toBeVisible({ timeout: 15000 })
}


/* ================================================================== */
/*  Test suite                                                        */
/* ================================================================== */

test.describe('/personas page', () => {

  test('loads and displays persona list with stat cards', async ({ page }) => {
    await setupPersonasPage(page, (url, method) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      return { body: '[]' }
    })

    // Page title is visible
    await expect(page.locator('.page-title')).toContainText('페르소나')

    // Stat cards (StatCard renders labels uppercased; Korean text is unchanged by toUpperCase)
    await expect(page.locator('.stat-card-label').filter({ hasText: '전체 페르소나' }).first()).toBeVisible()
    await expect(page.locator('.stat-card-label').filter({ hasText: '활성' }).first()).toBeVisible()

    // Persona rows
    await expect(page.getByText('Support Bot')).toBeVisible()
    await expect(page.getByText('Sales Bot')).toBeVisible()
    await expect(page.getByText('Inactive Helper')).toBeVisible()

    // NOTE: Default/Inactive badges moved from list view to detail panel
    // (PersonaInfoTab) after PR #335 introduced inline-edit on the name
    // column. They are verified by detail-panel tests below.
  })

  test('shows empty state when no personas exist', async ({ page }) => {
    await setupPersonasPage(page, (url, method) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    await expect(page.getByText('페르소나가 없습니다')).toBeVisible()
    // Empty state should show a create action button (page header also has one)
    await expect(page.getByRole('button', { name: /페르소나 생성/ }).first()).toBeVisible()
  })

  test('opens detail panel when clicking a persona row', async ({ page }) => {
    await setupPersonasPage(page, (url, method) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      if (url.includes('/api/personas/persona-1') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS[0]) }
      }
      return { body: '[]' }
    })

    // Click the first persona row. The name cell is now inline-editable
    // (PR #335) and stops click propagation, so we target the row's date
    // cell instead to trigger the row-level onRowClick handler.
    await page.locator('tr').filter({ hasText: 'Support Bot' }).locator('td').nth(1).click()

    // Detail panel opens with info tab
    await expect(page.locator('.detail-panel')).toBeVisible()
    await expect(page.locator('.persona-summary-name')).toContainText('Support Bot')

    // System prompt is displayed
    await expect(page.getByText('You are a helpful support assistant.')).toBeVisible()

    // Description is displayed
    await expect(page.getByText('Customer support assistant')).toBeVisible()

    // Response guideline is displayed
    await expect(page.getByText('Always be polite and concise.')).toBeVisible()

    // Welcome message is displayed
    await expect(page.getByText('Hello! How can I help you today?')).toBeVisible()
  })

  test('switches between Info and Playground tabs', async ({ page }) => {
    await setupPersonasPage(page, (url, method) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      if (url.includes('/api/personas/persona-1') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS[0]) }
      }
      return { body: '[]' }
    })

    // Select a persona via the date cell (name cell is inline-editable after PR #335)
    await page.locator('tr').filter({ hasText: 'Support Bot' }).locator('td').nth(1).click()
    await expect(page.locator('.detail-panel')).toBeVisible()

    // Info tab should be active by default
    const infoTab = page.locator('.tab-btn').filter({ hasText: '정보' })
    await expect(infoTab).toHaveClass(/active/)

    // Switch to Playground tab
    const playgroundTab = page.locator('.tab-btn').filter({ hasText: '플레이그라운드' })
    await playgroundTab.click()
    await expect(playgroundTab).toHaveClass(/active/)
    // The persona has a welcomeMessage, so it renders as a welcome chat bubble
    await expect(page.locator('.persona-playground')).toBeVisible()
    await expect(page.locator('.chat-bubble--welcome')).toBeVisible()
  })

  test('creates a new persona via the modal form', async ({ page }) => {
    let createCalled = false
    let createdPayload: Record<string, unknown> = {}

    await setupPersonasPage(page, (url, method, body) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        if (createCalled) {
          return { body: JSON.stringify([...MOCK_PERSONAS, {
            id: 'persona-new',
            name: 'New Agent',
            description: null,
            systemPrompt: 'You are a new agent.',
            responseGuideline: null,
            welcomeMessage: null,
            promptTemplateId: null,
            icon: null,
            isDefault: false,
            isActive: true,
            createdAt: Date.now(),
            updatedAt: Date.now(),
          }]) }
        }
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      if (url.endsWith('/api/personas') && method === 'POST') {
        createCalled = true
        if (body) createdPayload = JSON.parse(body)
        return {
          status: 201,
          body: JSON.stringify({
            id: 'persona-new',
            ...createdPayload,
            isDefault: false,
            isActive: true,
            createdAt: Date.now(),
            updatedAt: Date.now(),
          }),
        }
      }
      if (url.includes('/api/personas/persona-new') && method === 'GET') {
        return {
          body: JSON.stringify({
            id: 'persona-new',
            ...createdPayload,
            isDefault: false,
            isActive: true,
            createdAt: Date.now(),
            updatedAt: Date.now(),
          }),
        }
      }
      if (url.includes('/api/prompt-templates') && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Click top-level "Create Persona" button
    await page.locator('.page-header .btn-primary').click()

    // Modal should open
    const modal = page.locator('.modal')
    await expect(modal).toBeVisible()
    await expect(modal.locator('.modal-title')).toContainText('페르소나 생성')

    // Fill in required fields
    await modal.locator('input[name="name"]').fill('New Agent')
    await modal.locator('textarea[name="systemPrompt"]').fill('You are a new agent.')

    // Submit
    await modal.locator('button[type="submit"]').click()

    // Verify create was called
    await expect.poll(() => createCalled).toBe(true)
    expect(createdPayload).toMatchObject({
      name: 'New Agent',
      systemPrompt: 'You are a new agent.',
    })
  })

  test('edits an existing persona via the edit modal', async ({ page }) => {
    let updateCalled = false
    let updatedPayload: Record<string, unknown> = {}

    await setupPersonasPage(page, (url, method, body) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      if (url.includes('/api/personas/persona-1') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS[0]) }
      }
      if (url.includes('/api/personas/persona-1') && method === 'PUT') {
        updateCalled = true
        if (body) updatedPayload = JSON.parse(body)
        return {
          body: JSON.stringify({ ...MOCK_PERSONAS[0], ...updatedPayload, updatedAt: Date.now() }),
        }
      }
      if (url.includes('/api/prompt-templates') && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Select persona via the date cell (name cell is inline-editable after PR #335)
    await page.locator('tr').filter({ hasText: 'Support Bot' }).locator('td').nth(1).click()
    await expect(page.locator('.detail-panel')).toBeVisible()

    // Click Edit button in the info tab
    await page.locator('.persona-info-actions .btn').filter({ hasText: '수정' }).click()

    // Edit modal opens
    const modal = page.locator('.modal')
    await expect(modal).toBeVisible()
    await expect(modal.locator('.modal-title')).toContainText('페르소나 수정')

    // The name field should be pre-populated
    const nameInput = modal.locator('input[name="name"]')
    await expect(nameInput).toHaveValue('Support Bot')

    // Change the name
    await nameInput.clear()
    await nameInput.fill('Support Bot v2')

    // Submit
    await modal.locator('button[type="submit"]').click()

    // Verify update was called
    await expect.poll(() => updateCalled).toBe(true)
    expect(updatedPayload).toMatchObject({
      name: 'Support Bot v2',
    })
  })

  test('deletes a persona with confirmation dialog', async ({ page }) => {
    let deleteCalled = false

    await setupPersonasPage(page, (url, method) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        if (deleteCalled) {
          return { body: JSON.stringify(MOCK_PERSONAS.filter(p => p.id !== 'persona-2')) }
        }
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      if (url.includes('/api/personas/persona-2') && method === 'DELETE') {
        deleteCalled = true
        return { status: 200, body: '{}' }
      }
      return { body: '[]' }
    })

    // Click the delete button on the Sales Bot row
    const salesRow = page.locator('tr').filter({ hasText: 'Sales Bot' })
    await salesRow.locator('.btn-danger').click()

    // Confirm dialog should appear
    const dialog = page.locator('.modal')
    await expect(dialog).toBeVisible()
    await expect(dialog).toContainText('"Sales Bot" 페르소나를 삭제할까요?')

    // Confirm deletion
    await dialog.getByRole('button', { name: /확인/i }).click()

    // Verify delete was called. The undoable-delete pattern fires the
    // network request after a 5s grace window, so the default 5s
    // expect.poll timeout is bumped here.
    await expect.poll(() => deleteCalled, { timeout: 10_000 }).toBe(true)
  })

  test('shows error state when API returns an error', async ({ page }) => {
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

      const url = requestUrl.pathname
      if (url.includes('/auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
        return
      }
      if (url.includes('/auth/login')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (url.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: CAPABILITY_ENDPOINTS }),
        })
        return
      }
      if (url.endsWith('/api/personas')) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Internal server error' }),
        })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/personas')

    // Error alert should be displayed with retry button (allow extra time for TanStack Query retries on 5xx)
    await expect(page.locator('.alert.alert-error')).toBeVisible({ timeout: 30000 })
    await expect(page.getByText('재시도', { exact: false })).toBeVisible()
  })

  test('shows "select a persona" message when no persona is selected', async ({ page }) => {
    await setupPersonasPage(page, (url, method) => {
      if (url.endsWith('/api/personas') && method === 'GET') {
        return { body: JSON.stringify(MOCK_PERSONAS) }
      }
      return { body: '[]' }
    })

    // When no persona is selected, the layout is collapsed (split-layout--collapsed)
    // and the right panel is hidden — only the left list is visible
    await expect(page.locator('.split-layout--collapsed')).toBeVisible()
    await expect(page.locator('.split-right')).toHaveCount(0)
  })
})
