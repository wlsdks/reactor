import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/auth/login',
  '/api/auth/me',
  '/api/prompt-templates',
]

const TEMPLATES = [
  {
    id: 'tpl-support',
    name: 'Customer Support Greeting',
    description: 'Friendly opening line for support sessions',
    createdAt: 1714000000000,
    updatedAt: 1714003600000,
  },
  {
    id: 'tpl-sales',
    name: 'Sales Pitch v2',
    description: 'Outbound sales follow-up template',
    createdAt: 1714007200000,
    updatedAt: 1714010800000,
  },
]

const TEMPLATE_DETAIL_SUPPORT = {
  id: 'tpl-support',
  name: 'Customer Support Greeting',
  description: 'Friendly opening line for support sessions',
  createdAt: 1714000000000,
  updatedAt: 1714003600000,
  activeVersion: {
    id: 'ver-support-2',
    templateId: 'tpl-support',
    version: 2,
    content: 'You are a friendly support agent. Keep replies short.',
    status: 'ACTIVE',
    changeLog: 'Tone refresh',
    createdAt: 1714003600000,
  },
  versions: [
    {
      id: 'ver-support-2',
      templateId: 'tpl-support',
      version: 2,
      content: 'You are a friendly support agent. Keep replies short.',
      status: 'ACTIVE',
      changeLog: 'Tone refresh',
      createdAt: 1714003600000,
    },
    {
      id: 'ver-support-1',
      templateId: 'tpl-support',
      version: 1,
      content: 'Hello, how can I help today?',
      status: 'ARCHIVED',
      changeLog: 'Initial draft',
      createdAt: 1713996400000,
    },
  ],
}

test.describe('/prompts template manager', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem(
        'reactor-admin-feature-availability-v2',
        JSON.stringify({
          mode: 'manifest',
          endpoints: paths,
          timestamp: Date.now(),
        }),
      )
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url())
      if (!requestUrl.pathname.startsWith('/api/')) {
        await route.continue()
        return
      }

      const pathname = requestUrl.pathname

      if (pathname.includes('/auth/me')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(MOCK_USER),
        })
        return
      }
      if (pathname.includes('/auth/login')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }),
        })
        return
      }
      if (pathname.includes('/admin/capabilities')) {
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
      if (pathname === '/api/prompt-templates') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(TEMPLATES),
        })
        return
      }
      if (pathname === '/api/prompt-templates/tpl-support') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(TEMPLATE_DETAIL_SUPPORT),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '[]',
      })
    })

    await page.goto('/prompts')
  })

  test('renders the prompts header and the seeded template rows', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '프롬프트' })).toBeVisible()

    // Both seeded template names appear in the list table.
    await expect(page.getByText('Customer Support Greeting')).toBeVisible()
    await expect(page.getByText('Sales Pitch v2')).toBeVisible()
  })

  test('exposes the create-template action button in the page header', async ({ page }) => {
    // PromptsManager renders both a header CTA and (when empty) an EmptyState
    // CTA. With seeded templates only the header button exists, so this is
    // an unambiguous match.
    await expect(page.getByRole('button', { name: '템플릿 생성' })).toBeVisible()
  })

  test('opens the detail panel with version history when a template row is clicked', async ({ page }) => {
    await page.getByText('Customer Support Greeting').click()

    // Detail header reuses the template name as an h2.
    await expect(page.getByRole('heading', { level: 2, name: 'Customer Support Greeting' })).toBeVisible()
    // The active version section header is rendered as h3 "버전".
    await expect(page.getByRole('heading', { level: 3, name: '버전' })).toBeVisible()
    // The new-version action becomes available once a template is selected.
    await expect(page.getByRole('button', { name: '초안 버전 추가' })).toBeVisible()
  })

  test('shows the create-template modal with the name + description fields when the header CTA is pressed', async ({ page }) => {
    await page.getByRole('button', { name: '템플릿 생성' }).click()

    // Modal is rendered as role=dialog with the create title.
    await expect(page.getByRole('dialog', { name: '템플릿 생성' })).toBeVisible()
    // Inputs are wired through htmlFor / id, so getByLabel is reliable here.
    await expect(page.getByLabel('이름')).toBeVisible()
    await expect(page.getByLabel('설명')).toBeVisible()
  })
})
