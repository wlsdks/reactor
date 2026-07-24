import type { TFunction } from 'i18next'
import type { AdminRole } from '../types/navigation'
import { RELEASE_WORKFLOW_COMMAND_ACTIONS } from '../releaseWorkflow'

/**
 * Cross-page event used by Command Palette "create" actions.
 * Pages can listen for this and open their create modal when the
 * `feature` matches.
 */
export const COMMAND_CREATE_EVENT = 'cmd-palette:create'

export interface CommandCreateEventDetail {
  /** Feature identifier (e.g. 'persona', 'safety-rule'). */
  feature: string
}

/** Section under which the action is grouped in the palette UI. */
export type CommandActionSection = 'release' | 'navigate' | 'create' | 'action'

export interface CommandAction {
  /** Stable identifier, also used as React key. */
  id: string
  /** Section bucket for visual grouping. */
  section: CommandActionSection
  /** i18n key for the action title. */
  titleKey: string
  /** Optional i18n key for a one-line description. */
  descriptionKey?: string
  /** Extra non-translated keywords appended to the searchable text. */
  keywords?: string[]
  /** Optional ordered workflow step displayed before the title. */
  stepNumber?: number
  /** Hide a specialist shortcut until the operator enters a search query. */
  showByDefault?: boolean
  /** Run when the user invokes the action. */
  perform: () => void
  /** Optional gate; when it returns false, the action is filtered out. */
  when?: () => boolean
}

export interface ActionRegistryDeps {
  navigate: (path: string) => void
  /** Effective admin role for visibility gating. Undefined when unknown. */
  role: AdminRole | undefined
  /** Toggle the ADMIN "View as Manager" preview. */
  toggleViewAsManager: () => void
  /** Whether the toggle is available to the current user. */
  canToggleViewAs: boolean
}

/**
 * Keeps dynamically registered command action labels visible to the static
 * i18n verifier, which only recognizes literal translation call sites.
 */
export function markCommandPaletteActionKeysForI18nVerifier(t: TFunction): void {
  void t('commandPalette.sections.release')
  void t('commandPalette.search.scope.release')
  void t('commandPalette.search.scope.persona')
  void t('commandPalette.search.scope.prompt')
  void t('commandPalette.search.scope.feedback')
  void t('commandPalette.search.scope.audit')
  void t('commandPalette.search.scope.session')
  void t('commandPalette.actions.releaseWorkflow')
  void t('commandPalette.actions.releaseWorkflowDesc')
  void t('commandPalette.actions.releaseCockpit')
  void t('commandPalette.actions.releaseCockpitDesc')
  void t('commandPalette.actions.ragIngestion')
  void t('commandPalette.actions.ragIngestionDesc')
  void t('commandPalette.actions.ragLifecycle')
  void t('commandPalette.actions.ragLifecycleDesc')
  void t('commandPalette.actions.ragCitedAnswer')
  void t('commandPalette.actions.ragCitedAnswerDesc')
  void t('commandPalette.actions.feedbackPromotion')
  void t('commandPalette.actions.feedbackPromotionDesc')
  void t('commandPalette.actions.evalRegression')
  void t('commandPalette.actions.evalRegressionDesc')
  void t('commandPalette.actions.langsmithSync')
  void t('commandPalette.actions.langsmithSyncDesc')
  void t('commandPalette.actions.integrationSmoke')
  void t('commandPalette.actions.integrationSmokeDesc')
  void t('commandPalette.actions.slackGatewaySmoke')
  void t('commandPalette.actions.slackGatewaySmokeDesc')
  void t('commandPalette.actions.a2aProtocolSmoke')
  void t('commandPalette.actions.a2aProtocolSmokeDesc')
  void t('commandPalette.actions.providerSmoke')
  void t('commandPalette.actions.providerSmokeDesc')
}

/**
 * Dispatch the cross-page create event. Pages that want to react to
 * Command Palette "create" actions should attach a listener for
 * {@link COMMAND_CREATE_EVENT} and check `event.detail.feature`.
 */
export function dispatchCreateEvent(feature: string): void {
  if (typeof window === 'undefined') return
  const event = new CustomEvent<CommandCreateEventDetail>(COMMAND_CREATE_EVENT, {
    detail: { feature },
  })
  window.dispatchEvent(event)
}

function navigateAndCreate(
  navigate: (path: string) => void,
  path: string,
  feature: string,
): void {
  navigate(`${path}?create=1`)
  // Defer the event so pages mount their listener first on a fresh route.
  if (typeof window !== 'undefined') {
    window.setTimeout(() => dispatchCreateEvent(feature), 0)
  }
}

/**
 * Build the static action registry. The registry is rebuilt on every
 * palette open so role / dependency changes are reflected immediately.
 */
export function buildCommandActions(deps: ActionRegistryDeps): CommandAction[] {
  const { navigate, role, toggleViewAsManager, canToggleViewAs } = deps
  const isDevRole = role === 'ADMIN' || role === 'ADMIN_DEVELOPER'

  return [
    {
      id: 'create.persona',
      section: 'create',
      titleKey: 'commandPalette.actions.createPersona',
      descriptionKey: 'commandPalette.actions.createPersonaDesc',
      keywords: ['persona', '페르소나'],
      when: () => isDevRole,
      perform: () => navigateAndCreate(navigate, '/personas', 'persona'),
    },
    {
      id: 'create.safety-rule',
      section: 'create',
      titleKey: 'commandPalette.actions.createSafetyRule',
      descriptionKey: 'commandPalette.actions.createSafetyRuleDesc',
      keywords: ['safety', 'rule', '안전'],
      when: () => isDevRole,
      perform: () => navigateAndCreate(navigate, '/safety-rules', 'safety-rule'),
    },
    {
      id: 'create.scheduler-job',
      section: 'create',
      titleKey: 'commandPalette.actions.createSchedulerJob',
      descriptionKey: 'commandPalette.actions.createSchedulerJobDesc',
      keywords: ['scheduler', 'job', 'cron', '예약'],
      when: () => isDevRole,
      perform: () => navigateAndCreate(navigate, '/scheduler', 'scheduler-job'),
    },
    {
      id: 'create.mcp-server',
      section: 'create',
      titleKey: 'commandPalette.actions.createMcpServer',
      descriptionKey: 'commandPalette.actions.createMcpServerDesc',
      keywords: ['mcp', 'server', 'tool'],
      when: () => isDevRole,
      perform: () => navigateAndCreate(navigate, '/mcp-servers', 'mcp-server'),
    },
    {
      id: 'action.cache-invalidate',
      section: 'action',
      titleKey: 'commandPalette.actions.cacheInvalidate',
      descriptionKey: 'commandPalette.actions.cacheInvalidateDesc',
      keywords: ['cache', 'invalidate', 'health', '캐시'],
      perform: () => navigate('/health?action=cache-invalidate'),
    },
    {
      id: 'action.audit-export',
      section: 'action',
      titleKey: 'commandPalette.actions.auditExport',
      descriptionKey: 'commandPalette.actions.auditExportDesc',
      keywords: ['audit', 'export', 'csv', '감사'],
      when: () => isDevRole,
      perform: () => {
        navigate('/audit?action=export')
        if (typeof window !== 'undefined') {
          window.setTimeout(() => {
            window.dispatchEvent(new CustomEvent('cmd-palette:audit-export'))
          }, 0)
        }
      },
    },
    {
      id: 'navigate.feedback-followup',
      section: 'navigate',
      titleKey: 'commandPalette.actions.feedbackFollowupCtr',
      descriptionKey: 'commandPalette.actions.feedbackFollowupCtrDesc',
      keywords: ['slack', 'followup', 'ctr', 'feedback'],
      perform: () => navigate('/feedback#followup-ctr'),
    },
    ...RELEASE_WORKFLOW_COMMAND_ACTIONS.map((releaseAction) => ({
      id: releaseAction.id,
      section: 'release' as const,
      titleKey: releaseAction.titleKey,
      descriptionKey: releaseAction.descriptionKey,
      keywords: [
        ...releaseAction.keywords,
        ...(releaseAction.stepNumber ? [`step ${releaseAction.stepNumber}`, `${releaseAction.stepNumber}`] : []),
      ],
      stepNumber: releaseAction.stepNumber,
      showByDefault: 'showByDefault' in releaseAction
        ? releaseAction.showByDefault
        : true,
      when: () => isDevRole,
      perform: () => navigate(releaseAction.path),
    })),
    {
      id: 'navigate.tenant-analysis',
      section: 'navigate',
      titleKey: 'commandPalette.actions.tenantAnalysis',
      descriptionKey: 'commandPalette.actions.tenantAnalysisDesc',
      keywords: ['tenant', 'analysis', '테넌트'],
      perform: () => navigate('/tenants?tab=analysis'),
    },
    {
      id: 'action.toggle-dev-mode',
      section: 'action',
      titleKey: 'commandPalette.actions.toggleDevMode',
      descriptionKey: 'commandPalette.actions.toggleDevModeDesc',
      keywords: ['dev', 'manager', 'mode', 'view-as'],
      when: () => canToggleViewAs,
      perform: () => toggleViewAsManager(),
    },
    {
      id: 'navigate.dashboard',
      section: 'navigate',
      titleKey: 'commandPalette.actions.openDashboard',
      descriptionKey: 'commandPalette.actions.openDashboardDesc',
      keywords: ['dashboard', 'home', '대시보드'],
      perform: () => navigate('/'),
    },
    {
      id: 'navigate.health',
      section: 'navigate',
      titleKey: 'commandPalette.actions.openHealth',
      descriptionKey: 'commandPalette.actions.openHealthDesc',
      keywords: ['health', 'doctor', '진단'],
      perform: () => navigate('/health'),
    },
    {
      // Deep link to the Performance page's Tools segment so engineers can jump
      // straight to per-tool outcome counters without clicking through to the
      // tab. Dev-only because the surface is engineering-grade telemetry.
      id: 'navigate.performance-tools',
      section: 'navigate',
      titleKey: 'commandPalette.actions.openPerformanceTools',
      descriptionKey: 'commandPalette.actions.openPerformanceToolsDesc',
      keywords: ['performance', 'tools', 'tool', 'mcp', 'outcome', '도구', '성능'],
      when: () => isDevRole,
      perform: () => navigate('/performance?seg=tools'),
    },
  ]
}

/** Filter actions by the (optional) `when` gate. */
export function filterAvailableActions(actions: CommandAction[]): CommandAction[] {
  return actions.filter((a) => (a.when ? a.when() : true))
}

/**
 * Narrow the action list by a free-form query. Match is case-insensitive
 * against the (translated) title, description, action id, and any
 * supplied keywords.
 */
export function filterActionsByQuery(
  actions: CommandAction[],
  query: string,
  translate: (key: string) => string,
): CommandAction[] {
  const trimmed = query.trim().toLowerCase()
  if (!trimmed) return actions.filter((action) => action.showByDefault !== false)
  return actions.filter((action) => {
    const title = translate(action.titleKey).toLowerCase()
    const desc = action.descriptionKey ? translate(action.descriptionKey).toLowerCase() : ''
    const keywords = (action.keywords ?? []).join(' ').toLowerCase()
    return (
      title.includes(trimmed) ||
      desc.includes(trimmed) ||
      keywords.includes(trimmed) ||
      action.id.toLowerCase().includes(trimmed)
    )
  })
}
