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

const MOCK_TEMPLATES = [
  {
    id: 'template-sales',
    name: 'Sales Assistant Prompt',
    description: 'Sales-facing versioned prompt',
    createdAt: 1704067200000,
    updatedAt: 1704153600000,
  },
  {
    id: 'template-support',
    name: 'Support Prompt v2',
    description: 'Customer support versioned prompt with empathy guidelines',
    createdAt: 1704412800000,
    updatedAt: 1704844800000,
  },
]

function makeTemplateDetail(template: typeof MOCK_TEMPLATES[0], versions: unknown[] = []) {
  return {
    ...template,
    activeVersion: versions.find((v: unknown) => (v as { status: string }).status === 'ACTIVE') ?? {
      id: 'version-1',
      templateId: template.id,
      version: 1,
      content: `Prompt content for ${template.name}`,
      status: 'ACTIVE',
      changeLog: 'Initial rollout',
      createdAt: 1704153600000,
    },
    versions: versions.length > 0 ? versions : [
      {
        id: 'version-1',
        templateId: template.id,
        version: 1,
        content: `Prompt content for ${template.name}`,
        status: 'ACTIVE',
        changeLog: 'Initial rollout',
        createdAt: 1704153600000,
      },
    ],
  }
}

async function setupPromptStudioPage(
  page: Page,
  handleApi: (pathname: string, method: string, body?: string | null) => { status?: number; body: string },
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

    const pathname = requestUrl.pathname
    const method = route.request().method()

    if (pathname.includes('/auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
      return
    }
    if (pathname.includes('/auth/login')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
      return
    }
    if (pathname.includes('/admin/capabilities')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: CAPABILITY_ENDPOINTS }),
      })
      return
    }

    let reqBody: string | null = null
    try { reqBody = await route.request().postData() } catch { /* no body */ }

    const response = handleApi(pathname, method, reqBody)
    await route.fulfill({
      status: response.status ?? 200,
      contentType: 'application/json',
      body: response.body,
    })
  })

  await page.goto('/prompt-studio')
  await expect(page.locator('.page-title')).toBeVisible({ timeout: 15000 })
}


/* ================================================================== */
/*  Test suite                                                        */
/* ================================================================== */

test.describe('/prompt-studio page', () => {

  test('loads and displays template list', async ({ page }) => {
    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Page title is visible
    await expect(page.locator('.page-title')).toContainText('프롬프트 스튜디오')

    // Template list shows both templates
    await expect(page.getByText('Sales Assistant Prompt')).toBeVisible()
    await expect(page.getByText('Support Prompt v2')).toBeVisible()

    // Template count header
    await expect(page.getByText(/프롬프트 스튜디오 · 2/)).toBeVisible()
  })

  test('shows empty state when no templates exist', async ({ page }) => {
    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    await expect(page.getByText('프롬프트 템플릿 없음')).toBeVisible()
    await expect(page.getByText('템플릿 생성')).toBeVisible()
  })

  test('shows "select a template" message when none selected', async ({ page }) => {
    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    await expect(page.getByText('템플릿을 선택하면 상세 정보를 볼 수 있습니다')).toBeVisible()
  })

  test('selects a template and shows detail with version tab', async ({ page }) => {
    const detail = makeTemplateDetail(MOCK_TEMPLATES[0])

    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'GET') {
        return { body: JSON.stringify(detail) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Click the template in the list
    await page.getByText('Sales Assistant Prompt').click()

    // Detail header shows the template name
    await expect(page.locator('.detail-header h2')).toContainText('Sales Assistant Prompt')

    // Active badge is visible in the detail header (StatusBadge uses 'badge' class)
    await expect(page.locator('.detail-header .badge').filter({ hasText: 'ACTIVE' })).toBeVisible()

    // Version tab is shown by default with version content
    await expect(page.getByText('Prompt content for Sales Assistant Prompt')).toBeVisible()

    // "Create Draft Version" button is visible
    await expect(page.getByText('초안 버전 추가')).toBeVisible()
  })

  test('creates a new template via the modal', async ({ page }) => {
    let createCalled = false
    let createdPayload: Record<string, unknown> = {}

    await setupPromptStudioPage(page, (pathname, method, body) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname === '/api/prompt-templates' && method === 'POST') {
        createCalled = true
        if (body) createdPayload = JSON.parse(body)
        return {
          status: 201,
          body: JSON.stringify({
            id: 'template-new',
            ...createdPayload,
            createdAt: Date.now(),
            updatedAt: Date.now(),
          }),
        }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Click "New Template" button at the bottom of the template list
    await page.locator('.template-list-create-btn').click()

    // Modal opens
    const modal = page.locator('.modal')
    await expect(modal).toBeVisible()
    await expect(modal.locator('.modal-title')).toContainText('템플릿 생성')

    // Fill in the form
    await modal.locator('#template-name').fill('My New Template')
    await modal.locator('#template-description').fill('A template for testing')

    // Submit the form
    await modal.locator('.btn-primary').click()

    // Verify create was called
    await expect.poll(() => createCalled).toBe(true)
    expect(createdPayload).toMatchObject({
      name: 'My New Template',
      description: 'A template for testing',
    })
  })

  test('shows Versions, Experiments, and Settings as collapsible sections', async ({ page }) => {
    const detail = makeTemplateDetail(MOCK_TEMPLATES[0])

    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'GET') {
        return { body: JSON.stringify(detail) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Select template
    await page.getByText('Sales Assistant Prompt').click()
    await expect(page.locator('.detail-header h2')).toContainText('Sales Assistant Prompt')

    // Settings (templateInfo) and Versions (body) are defaultOpen — visible without any clicks
    await expect(page.locator('.collapsible-header').filter({ hasText: '템플릿 정보' })).toBeVisible()
    await expect(page.locator('.collapsible-header').filter({ hasText: '본문 / 변수' })).toBeVisible()

    // Settings section content (template id + delete button) visible since defaultOpen
    await expect(page.getByText('template-sales')).toBeVisible()
    await expect(page.locator('.btn-danger')).toBeVisible()

    // Experiments is closed by default — open it then assert empty-state content
    await page.locator('.collapsible-header').filter({ hasText: '실험 / 평가' }).click()
    await expect(page.getByText('아직 실험이 없습니다')).toBeVisible()
  })

  test('deletes a template from the Settings tab with confirmation', async ({ page }) => {
    let deleteCalled = false
    const detail = makeTemplateDetail(MOCK_TEMPLATES[0])

    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        if (deleteCalled) {
          return { body: JSON.stringify(MOCK_TEMPLATES.filter(t => t.id !== 'template-sales')) }
        }
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'GET') {
        return { body: JSON.stringify(detail) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'DELETE') {
        deleteCalled = true
        return { status: 200, body: '{}' }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Select template
    await page.getByText('Sales Assistant Prompt').click()
    await expect(page.locator('.detail-header h2')).toContainText('Sales Assistant Prompt')

    // Settings ("템플릿 정보") section is defaultOpen — delete button already visible
    // Click Delete button in settings section
    await page.locator('.detail-actions .btn-danger').click()

    // First confirmation dialog (from SettingsTab)
    const settingsDialog = page.locator('[role="dialog"]').last()
    await expect(settingsDialog).toBeVisible()
    await expect(settingsDialog).toContainText('"Sales Assistant Prompt" 템플릿과 모든 버전을 삭제할까요?')
    await settingsDialog.getByRole('button', { name: /확인/i }).click()

    // Second confirmation dialog (from parent PromptStudioManager)
    const parentDialog = page.locator('[role="dialog"]').last()
    await expect(parentDialog).toBeVisible({ timeout: 5000 })
    await parentDialog.getByRole('button', { name: /확인/i }).click()

    // Verify delete was called. The undoable-delete pattern delays the
    // network request by 5s so the default poll timeout is bumped.
    await expect.poll(() => deleteCalled, { timeout: 10_000 }).toBe(true)
  })

  test('creates a new version via the version modal', async ({ page }) => {
    let versionCreateCalled = false
    let versionPayload: Record<string, unknown> = {}
    const detail = makeTemplateDetail(MOCK_TEMPLATES[0])

    await setupPromptStudioPage(page, (pathname, method, body) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales/versions') && method === 'POST') {
        versionCreateCalled = true
        if (body) versionPayload = JSON.parse(body)
        return {
          status: 201,
          body: JSON.stringify({
            id: 'version-2',
            templateId: 'template-sales',
            version: 2,
            content: versionPayload.content ?? '',
            status: 'DRAFT',
            changeLog: versionPayload.changeLog ?? '',
            createdAt: Date.now(),
          }),
        }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'GET') {
        return { body: JSON.stringify(detail) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Select template
    await page.getByText('Sales Assistant Prompt').click()
    await expect(page.locator('.detail-header h2')).toContainText('Sales Assistant Prompt')

    // Click "Create Draft Version" button
    await page.getByText('초안 버전 추가').click()

    // Version creation modal opens
    const modal = page.locator('.modal')
    await expect(modal).toBeVisible()

    // Content textarea should be pre-filled with the active version content
    const contentTextarea = modal.locator('#version-content')
    await expect(contentTextarea).toHaveValue('Prompt content for Sales Assistant Prompt')

    // Modify content and add changelog
    await contentTextarea.clear()
    await contentTextarea.fill('Updated prompt with better instructions.')
    await modal.locator('#version-changelog').fill('Improved clarity and tone')

    // Save
    await modal.locator('.btn-primary').click()

    // Verify version create was called
    await expect.poll(() => versionCreateCalled).toBe(true)
    expect(versionPayload).toMatchObject({
      content: 'Updated prompt with better instructions.',
      changeLog: 'Improved clarity and tone',
    })
  })

  test('shows error state when template list fails to load', async ({ page }) => {
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
      const pathname = requestUrl.pathname
      if (pathname.includes('/auth/me')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ generatedAt: Date.now(), source: 'playwright-mock', paths: CAPABILITY_ENDPOINTS }),
        })
        return
      }
      if (pathname === '/api/prompt-templates') {
        await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'Internal server error' }) })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/prompt-studio')

    // Error alert with retry button
    await expect(page.locator('.alert.alert-error')).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('재시도', { exact: false })).toBeVisible()
  })

  test('experiments tab shows empty onboarding when no experiments exist', async ({ page }) => {
    const detail = makeTemplateDetail(MOCK_TEMPLATES[0])

    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'GET') {
        return { body: JSON.stringify(detail) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Select template
    await page.getByText('Sales Assistant Prompt').click()
    await expect(page.locator('.detail-header h2')).toBeVisible()

    // Open the Experiments collapsible section (closed by default)
    await page.locator('.collapsible-header').filter({ hasText: '실험 / 평가' }).click()

    // Empty state with onboarding steps
    await expect(page.getByText('아직 실험이 없습니다')).toBeVisible()
    await expect(page.getByText('비교할 버전 선택')).toBeVisible()
    await expect(page.getByText('우승 버전 활성화')).toBeVisible()
  })

  test('version tab shows version list with status badges and actions', async ({ page }) => {
    const versions = [
      {
        id: 'version-1',
        templateId: 'template-sales',
        version: 1,
        content: 'Original system prompt content',
        status: 'ARCHIVED',
        changeLog: 'Initial rollout',
        createdAt: 1704153600000,
      },
      {
        id: 'version-2',
        templateId: 'template-sales',
        version: 2,
        content: 'Updated system prompt with improved tone',
        status: 'ACTIVE',
        changeLog: 'Improved tone and clarity',
        createdAt: 1704240000000,
      },
      {
        id: 'version-3',
        templateId: 'template-sales',
        version: 3,
        content: 'Draft version with experimental changes',
        status: 'DRAFT',
        changeLog: 'Experimental changes for A/B test',
        createdAt: 1704326400000,
      },
    ]
    const detail = makeTemplateDetail(MOCK_TEMPLATES[0], versions)

    await setupPromptStudioPage(page, (pathname, method) => {
      if (pathname === '/api/prompt-templates' && method === 'GET') {
        return { body: JSON.stringify(MOCK_TEMPLATES) }
      }
      if (pathname.includes('/api/prompt-templates/template-sales') && method === 'GET') {
        return { body: JSON.stringify(detail) }
      }
      if (pathname === '/api/prompt-lab/experiments' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      return { body: '[]' }
    })

    // Select template
    await page.getByText('Sales Assistant Prompt').click()
    await expect(page.locator('.detail-header h2')).toBeVisible()

    // Three version items visible
    await expect(page.locator('.version-item')).toHaveCount(3)

    // Status badges (StatusBadge uses 'badge' class)
    await expect(page.locator('.version-item .badge').filter({ hasText: 'ARCHIVED' })).toBeVisible()
    await expect(page.locator('.version-item .badge').filter({ hasText: 'ACTIVE' })).toBeVisible()
    await expect(page.locator('.version-item .badge').filter({ hasText: 'DRAFT' })).toBeVisible()

    // Active version has an "Archive" button, Draft/Archived have "Activate" buttons
    await expect(page.getByText('보관', { exact: true })).toBeVisible()
    // DRAFT and ARCHIVED versions should have Activate buttons (2 of them)
    const activateButtons = page.locator('.version-item .btn-primary').filter({ hasText: '활성화' })
    await expect(activateButtons).toHaveCount(2)

    // Changelogs are visible (scoped to .version-item — activity log section also renders these strings in DOM)
    await expect(page.locator('.version-item').getByText('Initial rollout')).toBeVisible()
    await expect(page.locator('.version-item').getByText('Improved tone and clarity')).toBeVisible()
  })
})
