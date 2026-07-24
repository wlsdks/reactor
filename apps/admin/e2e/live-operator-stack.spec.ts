import { expect, test, type Locator, type Page } from '@playwright/test'

const LIVE_ADMIN_EMAIL = process.env.PLAYWRIGHT_LIVE_ADMIN_EMAIL || 'admin@example.com'
const LIVE_ADMIN_PASSWORD = process.env.PLAYWRIGHT_LIVE_ADMIN_PASSWORD || 'admin1234'

const copy = {
  dashboardHeading: localizedExact('운영 센터', 'Operations Center'),
  readyServers: localizedContains('운영 가능 서버: 2', 'Ready Servers: 2'),
  attentionServers: localizedContains('주의 필요 서버: 0', 'Needs Attention: 0'),
  systemTopology: localizedExact('시스템 토폴로지', 'System Topology'),
  integrationsHeading: localizedExact('시스템 연결', 'System Connections'),
  projectConnections: localizedExact('프로젝트 연결 상태', 'Project Connection Status'),
  registeredStatusConnected: localizedContains('등록 상태: CONNECTED', 'Registry Status: CONNECTED'),
  preflightWarnZero: localizedContains('Preflight WARN: 0', 'Preflight WARN: 0'),
  mcpServersHeading: localizedExact('도구 서버', 'Tool Servers'),
  registryHeadline: localizedContains('등록 2 · 연결 2 · 미연결 0', 'Inventory 2 · Connected 2 · Disconnected 0'),
  recoverAttentionServers: localizedExact('복구 대상 서버 재연결', 'Recover Attention Servers'),
  configReadiness: localizedExact('구성 준비도', 'Config Readiness'),
  noWarnings: localizedExact('현재 경고/실패 항목이 없습니다.', 'No warnings or failures right now.'),
  allowedSwaggerSources: localizedContains(
    '허용 Swagger source 이름(줄바꿈 구분)',
    'Allowed Swagger source names (one per line)',
  ),
  allowedJiraProjects: localizedContains(
    '허용 Jira 프로젝트 키(줄바꿈 구분)',
    'Allowed Jira project keys (one per line)',
  ),
  allowedConfluenceSpaces: localizedContains(
    '허용 Confluence 스페이스 키(줄바꿈 구분)',
    'Allowed Confluence space keys (one per line)',
  ),
  allowedBitbucketRepositories: localizedContains(
    '허용 Bitbucket 저장소(줄바꿈 구분)',
    'Allowed Bitbucket repositories (one per line)',
  ),
} as const

test.describe('live operator stack smoke', () => {
  test.skip(!process.env.PLAYWRIGHT_LIVE_STACK, 'Set PLAYWRIGHT_LIVE_STACK=1 to run live operator smoke checks.')

  test('shows both MCP servers as production-ready across key operator views', async ({ page }) => {
    const consoleErrors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error') {
        consoleErrors.push(message.text())
      }
    })

    await login(page)
    consoleErrors.length = 0

    await expect(page.getByRole('heading', { name: copy.dashboardHeading })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: copy.systemTopology })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(copy.readyServers)).toBeVisible()
    await expect(page.getByText(copy.attentionServers)).toBeVisible()
    await expect(page.getByText('Atlassian MCP').first()).toBeVisible()
    await expect(page.getByText('Swagger MCP').first()).toBeVisible()
    await expect(page.getByText(copy.registeredStatusConnected)).toHaveCount(2)
    await expect(page.getByText(copy.preflightWarnZero)).toHaveCount(2)

    await page.goto('/integrations')
    await expect(page.getByRole('heading', { name: copy.integrationsHeading })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: copy.projectConnections })).toBeVisible()
    await expect(page.getByText('Atlassian MCP').first()).toBeVisible()
    await expect(page.getByText('Swagger MCP').first()).toBeVisible()
    await expect(page.getByText(copy.registeredStatusConnected)).toHaveCount(2)
    await expect(page.getByText(copy.preflightWarnZero)).toHaveCount(2)

    await page.goto('/mcp-servers')
    await expect(page.getByRole('heading', { name: copy.mcpServersHeading })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByText(copy.registryHeadline)).toBeVisible()
    await expect(page.getByRole('button', { name: copy.recoverAttentionServers })).toBeDisabled()

    await openRegistryServerDetail(page, 'swagger')
    await expect(page.locator('.split-right').getByRole('heading', { name: /^swagger$/i })).toBeVisible()
    await expect(page.getByRole('heading', { name: copy.configReadiness })).toBeVisible()
    await expect(page.getByText(copy.noWarnings)).toBeVisible()
    await expect(formTextboxByLabel(page, copy.allowedSwaggerSources)).toHaveValue('petstore-public')

    await openRegistryServerDetail(page, 'atlassian')
    await expect(page.locator('.split-right').getByRole('heading', { name: /^atlassian$/i })).toBeVisible()
    await expect(formTextboxByLabel(page, copy.allowedJiraProjects)).toHaveValue('DEV\nINFRA\nJAR')
    await expect(formTextboxByLabel(page, copy.allowedConfluenceSpaces)).toHaveValue('DEV')
    await expect(formTextboxByLabel(page, copy.allowedBitbucketRepositories)).toHaveValue('jarvis\njarvis-infrastructure')

    await page.goto('/issues')
    await expect(page.getByRole('heading', { name: localizedExact('이슈 센터', 'Issue Center') })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('heading', { name: localizedExact('이슈 요약', 'Issue Summary') })).toBeVisible()
    await expect(page.getByRole('link', { name: localizedExact('콘솔 열기', 'Open Console') }).first()).toBeVisible()

    await page.waitForTimeout(500)
    expect(consoleErrors).toEqual([])
  })
})

async function login(page: Page) {
  await page.goto('/login')
  await expect(page.locator('#email')).toBeVisible({ timeout: 15_000 })

  await page.locator('#email').fill(LIVE_ADMIN_EMAIL)
  await page.locator('#password').fill(LIVE_ADMIN_PASSWORD)
  await page.locator('button[type="submit"]').click()

  await expect(page).not.toHaveURL(/\/login/, { timeout: 15_000 })
  await expect(page.getByRole('heading', { name: copy.dashboardHeading })).toBeVisible({ timeout: 15_000 })
}

async function openRegistryServerDetail(page: Page, serverName: string) {
  const serverRow = page.getByRole('row').filter({
    has: page.getByRole('cell', { name: new RegExp(`^${escapeRegex(serverName)}$`, 'i') }),
  }).first()
  await expect(serverRow).toBeVisible()
  await serverRow.click()
}

function formTextboxByLabel(page: Page, label: RegExp): Locator {
  return page.locator('.form-group').filter({ hasText: label }).getByRole('textbox')
}

function localizedExact(korean: string, english: string): RegExp {
  return new RegExp(`^(?:${escapeRegex(korean)}|${escapeRegex(english)})$`)
}

function localizedContains(korean: string, english: string): RegExp {
  return new RegExp(`(?:${escapeRegex(korean)}|${escapeRegex(english)})`)
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
