import {
  LayoutDashboard, AlertCircle, CheckSquare, HeartPulse,
  User, FileText, BookOpen, Shield, Database,
  MessageSquare, ThumbsUp, ClipboardList,
  Server, Search, Link, Clock, BarChart3, Orbit, Activity, Bug, Send,
  DollarSign, ShieldCheck, Cpu, Building2, Settings, Rocket,
} from 'lucide-react'
import type { TFunction } from 'i18next'
import type { AdminRole, NavGroup, NavItem, NavItemVisibility } from '../../shared/types/navigation'
import {
  RELEASE_OPERATION_NAV_PATHS_BY_ID,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../shared/releaseWorkflow'

export type { NavGroup, NavItem } from '../../shared/types/navigation'

/**
 * Keeps dynamically registered navigation labels visible to the static i18n
 * verifier, which only recognizes literal translation call sites.
 */
export function markNavigationKeysForI18nVerifier(t: TFunction): void {
  void t('nav.dashboard')
  void t('nav.health')
  void t('nav.issues')
  void t('nav.approvals')
  void t('nav.personas')
  void t('nav.promptStudio')
  void t('nav.reactorUniverse')
  void t('nav.releaseCockpit')
  void t('nav.releaseOperations')
  void t('nav.documents')
  void t('nav.ragCache')
  void t('nav.feedback')
  void t('nav.evals')
  void t('nav.integrations')
  void t('nav.models')
  void t('nav.safetyRules')
  void t('nav.inputGuard')
  void t('nav.accessControl')
  void t('nav.sessions')
  void t('nav.traces')
  void t('nav.audit')
  void t('nav.performance')
  void t('nav.usage')
  void t('nav.tenants')
  void t('nav.settings')
  void t('nav.mcpServers')
  void t('nav.chatInspector')
  void t('nav.scheduler')
  void t('nav.metricsIngestion')
  void t('nav.debugReplay')
  void t('nav.group.today')
  void t('nav.group.aiConfig')
  void t('nav.group.releaseOps')
  void t('nav.group.releaseOpsDesc')
  void t('nav.group.safetyPolicy')
  void t('nav.group.monitoring')
  void t('nav.group.analytics')
  void t('nav.group.administration')
  void t('nav.group.devTools')
  void t('nav.managerGroup.todayGlance')
  void t('nav.managerGroup.usage')
  void t('nav.managerGroup.organization')
  void t('nav.help.dashboard')
  void t('nav.help.health')
  void t('nav.help.issues')
  void t('nav.help.personas')
  void t('nav.help.promptStudio')
  void t('nav.help.reactorUniverse')
  void t('nav.help.releaseCockpit')
  void t('nav.help.releaseOperations')
  void t('nav.help.documents')
  void t('nav.help.ragCache')
  void t('nav.help.feedback')
  void t('nav.help.integrations')
  void t('nav.help.models')
  void t('nav.help.safetyRules')
  void t('nav.help.inputGuard')
  void t('nav.help.accessControl')
  void t('nav.help.sessions')
  void t('nav.help.traces')
  void t('nav.help.audit')
  void t('nav.help.performance')
  void t('nav.help.usage')
  void t('nav.help.tenants')
  void t('nav.help.settings')
  void t('nav.help.mcpServers')
  void t('nav.help.chatInspector')
  void t('nav.help.scheduler')
  void t('nav.help.metricsIngestion')
  void t('nav.help.debugReplay')
}

/**
 * Task-flow-oriented navigation structure. Release operations is split out
 * so the v1.1 RAG -> feedback -> eval -> live-smoke boundary is discoverable.
 *
 * `visibleTo` is the single role-based visibility authority.
 */
const navGroups: NavGroup[] = [
  {
    titleKey: 'nav.group.today',
    items: [
      { path: '/',          label: 'nav.dashboard', description: 'nav.help.dashboard', visibleTo: 'all', icon: LayoutDashboard },
      { path: '/health',    label: 'nav.health',    description: 'nav.help.health',    visibleTo: 'all', icon: HeartPulse },
      { path: '/issues',    label: 'nav.issues',    description: 'nav.help.issues',    visibleTo: 'all', icon: AlertCircle },
      { path: '/approvals', label: 'nav.approvals', description: 'nav.help.approvals', visibleTo: 'all', icon: CheckSquare },
    ],
  },
  {
    titleKey: 'nav.group.aiConfig',
    items: [
      { path: '/personas',         label: 'nav.personas',         description: 'nav.help.personas',         visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: User },
      { path: '/prompt-studio',    label: 'nav.promptStudio',     description: 'nav.help.promptStudio',     visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: FileText },
      { path: '/reactor-universe', label: 'nav.reactorUniverse',  description: 'nav.help.reactorUniverse',  visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Orbit },
    ],
  },
  {
    titleKey: 'nav.group.releaseOps',
    descriptionKey: 'nav.group.releaseOpsDesc',
    items: [
      { path: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit, label: 'nav.releaseOperations', description: 'nav.help.releaseOperations', visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Rocket, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit },
      { path: RELEASE_OPERATION_NAV_PATHS_BY_ID.ingest,       label: 'nav.documents',    description: 'dashboard.releaseWorkflow.ingestDesc',    visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: BookOpen, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.ingest },
      { path: RELEASE_OPERATION_NAV_PATHS_BY_ID.rag,          label: 'nav.ragCache',     description: 'dashboard.releaseWorkflow.ragDesc',       visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Database, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag },
      { path: RELEASE_OPERATION_NAV_PATHS_BY_ID.feedback,     label: 'nav.feedback',     description: 'dashboard.releaseWorkflow.feedbackDesc',        visibleTo: 'all',                        icon: ThumbsUp, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback },
      { path: RELEASE_OPERATION_NAV_PATHS_BY_ID.evals,        label: 'nav.evals',        description: 'dashboard.releaseWorkflow.evalsDesc',     visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: BarChart3, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals },
      { path: RELEASE_OPERATION_NAV_PATHS_BY_ID.integrations, label: 'nav.integrations', description: 'dashboard.releaseWorkflow.integrationsDesc', visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Link, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.integrations },
      { path: RELEASE_OPERATION_NAV_PATHS_BY_ID.provider,     label: 'nav.models',       description: 'dashboard.releaseWorkflow.providerDesc',  visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Cpu, releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider },
    ],
  },
  {
    titleKey: 'nav.group.safetyPolicy',
    items: [
      { path: '/safety-rules',    label: 'nav.safetyRules',    description: 'nav.help.safetyRules',    visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Shield },
      { path: '/access-control',  label: 'nav.accessControl',  description: 'nav.help.accessControl',  visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: ShieldCheck },
    ],
  },
  {
    titleKey: 'nav.group.monitoring',
    items: [
      { path: '/sessions', label: 'nav.sessions', description: 'nav.help.sessions',       visibleTo: 'all',                        icon: MessageSquare },
      { path: '/traces',   label: 'nav.traces',   description: 'nav.help.traces',   visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Activity },
      { path: '/audit',    label: 'nav.audit',    description: 'nav.help.audit',          visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: ClipboardList },
    ],
  },
  {
    titleKey: 'nav.group.analytics',
    items: [
      { path: '/performance', label: 'nav.performance', description: 'nav.help.performance', visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Activity },
      { path: '/usage',       label: 'nav.usage',       description: 'nav.help.usage',             visibleTo: 'all',                        icon: DollarSign },
    ],
  },
  {
    titleKey: 'nav.group.administration',
    items: [
      { path: '/tenants',   label: 'nav.tenants',   description: 'nav.help.tenants',         visibleTo: 'all',                        icon: Building2, discoverableWithoutCapability: true },
      { path: '/settings',  label: 'nav.settings',  description: 'nav.help.settings',  visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Settings, discoverableWithoutCapability: true },
    ],
  },
  {
    titleKey: 'nav.group.devTools',
    items: [
      { path: '/mcp-servers',    label: 'nav.mcpServers',    description: 'nav.help.mcpServers',    visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Server },
      { path: '/chat-inspector', label: 'nav.chatInspector', description: 'nav.help.chatInspector', visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Search },
      { path: '/scheduler',         label: 'nav.scheduler',         description: 'nav.help.scheduler',         visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Clock },
      { path: '/metrics-ingestion', label: 'nav.metricsIngestion', description: 'nav.help.metricsIngestion', visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Send },
      { path: '/debug-replay',      label: 'nav.debugReplay',      description: 'nav.help.debugReplay',      visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'], icon: Bug },
    ],
  },
]

function matchesVisibility(visibility: NavItemVisibility | undefined, role: AdminRole): boolean {
  if (visibility === undefined || visibility === 'all') return true
  return visibility.includes(role)
}

function routeBase(path: string): string {
  return path.split(/[?#]/, 1)[0] || '/'
}

function isReleaseOperationGroup(group: NavGroup): boolean {
  return group.titleKey === 'nav.group.releaseOps'
}

function isNavItemAvailable(
  group: NavGroup,
  item: NavItem,
  isRouteAvailable: (routePath: string) => boolean,
): boolean {
  return isReleaseOperationGroup(group) || item.discoverableWithoutCapability === true || isRouteAvailable(item.path)
}

export function isRouteVisibleByRole(routePath: string, role: AdminRole): boolean {
  if (routePath === '/') return true
  const requestedBase = routeBase(routePath)
  for (const group of navGroups) {
    const item = group.items.find((i) => routeBase(i.path) === requestedBase)
    if (!item) continue
    return matchesVisibility(item.visibleTo, role)
  }
  // Unknown route: admin developer can see everything, manager cannot.
  return role !== 'ADMIN_MANAGER'
}

export function getVisibleNavGroupsByRole(
  role: AdminRole,
  isRouteAvailable: (routePath: string) => boolean,
): NavGroup[] {
  if (role === 'ADMIN_MANAGER') {
    return getVisibleManagerNavGroups(isRouteAvailable)
  }
  return navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter((item: NavItem) => (
        matchesVisibility(item.visibleTo, role) && isNavItemAvailable(group, item, isRouteAvailable)
      )),
    }))
    .filter((group) => group.items.length > 0)
}

/**
 * Manager-specific 3-group taxonomy (PR W1-D).
 *
 * Per BX audit P1-8: ADMIN_MANAGER previously saw a stripped subset of the
 * 7-group developer taxonomy (Today / Monitoring / Analytics / Administration
 * each with a couple of items each), which read as "missing items" rather
 * than a coherent, manager-natural information architecture. We re-group
 * the same 8 manager-visible items into three groups that match the
 * manager's mental model:
 *
 *   - 오늘 한눈에 (todayGlance):   Dashboard, Health, Issues, Approvals
 *   - 사용 현황 (usage):           Sessions, Feedback, Usage & Cost
 *   - 조직 (organization):        Tenants
 *
 * Visibility / access is unchanged — manager-restricted items (e.g.
 * /traces, /audit, /personas) remain hidden via `visibleTo` on the source
 * item. Only the *grouping* differs from ADMIN/ADMIN_DEVELOPER.
 *
 * Source items are looked up by path from the developer `navGroups` so the
 * icon, label, description, and a11y wiring stay in lockstep with the
 * authoritative 7-group structure (single source of truth for nav metadata).
 */
const MANAGER_GROUP_DEFINITIONS: ReadonlyArray<{ titleKey: string; paths: string[] }> = [
  {
    titleKey: 'nav.managerGroup.todayGlance',
    paths: ['/', '/health', '/issues', '/approvals'],
  },
  {
    titleKey: 'nav.managerGroup.usage',
    paths: ['/sessions', '/feedback', '/usage'],
  },
  {
    titleKey: 'nav.managerGroup.organization',
    paths: ['/tenants'],
  },
]

function findNavItemByPath(path: string): NavItem | undefined {
  const requestedBase = routeBase(path)
  for (const group of navGroups) {
    const item = group.items.find((i) => routeBase(i.path) === requestedBase)
    if (item) return item.path === path ? item : { ...item, path }
  }
  return undefined
}

export function getVisibleManagerNavGroups(
  isRouteAvailable: (routePath: string) => boolean,
): NavGroup[] {
  const role: AdminRole = 'ADMIN_MANAGER'
  return MANAGER_GROUP_DEFINITIONS
    .map((def) => ({
      titleKey: def.titleKey,
      items: def.paths
        .map((p) => findNavItemByPath(p))
        .filter((item): item is NavItem => item !== undefined)
        .filter((item) => (
          matchesVisibility(item.visibleTo, role)
          && (item.discoverableWithoutCapability === true || isRouteAvailable(item.path))
        )),
    }))
    .filter((group) => group.items.length > 0)
}
