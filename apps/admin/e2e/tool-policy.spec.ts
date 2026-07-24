import { expect, test } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const CAPABILITY_PATHS = [
  '/api/admin/capabilities',
  '/api/admin/input-guard/pipeline',
  '/api/admin/input-guard/rules/{id}',
  '/api/auth/login',
  '/api/auth/me',
  '/api/output-guard/rules',
  '/api/tool-policy',
]

function buildPolicyState() {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    effective: {
      enabled: true,
      writeToolNames: ['write_file', 'apply_patch'],
      denyWriteChannels: ['commentary'],
      allowWriteToolNamesInDenyChannels: ['apply_patch'],
      allowWriteToolNamesByChannel: {
        summary: ['write_file'],
      },
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710003600000,
    },
    stored: {
      enabled: true,
      writeToolNames: ['write_file'],
      denyWriteChannels: ['commentary'],
      allowWriteToolNamesInDenyChannels: [],
      allowWriteToolNamesByChannel: {},
      denyWriteMessage: 'Denied',
      createdAt: 1710000000000,
      updatedAt: 1710000000000,
    },
  }
}

test.describe('/tool-policy operator console', () => {
  test('shows a recovery runbook when the contract returns 404 on first load', async ({ page }) => {
    await page.route('**/*', async (route) => {
      const requestUrl = new URL(route.request().url())
      if (!requestUrl.pathname.startsWith('/api/')) {
        await route.continue()
        return
      }

      const url = requestUrl.toString()

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
            paths: CAPABILITY_PATHS,
          }),
        })
        return
      }
      if (requestUrl.pathname === '/api/tool-policy') {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Not found' }),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: paths,
        timestamp: Date.now(),
      }))
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

    await page.goto('/tool-policy')

    await expect(page.getByText(/정책 엔드포인트를 사용할 수 없어요/)).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('정책 엔드포인트 오류')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('heading', { name: '문제 해결 가이드' })).toBeVisible()
  })

  test('renders readiness and drift details when policy data loads', async ({ page }) => {
    await page.addInitScript(({ paths, token }: { paths: string[]; token: string }) => {
      localStorage.setItem('reactor-admin-token', token)
      sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
        mode: 'manifest',
        endpoints: paths,
        timestamp: Date.now(),
      }))
    }, { paths: CAPABILITY_PATHS, token: MOCK_TOKEN })

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
            paths: CAPABILITY_PATHS,
          }),
        })
        return
      }
      if (requestUrl.pathname === '/api/tool-policy' && method === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(buildPolicyState()),
        })
        return
      }

      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    })

    await page.goto('/tool-policy')

    await expect(page.getByRole('heading', { name: '도구 정책 준비도' })).toBeVisible()
    await expect(page.getByText('설정 차이')).toBeVisible()
    await expect(page.getByText('정책 편집기')).toBeVisible()
    await expect(page.getByText('차단 채널 예외 도구')).toBeVisible()
  })
})
