import { test, expect, type Page } from '@playwright/test'
import { MOCK_TOKEN, MOCK_USER } from './helpers'

const MOCK_CAPABILITY_PATHS = [
  '/api/admin/audits',
  '/api/admin/capabilities',
  '/api/admin/platform/cache/stats',
  '/api/admin/platform/cache/invalidate',
  '/api/admin/platform/vectorstore/stats',
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

const MOCK_CACHE_STATS = {
  enabled: true,
  semanticEnabled: true,
  totalExactHits: 1250,
  totalSemanticHits: 340,
  totalMisses: 480,
  hitRate: 0.768,
  config: {
    ttlMinutes: 60,
    maxSize: 10000,
    similarityThreshold: 0.85,
    maxCandidates: 5,
    cacheableTemperature: 0.3,
  },
}

const MOCK_VECTOR_STORE_STATS = {
  available: true,
  documentCount: 1523,
}

// /api/rag-ingestion/policy returns RagPolicyState (configEnabled, dynamicEnabled,
// effective: RagPolicy, stored: RagPolicy | null) — see src/features/rag-cache/types.ts
const MOCK_RAG_POLICY = {
  configEnabled: true,
  dynamicEnabled: true,
  effective: {
    enabled: true,
    requireReview: true,
    allowedChannels: ['slack', 'web'],
    minQueryChars: 20,
    minResponseChars: 50,
    blockedPatterns: ['password', 'secret'],
  },
  stored: null,
}

const MOCK_SEARCH_RESULTS = [
  {
    id: 'doc-1',
    content: 'Rate limits are configured per-service.',
    metadata: { source: 'docs' },
    score: 0.91,
  },
  {
    id: 'doc-2',
    content: 'The Jira integration supports issue creation.',
    metadata: { source: 'knowledge_base' },
    score: 0.82,
  },
]

async function setupRagCachePage(
  page: Page,
  handleApi: (url: string, method: string, pathname: string) => { status?: number; body: string } | null,
) {
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify({
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits', '/api/admin/capabilities', '/api/admin/platform/cache/stats',
        '/api/admin/platform/cache/invalidate', '/api/admin/platform/vectorstore/stats',
        '/api/approvals', '/api/auth/login', '/api/auth/me', '/api/auth/register',
        '/api/chat', '/api/documents', '/api/feedback', '/api/intents', '/api/mcp/servers',
        '/api/ops/dashboard', '/api/output-guard/rules', '/api/personas',
        '/api/prompt-lab/experiments', '/api/prompt-templates', '/api/rag-ingestion/candidates',
        '/api/scheduler/jobs', '/api/sessions', '/api/tool-policy',
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

  await page.goto('/rag-cache')
  await expect(page.getByRole('heading', { name: 'RAG & 캐시' })).toBeVisible()
}

function defaultApiHandler(url: string, method: string, pathname: string): { status?: number; body: string } | null {
  if (pathname === '/api/admin/platform/cache/stats' && method === 'GET') {
    return { body: JSON.stringify(MOCK_CACHE_STATS) }
  }
  if (pathname === '/api/admin/platform/vectorstore/stats' && method === 'GET') {
    return { body: JSON.stringify(MOCK_VECTOR_STORE_STATS) }
  }
  if (pathname === '/api/rag-ingestion/policy' && method === 'GET') {
    return { body: JSON.stringify(MOCK_RAG_POLICY) }
  }
  // Smart-default tab needs pendingCandidates resolved as [] so manager
  // settles on 'rag' tab (no candidates → user-priority #2). Without this
  // mock, the candidates query stays undefined and tab flickers/lands on
  // unexpected default.
  if (pathname === '/api/rag-ingestion/candidates' && method === 'GET') {
    return { body: JSON.stringify([]) }
  }
  // CacheRuntimeControls reads single runtime settings — return 404 so the
  // hook's .catch(() => null) path triggers and readBool() falls back.
  // Without this, the route falls through to '[]' default and readBool
  // crashes on [].value.toLowerCase().
  if (pathname.startsWith('/api/admin/settings/') && method === 'GET') {
    return { status: 404, body: JSON.stringify({ error: 'Not found' }) }
  }
  return null
}

test.describe('/rag-cache page', () => {
  test('loads with four tabs and smart-defaults to RAG management', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)

    // All 4 tabs should be visible
    await expect(page.getByRole('tab', { name: '시맨틱 캐시' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '검토 대기' })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'RAG 관리' })).toBeVisible()
    await expect(page.getByRole('tab', { name: '분석' })).toBeVisible()

    // With 0 pending candidates, smart-default lands on 'rag' tab
    await expect(page.getByRole('tab', { name: 'RAG 관리', selected: true })).toBeVisible()
  })

  test('cache tab displays statistics cards', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()

    // Stat cards should show computed values — scope to .stat-card-value
    // since the insight bar also renders the hit-rate above
    await expect(page.locator('.stat-card-label', { hasText: '적중률' })).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '76.8%' })).toBeVisible()
    await expect(page.locator('.stat-card-label', { hasText: '정확 적중' })).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '1250' })).toBeVisible()
    await expect(page.locator('.stat-card-label', { hasText: '시맨틱 적중' })).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '340' })).toBeVisible()
    await expect(page.locator('.stat-card-label', { hasText: '미스' })).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '480' })).toBeVisible()
  })

  test('cache tab displays configuration table', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()

    await expect(page.getByRole('heading', { name: '설정' })).toBeVisible()
    await expect(page.getByText('TTL (분)')).toBeVisible()
    await expect(page.locator('.rag-config-card__value', { hasText: '60' })).toBeVisible()
    await expect(page.getByText('최대 항목 수')).toBeVisible()
    // toLocaleString() formats with thousands separator
    await expect(page.locator('.rag-config-card__value', { hasText: '10,000' })).toBeVisible()
    await expect(page.getByText('유사도 임계값')).toBeVisible()
    await expect(page.locator('.rag-config-card__value', { hasText: '0.85' })).toBeVisible()
  })

  test('cache invalidation flow shows confirmation dialog and completes', async ({ page }) => {
    let invalidateCalled = false

    await setupRagCachePage(page, (url, method, pathname) => {
      const base = defaultApiHandler(url, method, pathname)
      if (base) return base

      if (pathname === '/api/admin/platform/cache/invalidate' && method === 'POST') {
        invalidateCalled = true
        return { body: JSON.stringify({ invalidated: true, message: 'Cache invalidated' }) }
      }
      return null
    })
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()

    // Click invalidate button
    await page.getByRole('button', { name: '전체 캐시 무효화' }).click()

    // Modal opens with title "캐시 전체 무효화" + irreversible warning
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText('이 작업은 되돌릴 수 없습니다')).toBeVisible()

    // The execute button stays disabled until the operator types the
    // confirmation token (INVALIDATE) into the input. Fill it so the
    // danger button becomes enabled.
    await page.getByRole('dialog').getByRole('textbox').fill('INVALIDATE')

    // Confirm the action — modal uses execute action label "전체 무효화 실행"
    await page.getByRole('button', { name: '전체 무효화 실행' }).click()

    await expect.poll(() => invalidateCalled).toBe(true)
  })

  test('cache invalidation can be cancelled', async ({ page }) => {
    let invalidateCalled = false

    await setupRagCachePage(page, (url, method, pathname) => {
      const base = defaultApiHandler(url, method, pathname)
      if (base) return base

      if (pathname === '/api/admin/platform/cache/invalidate' && method === 'POST') {
        invalidateCalled = true
        return { body: JSON.stringify({ invalidated: true, message: 'Cache invalidated' }) }
      }
      return null
    })
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()

    // Click invalidate button
    await page.getByRole('button', { name: '전체 캐시 무효화' }).click()

    // Modal opens
    await expect(page.getByRole('dialog')).toBeVisible()

    // Cancel the action — modal cancel button (use exact match — page may also
    // have other 취소 buttons elsewhere; modal-actions houses both)
    await page.getByRole('dialog').getByRole('button', { name: '취소' }).click()

    // Dialog should disappear and invalidate should not be called
    await expect(page.getByRole('dialog')).toBeHidden()
    expect(invalidateCalled).toBe(false)
  })

  test('tab switching shows RAG Management tab with vector store stats', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)

    // Switch to RAG tab
    await page.getByRole('tab', { name: 'RAG 관리' }).click()

    // Vector store stats should be visible (StatCard renders labels uppercased)
    await expect(page.locator('.stat-card-label', { hasText: '벡터 스토어' })).toBeVisible()
    await expect(page.getByText('사용 가능')).toBeVisible()
    await expect(page.locator('.stat-card-label', { hasText: '인덱싱된 문서' })).toBeVisible()
    // Insight bar renders the documentCount as '1,523' (toLocaleString); the
    // StatCard renders the bare number '1523'. Scope to .stat-card-value to
    // disambiguate.
    await expect(page.locator('.stat-card-value', { hasText: '1523' })).toBeVisible()
  })

  test('RAG tab shows policy summary', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)

    // Switch to RAG tab (smart-default already lands here, but be explicit)
    await page.getByRole('tab', { name: 'RAG 관리' }).click()

    // RAG Policy section should be visible (label appears in StatCard + form label)
    await expect(page.getByText('RAG 수집 정책').first()).toBeVisible()
    await expect(page.getByText('검토 필수').first()).toBeVisible()
    await expect(page.getByText('허용 채널')).toBeVisible()
    // allowedChannels are rendered as .chip spans inside ChipInput
    await expect(page.locator('.chip', { hasText: 'slack' })).toBeVisible()
    await expect(page.locator('.chip', { hasText: 'web' })).toBeVisible()
  })

  test('RAG tab quick search returns results', async ({ page }) => {
    let searchCalled = false

    await setupRagCachePage(page, (url, method, pathname) => {
      const base = defaultApiHandler(url, method, pathname)
      if (base) return base

      if (pathname === '/api/documents/search' && method === 'POST') {
        searchCalled = true
        return { body: JSON.stringify(MOCK_SEARCH_RESULTS) }
      }
      return null
    })

    // Switch to RAG tab
    await page.getByRole('tab', { name: 'RAG 관리' }).click()

    // Quick Search section should be visible
    await expect(page.getByText('빠른 검색')).toBeVisible()

    // Fill search and submit. Use exact match to avoid colliding with the
    // header CommandPalette trigger ("페이지 검색...") which contains "검색".
    await page.getByPlaceholder('유사도 검색을 테스트할 쿼리를 입력하세요...').fill('rate limits')
    await page.getByRole('button', { name: '검색', exact: true }).click()

    await expect.poll(() => searchCalled).toBe(true)
    await expect(page.getByText('2건의 결과')).toBeVisible()
  })

  test('RAG tab quick search shows empty state when no results', async ({ page }) => {
    await setupRagCachePage(page, (url, method, pathname) => {
      const base = defaultApiHandler(url, method, pathname)
      if (base) return base

      if (pathname === '/api/documents/search' && method === 'POST') {
        return { body: JSON.stringify([]) }
      }
      return null
    })

    // Switch to RAG tab
    await page.getByRole('tab', { name: 'RAG 관리' }).click()

    // Fill search and submit. Use exact match to avoid colliding with the
    // header CommandPalette trigger ("페이지 검색...") which contains "검색".
    await page.getByPlaceholder('유사도 검색을 테스트할 쿼리를 입력하세요...').fill('nonexistent query')
    await page.getByRole('button', { name: '검색', exact: true }).click()

    const quickSearch = page.locator('.detail-panel', { has: page.getByRole('heading', { name: '빠른 검색' }) })
    await expect(quickSearch.getByText('아직 데이터가 없어요')).toBeVisible()
  })

  test('RAG tab has link to manage documents page', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)

    // Switch to RAG tab
    await page.getByRole('tab', { name: 'RAG 관리' }).click()

    // Manage Documents card has role="link" (RagCacheManager.tsx:359)
    await expect(page.getByRole('link', { name: /문서 관리/ })).toBeVisible()
  })

  test('handles cache stats API error gracefully', async ({ page }) => {
    await setupRagCachePage(page, (_url, method, pathname) => {
      if (pathname === '/api/admin/platform/cache/stats' && method === 'GET') {
        return { status: 500, body: JSON.stringify({ error: 'Internal server error' }) }
      }
      if (pathname === '/api/admin/platform/vectorstore/stats' && method === 'GET') {
        return { body: JSON.stringify(MOCK_VECTOR_STORE_STATS) }
      }
      if (pathname === '/api/rag-ingestion/policy' && method === 'GET') {
        return { body: JSON.stringify(MOCK_RAG_POLICY) }
      }
      if (pathname === '/api/rag-ingestion/candidates' && method === 'GET') {
        return { body: JSON.stringify([]) }
      }
      // CacheRuntimeControls reads settings — return 404 so the catch returns
      // null and readBool() falls back to true. Without this, the route falls
      // through to '[]' and readBool([].value) throws.
      if (pathname.startsWith('/api/admin/settings/') && method === 'GET') {
        return { status: 404, body: JSON.stringify({ error: 'Not found' }) }
      }
      return null
    })
    // Switch to cache tab to surface the cache stat cards (default lands on 'rag')
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()

    // The page should still load — stat cards show fallback values (StatCard renders labels uppercased)
    // Allow extra time for TanStack Query retries (retry count < 2 for 5xx errors)
    await expect(page.locator('.stat-card-label', { hasText: '적중률' })).toBeVisible({ timeout: 15000 })
    await expect(page.locator('.stat-card-value', { hasText: '-' }).first()).toBeVisible()
  })

  test('tab switching back and forth preserves tab state', async ({ page }) => {
    await setupRagCachePage(page, defaultApiHandler)

    // Smart-default lands on RAG tab (0 pending candidates)
    await expect(page.locator('.stat-card-label', { hasText: '벡터 스토어' })).toBeVisible()

    // Switch to cache tab
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()
    await expect(page.locator('.stat-card-label', { hasText: '적중률' })).toBeVisible()

    // Switch back to RAG tab
    await page.getByRole('tab', { name: 'RAG 관리' }).click()
    await expect(page.locator('.stat-card-label', { hasText: '벡터 스토어' })).toBeVisible()

    // Switch to cache tab again
    await page.getByRole('tab', { name: '시맨틱 캐시' }).click()
    await expect(page.locator('.stat-card-label', { hasText: '적중률' })).toBeVisible()
    await expect(page.locator('.stat-card-value', { hasText: '76.8%' })).toBeVisible()
  })
})
