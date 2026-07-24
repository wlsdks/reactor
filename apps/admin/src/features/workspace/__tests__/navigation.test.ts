import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { getRouteRequirements, ROUTE_REQUIREMENTS } from '../../capabilities/requirements'
import {
  getVisibleNavGroupsByRole,
  isRouteVisibleByRole,
} from '../navigation'
import {
  RELEASE_OPERATION_NAV_PATHS,
  RELEASE_WORKFLOW_COMMAND_ACTIONS,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'

function readKoreanTranslations(): unknown {
  return JSON.parse(readFileSync(resolve(process.cwd(), 'src/shared/i18n/ko.json'), 'utf8'))
}

function resolveTranslation(resource: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>((current, part) => (
      current && typeof current === 'object' && part in current
        ? (current as Record<string, unknown>)[part]
        : undefined
    ), resource)
}

describe('role-based navigation', () => {
  it('uses role visibility as the only navigation policy', () => {
    const workspaceContext = resolve(process.cwd(), 'src/features/workspace/context.tsx')
    const navigationSource = readFileSync(
      resolve(process.cwd(), 'src/features/workspace/navigation.ts'),
      'utf8',
    )
    const navigationTypes = readFileSync(
      resolve(process.cwd(), 'src/shared/types/navigation.ts'),
      'utf8',
    )
    const bootstrapSource = readFileSync(resolve(process.cwd(), 'src/main.tsx'), 'utf8')

    expect(existsSync(workspaceContext)).toBe(false)
    expect(navigationSource).not.toContain('WorkspaceMode')
    expect(navigationSource).not.toContain('audience:')
    expect(navigationTypes).not.toContain('Audience')
    expect(navigationTypes).not.toContain('audience:')
    expect(bootstrapSource).not.toContain('reactor-admin-workspace-mode')
  })

  it('returns groups with all items for the developer role when routes are available', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const allItems = groups.flatMap(g => g.items)
    expect(allItems.length).toBeGreaterThan(10)
  })

  it('returns 8 manager-visible items covering Today / Monitoring (no traces) / Usage / Tenants', () => {
    // PR6a role-based filter: ADMIN_MANAGER sees the routes flagged
    // visibleTo: 'all' — see CLAUDE.md "Role-Based Visibility" section.
    const groups = getVisibleNavGroupsByRole('ADMIN_MANAGER', () => true)
    const allItems = groups.flatMap(g => g.items)
    expect(allItems).toHaveLength(8)
    const paths = allItems.map(item => item.path)
    expect(paths).toContain('/')
    expect(paths).toContain('/health')
    expect(paths).toContain('/issues')
    expect(paths).toContain('/approvals')
    expect(paths).toContain('/sessions')
    expect(paths).toContain('/feedback')
    expect(paths).toContain('/usage')
    expect(paths).toContain('/tenants')
    // Developer-only paths must not appear
    expect(paths).not.toContain('/traces')
    expect(paths).not.toContain('/audit')
    expect(paths).not.toContain('/personas')
  })

  it('filters items by route availability function', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', (path) => path === '/' || path === '/personas')
    const allItems = groups.flatMap(g => g.items)
    const paths = allItems.map(item => item.path)
    expect(paths).toContain('/')
    expect(paths).toContain('/personas')
    expect(paths).not.toContain('/prompts')
  })

  it('keeps the release operations handoff when capability filtering hides other groups', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => false)
    expect(groups.map((g) => g.titleKey)).toEqual([
      'nav.group.releaseOps',
      'nav.group.administration',
    ])
    expect(groups[0]?.items.map((i) => i.path)).toEqual(RELEASE_OPERATION_NAV_PATHS)
    expect(groups[1]?.items.map((i) => i.path)).toEqual(['/tenants', '/settings'])
  })

  it('keeps the tenant operations workspace discoverable with a partial capability manifest', () => {
    const developerGroups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => false)
    const managerGroups = getVisibleNavGroupsByRole('ADMIN_MANAGER', () => false)

    expect(developerGroups.flatMap((group) => group.items).map((item) => item.path)).toContain('/tenants')
    expect(managerGroups.flatMap((group) => group.items).map((item) => item.path)).toContain('/tenants')
  })

  it('excludes removed sidebar items and safety sub-routes', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const paths = groups.flatMap(g => g.items).map(item => item.path)
    expect(paths).not.toContain('/platform-admin')
    expect(paths).not.toContain('/rbac')
    expect(paths).not.toContain('/intents')
    expect(paths).not.toContain('/proactive-channels')
    expect(paths).not.toContain('/output-guard')
    expect(paths).not.toContain('/tool-policy')
    expect(paths).not.toContain('/input-guard')
    expect(paths).not.toContain('/tenant-admin')
  })

  it('keeps removed sidebar items as redirects, not orphaned product routes', () => {
    const routerSource = readFileSync(resolve(process.cwd(), 'src/router.tsx'), 'utf8')
    const removedDirectRoutes = [
      '/platform-admin',
      '/rbac',
      '/intents',
      '/proactive-channels',
      '/output-guard',
      '/tool-policy',
      '/input-guard',
      '/tenant-admin',
      '/retention',
    ]

    for (const route of removedDirectRoutes) {
      expect(routerSource).not.toContain(`routePath="${route}"`)
      expect(ROUTE_REQUIREMENTS).not.toHaveProperty(route)
    }
  })

  it('removes legacy page wrappers for removed direct routes', () => {
    const removedPageFiles = [
      'src/pages/IntentsPage.tsx',
      'src/pages/OutputGuardPage.tsx',
      'src/pages/ProactiveChannelsPage.tsx',
      'src/pages/PromptLabPage.tsx',
      'src/pages/RetentionPage.tsx',
      'src/pages/PromptsPage.tsx',
      'src/pages/ToolPolicyPage.tsx',
      'src/pages/InputGuardPage.tsx',
      'src/features/platform-admin/ui/PlatformAdminManager.tsx',
    ]

    for (const pageFile of removedPageFiles) {
      expect(existsSync(resolve(process.cwd(), pageFile))).toBe(false)
    }
  })

  it('exposes /metrics-ingestion under the Dev Tools group (J-8 reclassification)', () => {
    // Stage J-8: metrics ingestion (debug tester) was previously hidden from
    // the sidebar, leaving operators unable to discover it. Re-grouped under
    // Dev Tools alongside debug-replay so its purpose (developer-only debug
    // tooling) is unambiguous.
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const devTools = groups.find((g) => g.titleKey === 'nav.group.devTools')
    expect(devTools).toBeDefined()
    const devToolsPaths = devTools?.items.map((i) => i.path) ?? []
    expect(devToolsPaths).toContain('/metrics-ingestion')
    expect(devToolsPaths).toContain('/debug-replay')
  })

  it('hides /metrics-ingestion from ADMIN_MANAGER (developer-only debug tool)', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_MANAGER', () => true)
    const paths = groups.flatMap((g) => g.items).map((i) => i.path)
    expect(paths).not.toContain('/metrics-ingestion')
  })

  it('returns groups with items covering key routes', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const allItems = groups.flatMap(g => g.items)
    const paths = allItems.map(item => item.path)
    expect(paths).toContain('/') // dashboard
    expect(paths).toContain('/issues') // issues
    expect(paths).toContain('/personas') // personas
    expect(paths).toContain('/prompt-studio') // prompt-studio
    expect(paths).toContain('/mcp-servers') // mcp-servers
    // /mcp-security removed — absorbed into /mcp-servers
    expect(paths).toContain('/safety-rules') // safety-rules (input + output guards + tool policy)
    expect(paths).toContain('/scheduler') // scheduler
    expect(paths).toContain('/approvals') // approvals
  })

  it('ADMIN_MANAGER receives manager-specific 3-group taxonomy (todayGlance / usage / organization)', () => {
    // PR W1-D: manager sees its own coherent grouping, not a stripped subset
    // of the developer 7-group taxonomy.
    const groups = getVisibleNavGroupsByRole('ADMIN_MANAGER', () => true)
    const groupKeys = groups.map(g => g.titleKey)
    expect(groupKeys).toEqual([
      'nav.managerGroup.todayGlance',
      'nav.managerGroup.usage',
      'nav.managerGroup.organization',
    ])
    // Developer group keys must not leak into the manager view.
    expect(groupKeys).not.toContain('nav.group.today')
    expect(groupKeys).not.toContain('nav.group.aiConfig')
    expect(groupKeys).not.toContain('nav.group.safetyPolicy')
    expect(groupKeys).not.toContain('nav.group.releaseOps')
    expect(groupKeys).not.toContain('nav.group.monitoring')
    expect(groupKeys).not.toContain('nav.group.analytics')
    expect(groupKeys).not.toContain('nav.group.administration')
    expect(groupKeys).not.toContain('nav.group.devTools')
  })

  it('manager 3-group taxonomy assigns the 8 manager items to the expected groups', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_MANAGER', () => true)
    const groupMap = new Map(groups.map(g => [g.titleKey, g.items.map(i => i.path)]))
    expect(groupMap.get('nav.managerGroup.todayGlance')).toEqual([
      '/', '/health', '/issues', '/approvals',
    ])
    expect(groupMap.get('nav.managerGroup.usage')).toEqual([
      '/sessions', '/feedback', '/usage',
    ])
    expect(groupMap.get('nav.managerGroup.organization')).toEqual(['/tenants'])
  })

  it('groups the v1.1 release workflow screens under Release operations', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const releaseOps = groups.find((g) => g.titleKey === 'nav.group.releaseOps')
    expect(releaseOps).toBeDefined()
    expect(releaseOps?.descriptionKey).toBe('nav.group.releaseOpsDesc')
    expect(releaseOps?.items.map((i) => i.path)).toEqual(RELEASE_OPERATION_NAV_PATHS)
    expect(releaseOps?.items.map((i) => i.path)).toEqual([
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      RELEASE_WORKFLOW_PATHS_BY_ID.ingest,
      RELEASE_WORKFLOW_PATHS_BY_ID.rag,
      RELEASE_WORKFLOW_PATHS_BY_ID.feedback,
      RELEASE_WORKFLOW_PATHS_BY_ID.evals,
      RELEASE_WORKFLOW_PATHS_BY_ID.integrations,
      RELEASE_WORKFLOW_PATHS_BY_ID.provider,
    ])
  })

  it('keeps release operation deep links available as a stable release handoff', () => {
    const availableBaseRoutes = new Set(['/', '/feedback', '/models'])
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', (path) => {
      const basePath = path.split(/[?#]/, 1)[0] || '/'
      return availableBaseRoutes.has(basePath)
    })

    const releaseOps = groups.find((g) => g.titleKey === 'nav.group.releaseOps')
    expect(releaseOps?.items.map((i) => i.path)).toEqual(RELEASE_OPERATION_NAV_PATHS)
  })

  it('keeps the release operation workflow discoverable when capability checks are partial', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', (path) => {
      const basePath = path.split(/[?#]/, 1)[0] || '/'
      return basePath === '/' || basePath === '/feedback' || basePath === '/integrations'
    })

    const releaseOps = groups.find((g) => g.titleKey === 'nav.group.releaseOps')
    expect(releaseOps?.items.map((i) => i.path)).toEqual(RELEASE_OPERATION_NAV_PATHS)
  })

  it('resolves capability requirements for release operation deep links', () => {
    expect(getRouteRequirements(RELEASE_WORKFLOW_PATHS_BY_ID.ingest)).toEqual(
      getRouteRequirements('/documents'),
    )
    expect(getRouteRequirements(RELEASE_WORKFLOW_PATHS_BY_ID.rag)).toEqual(
      getRouteRequirements('/rag-cache'),
    )
    expect(getRouteRequirements(RELEASE_WORKFLOW_PATHS_BY_ID.integrations)).toEqual(
      getRouteRequirements('/integrations'),
    )
    expect(getRouteRequirements(RELEASE_WORKFLOW_PATHS_BY_ID.provider)).toEqual(
      getRouteRequirements('/models'),
    )
  })

  it('marks release workflow sidebar items with stable step numbers', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const releaseOps = groups.find((g) => g.titleKey === 'nav.group.releaseOps')
    expect(releaseOps?.items.map((i) => i.releaseStepNumber)).toEqual([1, 2, 3, 4, 5, 6, 7])
  })

  it('uses release workflow descriptions for release operation navigation', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const releaseOps = groups.find((g) => g.titleKey === 'nav.group.releaseOps')
    expect(releaseOps?.items.map((i) => i.description)).toEqual([
      'nav.help.releaseOperations',
      'dashboard.releaseWorkflow.ingestDesc',
      'dashboard.releaseWorkflow.ragDesc',
      'dashboard.releaseWorkflow.feedbackDesc',
      'dashboard.releaseWorkflow.evalsDesc',
      'dashboard.releaseWorkflow.integrationsDesc',
      'dashboard.releaseWorkflow.providerDesc',
    ])
  })

  it('ADMIN and ADMIN_DEVELOPER continue to see the developer 8-group taxonomy', () => {
    const adminGroups = getVisibleNavGroupsByRole('ADMIN', () => true)
    const devGroups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true)
    const adminKeys = adminGroups.map(g => g.titleKey)
    const devKeys = devGroups.map(g => g.titleKey)
    // Both roles see the developer taxonomy, with v1.1 release workflow
    // screens grouped separately from generic AI config and dev tools.
    expect(adminKeys).toContain('nav.group.today')
    expect(adminKeys).toContain('nav.group.aiConfig')
    expect(adminKeys).toContain('nav.group.releaseOps')
    expect(adminKeys).toContain('nav.group.safetyPolicy')
    expect(adminKeys).toContain('nav.group.monitoring')
    expect(adminKeys).toContain('nav.group.analytics')
    expect(adminKeys).toContain('nav.group.administration')
    expect(adminKeys).toContain('nav.group.devTools')
    expect(devKeys).toEqual(adminKeys)
    // No manager-specific groups leak into developer views.
    expect(adminKeys).not.toContain('nav.managerGroup.todayGlance')
    expect(devKeys).not.toContain('nav.managerGroup.usage')
  })

  it('has Korean translations for every visible navigation metadata key', () => {
    const ko = readKoreanTranslations()
    const groups = [
      ...getVisibleNavGroupsByRole('ADMIN_DEVELOPER', () => true),
      ...getVisibleNavGroupsByRole('ADMIN_MANAGER', () => true),
    ]
    const keys = new Set<string>()

    for (const group of groups) {
      keys.add(group.titleKey)
      if (group.descriptionKey) keys.add(group.descriptionKey)
      for (const item of group.items) {
        keys.add(item.label)
        if (item.description) keys.add(item.description)
      }
    }

    for (const key of keys) {
      const translation = resolveTranslation(ko, key)
      expect(translation, key).toEqual(expect.any(String))
      expect(translation, key).not.toBe(key)
    }
  })

  it('keeps release command palette copy localized around the v1.1 workflow', () => {
    const ko = readKoreanTranslations()

    expect(resolveTranslation(ko, 'commandPalette.sections.release')).toBe('릴리즈 운영')
    for (const action of RELEASE_WORKFLOW_COMMAND_ACTIONS) {
      const title = resolveTranslation(ko, action.titleKey)
      const description = resolveTranslation(ko, action.descriptionKey)
      expect(typeof title).toBe('string')
      expect(typeof description).toBe('string')
      expect(title).not.toBe(action.titleKey)
      expect(description).not.toBe(action.descriptionKey)
    }
    expect(resolveTranslation(ko, 'commandPalette.actions.ragCitedAnswer')).toBe('RAG 근거 답변 열기')
    expect(resolveTranslation(ko, 'commandPalette.actions.integrationSmokeDesc'))
      .toBe('Slack, A2A, provider smoke_run과 필수/누락 리포트 evidence를 확인합니다.')
    expect(resolveTranslation(ko, 'commandPalette.actions.providerSmoke')).toBe('Provider smoke evidence 열기')
  })

  it('keeps release page help localized around the v1.1 workflow handoff', () => {
    const ko = readKoreanTranslations()
    const dashboardHelp = resolveTranslation(ko, 'dashboardPage.help')
    const ragHelp = resolveTranslation(ko, 'ragCachePage.helpOverlay')
    const integrationsHelp = resolveTranslation(ko, 'integrationsPage.helpOverlay')
    const evalsHelp = resolveTranslation(ko, 'evalsPage.help')
    const modelsHelp = resolveTranslation(ko, 'modelsPage.help')

    expect(dashboardHelp).toEqual(expect.arrayContaining([
      expect.stringContaining('readiness 필수/누락 리포트'),
      expect.stringContaining('requiredReports'),
    ]))
    expect(ragHelp).toEqual(expect.arrayContaining([
      expect.stringContaining('문서 검색, 답변 확인, 답변 검토'),
      expect.stringContaining('참고 문서'),
      expect.stringContaining('수집 기준'),
    ]))
    expect(integrationsHelp).toEqual(expect.arrayContaining([
      expect.stringContaining('smoke_run'),
      expect.stringContaining('A2A peer'),
      expect.stringContaining('readiness aggregate'),
    ]))
    expect(evalsHelp).toEqual(expect.arrayContaining([
      expect.stringContaining('LangSmith에 빠짐없이 저장'),
      expect.stringContaining('평가 자료 묶음에 포함'),
      expect.stringContaining('실제로 시험'),
    ]))
    expect(modelsHelp).toEqual(expect.arrayContaining([
      expect.stringContaining('실제로 답하고 사용량이 기록'),
      expect.stringContaining('로컬 Ollama 모델'),
      expect.stringContaining('출시 상태를 새로고침'),
    ]))
  })
})
