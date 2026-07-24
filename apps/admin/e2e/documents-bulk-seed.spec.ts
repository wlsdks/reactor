import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

/**
 * E2E coverage for the policy-RAG bulk-seed flow on the Documents page.
 *
 * Three flows are exercised:
 *  - Paste-JSON success (single entry, modal closes after seed).
 *  - Manual fieldarray (add/remove + focus management).
 *  - Partial-success (BE returns fewer keys than requested → modal stays open).
 */

const MOCK_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
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

interface SeedHandlerOptions {
  /** Override the seed-policy response. When omitted, returns success-all. */
  seedResponse?: { documentCount: number; chunkCount: number; keys: string[]; durationMs: number }
}

async function setupDocumentsPage(page: Page, options: SeedHandlerOptions = {}) {
  await page.addInitScript(
    ({ token, paths }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem(
        'reactor-admin-feature-availability-v2',
        JSON.stringify({
          mode: 'manifest',
          endpoints: paths,
          timestamp: Date.now(),
        }),
      )
    },
    { token: MOCK_TOKEN, paths: MOCK_CAPABILITY_PATHS },
  )

  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }

    const url = requestUrl.toString()
    const pathname = requestUrl.pathname

    if (url.includes('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(MOCK_USER),
      })
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

    if (pathname === '/api/admin/rag/seed-policy') {
      const seedResponse = options.seedResponse ?? {
        documentCount: 1,
        chunkCount: 4,
        keys: ['k1'],
        durationMs: 200,
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(seedResponse),
      })
      return
    }

    if (pathname === '/api/rag-ingestion/candidates') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
      return
    }

    if (pathname === '/api/rag-ingestion/policy') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          configEnabled: true,
          dynamicEnabled: true,
          stored: null,
          effective: {
            enabled: true,
            requireReview: true,
            allowedChannels: [],
            minQueryChars: 1,
            minResponseChars: 1,
            blockedPatterns: [],
            createdAt: Date.now(),
            updatedAt: Date.now(),
          },
        }),
      })
      return
    }

    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })

  await page.goto('/documents')
  await expect(page.getByRole('heading', { name: '문서', exact: true })).toBeVisible()
}

test.describe('/documents bulk-seed flow', () => {
  test('exposes the bulk-seed button in the page header', async ({ page }) => {
    await setupDocumentsPage(page)
    await expect(
      page.getByRole('button', { name: /정책 일괄 시드/ }),
    ).toBeVisible()
  })

  test('paste JSON → preview → submit success path closes the modal', async ({ page }) => {
    await setupDocumentsPage(page, {
      seedResponse: {
        documentCount: 1,
        chunkCount: 4,
        keys: ['k1'],
        durationMs: 200,
      },
    })

    await page.getByRole('button', { name: /정책 일괄 시드/ }).click()

    const dialog = page.getByRole('dialog', { name: /정책 문서 일괄 시드/ })
    await expect(dialog).toBeVisible()

    const textarea = dialog.getByLabel(/JSON 입력/)
    await textarea.fill(JSON.stringify([{ key: 'k1', title: 'T1', content: 'C1' }]))

    // Preview row appears once the debounced parser runs.
    await expect(dialog.getByText('k1')).toBeVisible({ timeout: 2000 })

    const submit = dialog.getByRole('button', { name: /1개 항목 시드/ })
    await expect(submit).toBeEnabled()
    await submit.click()

    await expect(dialog).toBeHidden({ timeout: 5000 })
  })

  test('partial success keeps the modal open with a status announcement', async ({ page }) => {
    await setupDocumentsPage(page, {
      // 2 entries requested, BE returns only 1 key — partial success.
      seedResponse: {
        documentCount: 1,
        chunkCount: 4,
        keys: ['k1'],
        durationMs: 200,
      },
    })

    await page.getByRole('button', { name: /정책 일괄 시드/ }).click()
    const dialog = page.getByRole('dialog', { name: /정책 문서 일괄 시드/ })

    await dialog.getByLabel(/JSON 입력/).fill(
      JSON.stringify([
        { key: 'k1', title: 'T1', content: 'C1' },
        { key: 'k2', title: 'T2', content: 'C2' },
      ]),
    )

    const submit = dialog.getByRole('button', { name: /2개 항목 시드/ })
    await expect(submit).toBeEnabled({ timeout: 2000 })
    await submit.click()

    // Polite live region announces the 1/2 partial result.
    await expect(page.getByTestId('live-announcer-polite')).toContainText(/1\/2/)
    await expect(dialog).toBeVisible()
  })

  test('manual tab — add/remove entries and focus moves to the new key input', async ({ page }) => {
    await setupDocumentsPage(page)
    await page.getByRole('button', { name: /정책 일괄 시드/ }).click()
    const dialog = page.getByRole('dialog', { name: /정책 문서 일괄 시드/ })

    await dialog.getByRole('tab', { name: /수동 입력/ }).click()
    await dialog.getByRole('button', { name: /수동 항목 추가/ }).click()

    // Focus moves to the new entry's key input.
    const keyInput = dialog.getByLabel(/^키$/)
    await expect(keyInput).toBeFocused()
    await expect(dialog.getByRole('group', { name: /항목 1/ })).toBeVisible()

    // Add a second entry, then remove the first.
    await dialog.getByRole('button', { name: /수동 항목 추가/ }).click()
    await expect(dialog.getByRole('group').nth(1)).toBeVisible()

    await dialog.getByRole('button', { name: /1번 항목 제거/ }).click()
    await expect(dialog.getByRole('group')).toHaveCount(1)
  })
})
