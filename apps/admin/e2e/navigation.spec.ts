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
  '/api/error-report',
  '/api/feedback',
  '/api/intents',
  '/api/mcp/servers',
  '/api/mcp/security',
  '/api/ops/dashboard',
  '/api/ops/metrics/names',
  '/api/output-guard/rules',
  '/api/personas',
  '/api/proactive-channels',
  '/api/prompt-lab/experiments',
  '/api/prompt-templates',
  '/api/rag-ingestion/candidates',
  '/api/scheduler/jobs',
  '/api/sessions',
  '/api/slack/commands',
  '/api/slack/events',
  '/api/tool-policy',
]

async function setupAndNavigate(page: Page, path = '/') {
  // Set token + capabilities cache before page load (avoids extra API calls)
  await page.addInitScript((token: string) => {
    localStorage.setItem('reactor-admin-token', token)
    // Suppress onboarding tour shade so it doesn't intercept sidenav clicks
    // when the test starts at "/" (the only path that mounts the tour).
    localStorage.setItem('reactor-admin-v1-1-release-onboarding-completed', new Date().toISOString())
    const cache = {
      mode: 'manifest',
      endpoints: [
        '/api/admin/audits', '/api/admin/capabilities', '/api/approvals', '/api/auth/login',
        '/api/auth/me', '/api/auth/register', '/api/chat', '/api/documents', '/api/error-report',
        '/api/feedback', '/api/intents', '/api/mcp/servers', '/api/mcp/security',
        '/api/ops/dashboard', '/api/ops/metrics/names', '/api/output-guard/rules', '/api/personas',
        '/api/proactive-channels', '/api/prompt-lab/experiments', '/api/prompt-templates',
        '/api/rag-ingestion/candidates', '/api/scheduler/jobs', '/api/sessions',
        '/api/slack/commands', '/api/slack/events', '/api/tool-policy',
      ],
      timestamp: Date.now(),
    }
    sessionStorage.setItem('reactor-admin-feature-availability-v2', JSON.stringify(cache))
  }, MOCK_TOKEN)

  // Single route handler for ALL backend API calls (exact baseURL avoids matching source files)
  await page.route('**/*', async (route) => {
    const requestUrl = new URL(route.request().url())
    if (!requestUrl.pathname.startsWith('/api/')) {
      await route.continue()
      return
    }
    const url = requestUrl.toString()
    if (url.includes('/auth/me')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MOCK_USER) })
    } else if (url.includes('/auth/login')) {
      await route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ token: MOCK_TOKEN, user: MOCK_USER }) })
    } else if (url.includes('/admin/capabilities')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        generatedAt: Date.now(),
        source: 'playwright-mock',
        paths: MOCK_CAPABILITY_PATHS,
      }) })
    } else if (url.includes('/ops/dashboard')) {
      // Dashboard needs an object with specific shape
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        generatedAt: Date.now(),
        ragEnabled: false,
        mcp: { total: 0, statusCounts: {} },
        scheduler: {
          totalJobs: 0,
          enabledJobs: 0,
          runningJobs: 0,
          failedJobs: 0,
          attentionBacklog: 0,
          agentJobs: 0,
        },
        recentSchedulerExecutions: [],
        approvals: {
          pendingCount: 0,
        },
        responseTrust: {
          unverifiedResponses: 0,
          outputGuardRejected: 0,
          outputGuardModified: 0,
          boundaryFailures: 0,
        },
        employeeValue: {
          observedResponses: 0,
          groundedResponses: 0,
          groundedRatePercent: 0,
          blockedResponses: 0,
          interactiveResponses: 0,
          scheduledResponses: 0,
          answerModes: {},
          channels: [],
          lanes: [],
          toolFamilies: [],
          topMissingQueries: [],
        },
        recentTrustEvents: [],
        metrics: [],
      }) })
    } else if (
      (requestUrl.pathname === '/api/slack/commands' ||
        requestUrl.pathname === '/api/slack/events' ||
        requestUrl.pathname === '/api/error-report') &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({ status: 405, contentType: 'application/json', body: JSON.stringify({ error: 'Method not allowed' }) })
    } else if (url.includes('/mcp/servers')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    } else if (url.includes('/mcp/security') || url.includes('/tool-policy')) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ error: 'HTTP 404' }) })
    } else if (url.includes('/output-guard/rules/audits')) {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'socket hang up' }) })
    } else if (url.includes('/output-guard/rules')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
    }
  })

  await page.goto(path)
  // Wait for authenticated sidenav to appear (items may be icon-only when collapsed)
  await page.waitForSelector('.sidenav .sidenav-item', { timeout: 15000 })
}

test.describe('Navigation', () => {
  test('renders sidenav with nav items', async ({ page }) => {
    await setupAndNavigate(page)
    await expect(page.locator('.sidenav')).toBeVisible()
  })

  test('shows OPS nav item', async ({ page }) => {
    await setupAndNavigate(page)
    await expect(page.getByRole('link', { name: '대시보드' })).toBeAttached()
  })

  test('shows ALERT nav item', async ({ page }) => {
    await setupAndNavigate(page)
    await expect(page.getByRole('link', { name: '이슈' })).toBeAttached()
  })

  test('shows AI nav item', async ({ page }) => {
    await setupAndNavigate(page)
    await expect(page.getByRole('link', { name: '페르소나' })).toBeAttached()
  })

  test('navigating to /personas loads PersonaManager', async ({ page }) => {
    await setupAndNavigate(page)
    await page.getByRole('link', { name: '페르소나' }).click()
    await expect(page).toHaveURL(/\/personas/, { timeout: 10000 })
    await expect(page.locator('.page-title')).toBeVisible({ timeout: 10000 })
  })

  test('renders retro header with REACTOR brand', async ({ page }) => {
    await setupAndNavigate(page)
    await expect(page.locator('.app-header')).toContainText('Reactor')
  })

  test('renders global status strip in header on dashboard load', async ({ page }) => {
    await setupAndNavigate(page)
    // Strip is the persistent ambient status alongside the brand cluster.
    // The mocked dashboard has total=0 MCP, 0 approvals — only the
    // "last updated" chip is guaranteed to render. The strip itself must
    // mount so the structural promise ("데이터를 한 곳에") is visible.
    const strip = page.locator('.global-status-strip')
    await expect(strip).toBeAttached({ timeout: 10000 })
    await expect(strip.locator('[data-chip="last-updated"]')).toBeVisible()
    // approvals=0 should still render a chip pointing to /approvals
    await expect(strip.locator('[data-chip="approvals"]')).toBeVisible()
    await expect(strip.locator('[data-chip="approvals"]')).toHaveAttribute('href', '/approvals')
  })

  test('renders muted footer with console title and localized role', async ({ page }) => {
    await setupAndNavigate(page)
    const footer = page.locator('.app-footer')
    await expect(footer).toContainText('REACTOR 관리 콘솔')
    // Demo session is ADMIN → "최고 관리자" per auth.roleNames.ADMIN
    await expect(footer.locator('.app-footer-role')).toBeVisible()
  })

  test('active nav item has active class on dashboard', async ({ page }) => {
    await setupAndNavigate(page)
    const dashLink = page.locator('.sidenav a[href="/"]')
    await expect(dashLink).toHaveClass(/active/, { timeout: 5000 })
  })

  test('mcp servers page shows empty state and disabled bulk actions when registry is empty', async ({ page }) => {
    await setupAndNavigate(page, '/mcp-servers')

    await expect(page.getByRole('heading', { name: 'MCP 서버' })).toBeVisible()
    await expect(page.getByText('등록된 MCP 서버 없음')).toBeVisible()
    await expect(page.getByRole('button', { name: '미연결 서버 전체 연결' })).toBeDisabled()
    await expect(page.getByRole('button', { name: '긴급 전체 차단' })).toBeDisabled()
  })

  test('integrations page shows control plane probe diagnostics', async ({ page }) => {
    await setupAndNavigate(page, '/integrations')

    await expect(page.getByText('시스템 상태 점검')).toBeVisible()
    await expect(page.getByText('프로젝트 연결 상태')).toBeVisible()
    await expect(page.getByText('관리자 기능')).toBeVisible()
  })

  test('release operations views keep decision, boundary, and evidence addressable', async ({ page }) => {
    await setupAndNavigate(page, '/release#release-cockpit')

    const decisionTab = page.getByRole('tab', { name: '릴리즈 판단' })
    const boundaryTab = page.getByRole('tab', { name: '제품 경계' })
    const evidenceTab = page.getByRole('tab', { name: 'Evidence' })

    await expect(decisionTab).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText('태그 추천, blocker, warning 검토와 로컬 검증 상태를 기준으로 지금 내릴 결정을 확인합니다.')).toBeVisible()
    await expect(page.locator('[data-release-section="boundary"]:visible')).toHaveCount(0)

    await boundaryTab.click()
    await expect(page).toHaveURL(/\/release\?view=boundary#release-workflow$/)
    await expect(boundaryTab).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText('RAG 수집부터 근거 답변, feedback/eval 승격, LangSmith와 live smoke까지 제품 흐름을 단계별로 확인합니다.')).toBeVisible()
    await expect(page.locator('#release-workflow')).toBeVisible()
    await expect(page.locator('[data-release-section="decision"]:visible')).toHaveCount(0)

    await evidenceTab.click()
    await expect(page).toHaveURL(/\/release\?view=evidence#release-evidence$/)
    await expect(evidenceTab).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByText('readiness, LangSmith, RAG, feedback, Slack/A2A/provider smoke의 상세 리포트 계약을 검토합니다.')).toBeVisible()
    await expect(page.locator('#release-evidence')).toBeVisible()
    await expect(page.locator('[data-release-section="boundary"]:visible')).toHaveCount(0)
  })

  test('issues page shows centralized issue summary with topology map', async ({ page }) => {
    await setupAndNavigate(page, '/issues')

    await expect(page.getByText('전체 모듈의 시스템 상태 및 이슈 추적')).toBeVisible()
    // The page now uses a topology map with buttons instead of a table with links
    await expect(page.getByRole('button', { name: /심각/ })).toBeVisible()
  })
})
