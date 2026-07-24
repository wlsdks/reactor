import { render, screen, fireEvent } from '../../../test/utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { CommandPalette } from '../CommandPalette'
import {
  buildCommandActions,
  filterActionsByQuery,
  filterAvailableActions,
} from '../commandPaletteActions'
import { RELEASE_WORKFLOW_COMMAND_ACTIONS, buildReleaseWorkflowSearchRecords } from '../../releaseWorkflow'
import type { NavGroup } from '../../types/navigation'
import type { SearchableRecord } from '../../lib/searchIndex'
import { LayoutDashboard, AlertCircle, User, Database } from 'lucide-react'

const mockSearchRecords: SearchableRecord[] = []
vi.mock('../../lib/useGlobalSearchRecords', () => ({
  useGlobalSearchRecords: () => mockSearchRecords,
}))

function setMockSearchRecords(records: SearchableRecord[]) {
  mockSearchRecords.length = 0
  mockSearchRecords.push(...records)
}

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

const mockToggleViewAsManager = vi.fn()
const roleVisibilityMock = {
  effectiveRole: 'ADMIN' as const,
  role: 'ADMIN' as const,
  canToggleViewAs: true,
  viewAsManager: false,
  toggleViewAsManager: mockToggleViewAsManager,
  isRouteVisible: () => true,
  getVisibleNavGroups: () => [],
}

vi.mock('../../../features/workspace', async () => {
  const actual = await vi.importActual<typeof import('../../../features/workspace')>(
    '../../../features/workspace',
  )
  return {
    ...actual,
    useRoleVisibility: () => roleVisibilityMock,
  }
})

const testNavGroups: NavGroup[] = [
  {
    titleKey: 'nav.group.operations',
    items: [
      { path: '/', label: 'nav.dashboard', description: 'nav.help.dashboard', icon: LayoutDashboard },
      { path: '/issues', label: 'nav.issues', description: 'nav.help.issues', icon: AlertCircle },
    ],
  },
  {
    titleKey: 'nav.group.aiConfig',
    items: [
      { path: '/personas', label: 'nav.personas', description: 'nav.help.personas', icon: User },
    ],
  },
  {
    titleKey: 'nav.group.releaseOps',
    descriptionKey: 'nav.group.releaseOpsDesc',
    items: [
      {
        path: '/rag-cache',
        label: 'nav.ragCache',
        description: 'nav.help.ragCache',

        icon: Database,
        releaseStepNumber: 3,
      },
    ],
  },
]

function openPalette() {
  fireEvent.keyDown(document, { key: 'k', metaKey: true })
}

describe('CommandPalette', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    mockToggleViewAsManager.mockClear()
    roleVisibilityMock.effectiveRole = 'ADMIN'
    roleVisibilityMock.role = 'ADMIN'
    roleVisibilityMock.canToggleViewAs = true
    roleVisibilityMock.viewAsManager = false
    roleVisibilityMock.isRouteVisible = () => true
    setMockSearchRecords([])
  })

  it('renders nothing when closed', () => {
    const { container } = render(<CommandPalette navGroups={testNavGroups} />)
    expect(container.innerHTML).toBe('')
  })

  it('opens on Cmd+K', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('opens on Ctrl+K', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('closes on Escape', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes when clicking the overlay', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    const dialog = screen.getByRole('dialog')
    fireEvent.click(dialog.parentElement!)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows nav items and registry actions together', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    // 3 nav items + 12 registry actions (all visible to ADMIN role)
    expect(screen.getAllByRole('option').length).toBeGreaterThanOrEqual(3 + 12)
  })

  it('renders release workflow actions in their own first section', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    const sections = screen.getAllByText(/^commandPalette\.sections\./)

    expect(sections.map((section) => section.textContent)).toEqual([
      'commandPalette.sections.release',
      'commandPalette.sections.navigate',
      'commandPalette.sections.create',
      'commandPalette.sections.action',
    ])
    expect(screen.getByText('commandPalette.sections.release')).toBeInTheDocument()
    expect(screen.getByText('commandPalette.sections.navigate')).toBeInTheDocument()
    expect(screen.getByText('commandPalette.sections.create')).toBeInTheDocument()
    expect(screen.getByText('commandPalette.sections.action')).toBeInTheDocument()
    expect(
      screen.getByRole('option', { name: 'commandPalette.actions.releaseWorkflow' }),
    ).toHaveAttribute('data-action-id', 'navigate.release-workflow')
  })

  it('keeps the default release section focused on the workflow overview and primary steps', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()

    const defaultReleaseActionIds = screen
      .getAllByRole('option')
      .map((option) => option.getAttribute('data-action-id'))
      .filter((actionId): actionId is string => actionId?.startsWith('navigate.') ?? false)

    expect(defaultReleaseActionIds).toEqual(expect.arrayContaining([
      'navigate.release-workflow',
      'navigate.release-cockpit',
      'navigate.rag-ingestion',
      'navigate.rag-lifecycle',
      'navigate.feedback-promotion',
      'navigate.eval-regression',
      'navigate.integration-smoke',
      'navigate.provider-smoke',
    ]))
    expect(defaultReleaseActionIds).not.toEqual(expect.arrayContaining([
      'navigate.rag-cited-answer',
      'navigate.langsmith-sync',
      'navigate.slack-gateway-smoke',
      'navigate.a2a-protocol-smoke',
    ]))
  })

  it('reveals a release evidence shortcut when its search terms are entered', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'langsmith_eval_sync' } })

    expect(screen.getByRole('option', { name: '5. commandPalette.actions.langsmithSync' }))
      .toHaveAttribute('data-action-id', 'navigate.langsmith-sync')
  })

  it('filters items by search query (nav match)', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'dashboard' } })
    // Both nav.dashboard and the openDashboard action match
    const opts = screen.getAllByRole('option')
    expect(opts.length).toBeGreaterThanOrEqual(1)
  })

  it('filters down to a single registry action', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'createSafetyRule' } })
    const opts = screen.getAllByRole('option')
    expect(opts).toHaveLength(1)
    expect(opts[0]).toHaveAttribute('data-action-id', 'create.safety-rule')
  })

  it('shows search empty state when query has no results', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'zzz-no-match' } })
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
    // When the query is non-empty we surface the data-search empty copy.
    expect(screen.getByText('commandPalette.search.emptyResult')).toBeInTheDocument()
  })

  it('navigates the release workflow entry with Enter by default', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
    expect(mockNavigate).toHaveBeenCalledWith('/release#release-workflow')
  })

  it('arrow keys move within the release workflow section first', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    const input = screen.getByRole('textbox')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mockNavigate).toHaveBeenCalledWith('/release#release-cockpit')
  })

  it('runs an action via click and dispatches navigation', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'createPersona' } })
    const option = screen.getByRole('option')
    fireEvent.click(option)
    expect(mockNavigate).toHaveBeenCalledWith('/personas?create=1')
  })

  it('runs the toggle DEV mode action via Enter', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'toggleDevMode' } })
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' })
    expect(mockToggleViewAsManager).toHaveBeenCalledTimes(1)
  })

  it('toggles open/closed with repeated Cmd+K', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    openPalette()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders the data search section with scope chip when results exist', () => {
    setMockSearchRecords([
      {
        id: 'p-1',
        scope: 'persona',
        title: 'Phoenix Persona',
        subtitle: 'Senior support agent',
        navigateTo: '/personas?id=p-1',
        haystack: 'phoenix persona senior support agent',
      },
    ])
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'phoenix' } })

    expect(screen.getByText('commandPalette.search.sectionTitle')).toBeInTheDocument()
    expect(screen.getByText('Phoenix Persona')).toBeInTheDocument()
    expect(screen.getByText('Senior support agent')).toBeInTheDocument()
    // Scope chip is rendered with the i18n key for the scope.
    expect(screen.getByText('commandPalette.search.scope.persona')).toBeInTheDocument()
  })

  it('does not render the search section when query is empty', () => {
    setMockSearchRecords([
      {
        id: 'p-1',
        scope: 'persona',
        title: 'Phoenix',
        navigateTo: '/personas?id=p-1',
        haystack: 'phoenix',
      },
    ])
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    expect(screen.queryByText('commandPalette.search.sectionTitle')).not.toBeInTheDocument()
  })

  it('navigates to a search result on Enter', () => {
    setMockSearchRecords([
      {
        id: 'fb-1',
        scope: 'feedback',
        title: 'How do I export the report?',
        navigateTo: '/feedback?id=fb-1',
        haystack: 'how do i export the report',
      },
    ])
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'export' } })

    // Find the search-result row (other static actions may also match the query).
    const searchOption = screen
      .getAllByRole('option')
      .find((el) => el.getAttribute('data-search-scope') === 'feedback')
    expect(searchOption).toBeDefined()
    expect(searchOption).toHaveAttribute('data-search-id', 'fb-1')
    fireEvent.click(searchOption!)
    expect(mockNavigate).toHaveBeenCalledWith('/feedback?id=fb-1')
  })

  it('renders release search result step numbers consistently with release actions', () => {
    setMockSearchRecords([
      {
        id: 'release:navigate.provider-smoke',
        scope: 'release',
        title: 'commandPalette.actions.providerSmoke',
        subtitle: 'commandPalette.actions.providerSmokeDesc',
        navigateTo: '/models#provider-smoke',
        haystack: 'provider smoke ollama model usage step 7',
        stepNumber: 7,
      },
    ])
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ollama' } })

    const releaseResult = screen
      .getAllByRole('option', { name: '7. commandPalette.actions.providerSmoke' })
      .find((el) => el.getAttribute('data-search-id') === 'release:navigate.provider-smoke')
    expect(releaseResult).toBeDefined()
    expect(releaseResult).toHaveAttribute('data-search-scope', 'release')
    expect(releaseResult!.querySelector('.cmd-palette__step')).toHaveTextContent('7')
    expect(releaseResult!.querySelector('.cmd-palette__step')).toHaveAttribute('aria-hidden', 'true')
  })

  it('renders release blocker search records as owning workflow shortcuts', () => {
    setMockSearchRecords(buildReleaseWorkflowSearchRecords((key) => key))
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'preflight' } })

    const releaseResult = screen
      .getAllByRole('option', { name: '6. preflight blocker' })
      .find((el) => el.getAttribute('data-search-id') === 'release:blocker:preflight')
    expect(releaseResult).toBeDefined()
    expect(releaseResult).toHaveAttribute('data-search-scope', 'release')
    expect(releaseResult).toHaveTextContent('commandPalette.actions.integrationSmoke')
    fireEvent.click(releaseResult!)

    expect(mockNavigate).toHaveBeenCalledWith('/integrations#release-smoke')
  })

  it('hides data search results whose destination is not visible to the effective role', () => {
    roleVisibilityMock.effectiveRole = 'ADMIN_MANAGER'
    roleVisibilityMock.role = 'ADMIN_MANAGER'
    roleVisibilityMock.canToggleViewAs = false
    roleVisibilityMock.isRouteVisible = (path: string) => path === '/feedback'
    setMockSearchRecords([
      {
        id: 'release:navigate.provider-smoke',
        scope: 'release',
        title: 'Provider smoke',
        navigateTo: '/models#provider-smoke',
        haystack: 'provider smoke ollama model usage',
      },
      {
        id: 'fb-1',
        scope: 'feedback',
        title: 'Feedback promotion',
        navigateTo: '/feedback?id=fb-1',
        haystack: 'feedback promotion',
      },
    ])
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ollama' } })

    expect(screen.queryByRole('option')).not.toBeInTheDocument()
    expect(screen.getByText('commandPalette.search.emptyResult')).toBeInTheDocument()
  })

  it('limits the search section to top 20 results', () => {
    const records: SearchableRecord[] = Array.from({ length: 30 }, (_, i) => ({
      id: `r-${i}`,
      scope: 'audit' as const,
      title: `Audit ${String(i).padStart(2, '0')}`,
      navigateTo: `/audit?id=r-${i}`,
      haystack: `audit ${i}`,
    }))
    setMockSearchRecords(records)
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'audit' } })

    const searchOptions = screen
      .getAllByRole('option')
      .filter((el) => el.getAttribute('data-search-scope') === 'audit')
    expect(searchOptions).toHaveLength(20)
  })
})

describe('commandPaletteActions registry', () => {
  const baseDeps = {
    navigate: vi.fn(),
    role: 'ADMIN' as const,
    toggleViewAsManager: vi.fn(),
    canToggleViewAs: true,
  }

  it('returns the seeded actions (>=10)', () => {
    const actions = buildCommandActions(baseDeps)
    expect(actions.length).toBeGreaterThanOrEqual(10)
  })

  it('groups actions across the command sections', () => {
    const actions = buildCommandActions(baseDeps)
    const sections = new Set(actions.map((a) => a.section))
    expect(sections.has('release')).toBe(true)
    expect(sections.has('navigate')).toBe(true)
    expect(sections.has('create')).toBe(true)
    expect(sections.has('action')).toBe(true)
  })

  it('hides dev-only actions for ADMIN_MANAGER role', () => {
    const all = buildCommandActions({ ...baseDeps, role: 'ADMIN_MANAGER', canToggleViewAs: false })
    const visible = filterAvailableActions(all)
    expect(visible.find((a) => a.id === 'create.persona')).toBeUndefined()
    expect(visible.find((a) => a.id === 'create.safety-rule')).toBeUndefined()
    expect(visible.find((a) => a.id === 'action.toggle-dev-mode')).toBeUndefined()
  })

  it('keeps universal navigate actions for ADMIN_MANAGER', () => {
    const all = buildCommandActions({ ...baseDeps, role: 'ADMIN_MANAGER', canToggleViewAs: false })
    const visible = filterAvailableActions(all)
    expect(visible.find((a) => a.id === 'navigate.dashboard')).toBeDefined()
    expect(visible.find((a) => a.id === 'navigate.feedback-followup')).toBeDefined()
  })

  it('filterActionsByQuery narrows by title and keywords while keeping specialist shortcuts searchable', () => {
    const actions = buildCommandActions(baseDeps)
    const t = (key: string) => key
    expect(filterActionsByQuery(actions, 'persona', t)).toHaveLength(1)
    expect(filterActionsByQuery(actions, 'cron', t)).toHaveLength(1)
    expect(filterActionsByQuery(actions, '', t))
      .toEqual(actions.filter((action) => action.showByDefault !== false))
    expect(filterActionsByQuery(actions, 'langsmith_eval_sync', t).map((action) => action.id))
      .toEqual(['navigate.langsmith-sync'])
  })

  it('perform invokes the navigate dependency', () => {
    const navigate = vi.fn()
    const actions = buildCommandActions({ ...baseDeps, navigate })
    const dashboard = actions.find((a) => a.id === 'navigate.dashboard')!
    dashboard.perform()
    expect(navigate).toHaveBeenCalledWith('/')
  })

  it('exposes a "Open performance tools" action for dev roles only', () => {
    // Dev-only because the Tools tab surfaces engineering-grade outcome
    // counters; ADMIN_MANAGER stays scoped to today/usage/tenants.
    const adminVisible = filterAvailableActions(
      buildCommandActions({ ...baseDeps, role: 'ADMIN' }),
    )
    expect(
      adminVisible.find((a) => a.id === 'navigate.performance-tools'),
    ).toBeDefined()

    const developerVisible = filterAvailableActions(
      buildCommandActions({ ...baseDeps, role: 'ADMIN_DEVELOPER' }),
    )
    expect(
      developerVisible.find((a) => a.id === 'navigate.performance-tools'),
    ).toBeDefined()

    const managerVisible = filterAvailableActions(
      buildCommandActions({
        ...baseDeps,
        role: 'ADMIN_MANAGER',
        canToggleViewAs: false,
      }),
    )
    expect(
      managerVisible.find((a) => a.id === 'navigate.performance-tools'),
    ).toBeUndefined()
  })

  it('"Open performance tools" navigates to /performance?seg=tools', () => {
    const navigate = vi.fn()
    const actions = buildCommandActions({ ...baseDeps, navigate })
    const action = actions.find((a) => a.id === 'navigate.performance-tools')!
    action.perform()
    expect(navigate).toHaveBeenCalledWith('/performance?seg=tools')
  })

  it('exposes release workflow shortcuts for developer roles only', () => {
    const adminVisible = filterAvailableActions(
      buildCommandActions({ ...baseDeps, role: 'ADMIN' }),
    )
    expect(adminVisible.find((a) => a.id === 'navigate.release-workflow')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.release-cockpit')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.rag-ingestion')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.rag-lifecycle')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.rag-cited-answer')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.feedback-promotion')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.eval-regression')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.langsmith-sync')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.integration-smoke')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.slack-gateway-smoke')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.a2a-protocol-smoke')).toBeDefined()
    expect(adminVisible.find((a) => a.id === 'navigate.provider-smoke')).toBeDefined()

    const managerVisible = filterAvailableActions(
      buildCommandActions({
        ...baseDeps,
        role: 'ADMIN_MANAGER',
        canToggleViewAs: false,
      }),
    )
    expect(managerVisible.find((a) => a.id === 'navigate.release-workflow')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.release-cockpit')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.rag-ingestion')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.rag-lifecycle')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.rag-cited-answer')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.feedback-promotion')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.eval-regression')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.langsmith-sync')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.integration-smoke')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.slack-gateway-smoke')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.a2a-protocol-smoke')).toBeUndefined()
    expect(managerVisible.find((a) => a.id === 'navigate.provider-smoke')).toBeUndefined()
  })

  it('marks release workflow actions with step numbers for search and display', () => {
    const actions = buildCommandActions(baseDeps)
    const releaseActions = actions.filter((a) => a.id.startsWith('navigate.') && a.stepNumber)
    expect(releaseActions.every((a) => a.section === 'release')).toBe(true)
    expect(releaseActions.map((a) => [a.id, a.stepNumber])).toEqual([
      ['navigate.release-cockpit', 1],
      ['navigate.rag-ingestion', 2],
      ['navigate.rag-lifecycle', 3],
      ['navigate.rag-cited-answer', 3],
      ['navigate.feedback-promotion', 4],
      ['navigate.eval-regression', 5],
      ['navigate.langsmith-sync', 5],
      ['navigate.integration-smoke', 6],
      ['navigate.slack-gateway-smoke', 6],
      ['navigate.a2a-protocol-smoke', 6],
      ['navigate.provider-smoke', 7],
    ])
    expect(filterActionsByQuery(actions, 'step 6', (key) => key).map((a) => a.id))
      .toEqual([
        'navigate.integration-smoke',
        'navigate.slack-gateway-smoke',
        'navigate.a2a-protocol-smoke',
      ])
  })

  it('finds release workflow actions by Korean operator terms', () => {
    const actions = buildCommandActions(baseDeps)
    const t = (key: string) => key

    expect(filterActionsByQuery(actions, '근거 답변', t).map((a) => a.id))
      .toContain('navigate.rag-cited-answer')
    expect(filterActionsByQuery(actions, '평가 회귀', t).map((a) => a.id))
      .toContain('navigate.eval-regression')
    expect(filterActionsByQuery(actions, '라이브 스모크', t).map((a) => a.id))
      .toContain('navigate.integration-smoke')
    expect(filterActionsByQuery(actions, '제공자', t).map((a) => a.id))
      .toEqual(['navigate.provider-smoke'])
  })

  it('finds release unblock surfaces by exact environment variable names', () => {
    const actions = buildCommandActions(baseDeps)
    const t = (key: string) => key

    expect(filterActionsByQuery(actions, 'LANGSMITH_API_KEY', t).map((a) => a.id))
      .toEqual(['navigate.langsmith-sync'])
    expect(filterActionsByQuery(actions, 'REACTOR_SLACK_SIGNING_SECRET', t).map((a) => a.id))
      .toEqual([
        'navigate.integration-smoke',
        'navigate.slack-gateway-smoke',
      ])
    expect(filterActionsByQuery(actions, 'REACTOR_A2A_BASE_URL', t).map((a) => a.id))
      .toEqual([
        'navigate.integration-smoke',
        'navigate.a2a-protocol-smoke',
      ])
    expect(filterActionsByQuery(actions, 'OPENAI_API_KEY', t).map((a) => a.id))
      .toEqual([
        'navigate.integration-smoke',
        'navigate.provider-smoke',
      ])
    expect(filterActionsByQuery(actions, 'AIMessage.usage_metadata', t).map((a) => a.id))
      .toEqual(['navigate.provider-smoke'])
  })

  it('renders release workflow action step numbers in the palette', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'releaseCockpit' } })

    expect(screen.getByRole('option', { name: '1. commandPalette.actions.releaseCockpit' }))
      .toBeInTheDocument()
  })

  it('renders release workflow nav step numbers in the palette', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ragCache' } })

    const option = screen.getByRole('option', { name: '3. nav.ragCache' })
    expect(option).toBeInTheDocument()
    expect(option.querySelector('.cmd-palette__step')).toHaveTextContent('3')
    expect(option.querySelector('.cmd-palette__step')).toHaveAttribute('aria-hidden', 'true')
  })

  it('shows release workflow group context on release nav results', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ragCache' } })

    const option = screen.getByRole('option', { name: '3. nav.ragCache' })
    expect(option.querySelector('.cmd-palette__item-desc'))
      .toHaveTextContent('Release Operations · nav.help.ragCache')
  })

  it('finds release workflow nav items by step query', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'step 3' } })

    expect(screen.getByRole('option', { name: '3. nav.ragCache' })).toBeInTheDocument()
  })

  it('finds release workflow nav items by Korean step query', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '릴리즈 단계 3' } })

    expect(screen.getByRole('option', { name: '3. nav.ragCache' })).toBeInTheDocument()
  })

  it('finds release workflow nav items by release operation boundary terms', () => {
    render(<CommandPalette navGroups={testNavGroups} />)
    openPalette()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'release gate' } })

    expect(screen.getByRole('option', { name: '3. nav.ragCache' })).toBeInTheDocument()
  })

  it('finds release workflow actions by readiness report evidence terms', () => {
    const actions = buildCommandActions({ ...baseDeps, navigate: vi.fn() })
    const t = (key: string) => key

    expect(filterActionsByQuery(actions, 'requiredReports', t).map((a) => a.id))
      .toEqual(expect.arrayContaining(['navigate.release-workflow', 'navigate.release-cockpit', 'navigate.integration-smoke']))
    expect(filterActionsByQuery(actions, 'missingReports', t).map((a) => a.id))
      .toEqual(expect.arrayContaining(['navigate.release-workflow', 'navigate.release-cockpit', 'navigate.integration-smoke']))
    expect(filterActionsByQuery(actions, 'release_evidence', t).map((a) => a.id))
      .toEqual(expect.arrayContaining(['navigate.release-workflow', 'navigate.release-cockpit']))
    expect(filterActionsByQuery(actions, 'langsmith_eval_sync', t).map((a) => a.id))
      .toEqual(['navigate.langsmith-sync'])
    expect(filterActionsByQuery(actions, 'smoke_run', t).map((a) => a.id))
      .toEqual(['navigate.integration-smoke'])
  })

  it('release workflow shortcuts navigate to the owning surfaces', () => {
    const navigate = vi.fn()
    const actions = buildCommandActions({ ...baseDeps, navigate })

    RELEASE_WORKFLOW_COMMAND_ACTIONS.forEach((releaseAction) => {
      actions.find((a) => a.id === releaseAction.id)!.perform()
    })

    RELEASE_WORKFLOW_COMMAND_ACTIONS.forEach((releaseAction, index) => {
      expect(navigate).toHaveBeenNthCalledWith(index + 1, releaseAction.path)
    })
  })
})
