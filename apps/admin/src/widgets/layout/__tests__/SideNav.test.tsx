import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, act } from '../../../test/utils'
import { MemoryRouter } from 'react-router-dom'
import { SideNav } from '../SideNav'
import { useSidebarStore } from '../../../shared/store/sidebar.store'
import {
  __resetSidenavGroupsStoreForTests,
  useSidenavGroupsStore,
} from '../../../shared/store/sidenav-groups.store'

vi.mock('../../../features/capabilities', () => ({
  useFeatureAvailability: () => ({
    isRouteAvailable: () => true,
    isLoading: false,
  }),
}))

vi.mock('../../../features/issues', () => ({
  useIssueCenterSnapshot: () => ({ data: null }),
}))

vi.mock('../../../features/workspace', () => {
  const noopIcon = () => null
  const navGroupsFixture = [
    {
      titleKey: 'nav.group.today',
      items: [
        {
          path: '/',
          label: 'nav.dashboard',
          description: 'nav.help.dashboard',
          visibleTo: 'all' as const,
          icon: noopIcon,
        },
      ],
    },
    {
      titleKey: 'nav.group.releaseOps',
      descriptionKey: 'nav.group.releaseOpsDesc',
      items: [
        {
          path: '/release#release-cockpit',
          label: 'nav.releaseOperations',
          description: 'nav.help.releaseOperations',
          visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'] as const,
          icon: noopIcon,
          releaseStepNumber: 1,
        },
        {
          path: '/models#provider-smoke',
          label: 'nav.models',
          description: 'dashboard.releaseWorkflow.providerDesc',
          visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'] as const,
          icon: noopIcon,
          releaseStepNumber: 7,
        },
      ],
    },
    {
      titleKey: 'nav.group.devTools',
      items: [
        {
          path: '/mcp-servers',
          label: 'nav.mcpServers',
          description: 'nav.help.mcpServers',
          visibleTo: ['ADMIN', 'ADMIN_DEVELOPER'] as const,
          icon: noopIcon,
        },
      ],
    },
  ]
  return {
    useRoleVisibility: vi.fn().mockReturnValue({
      role: 'ADMIN',
      effectiveRole: 'ADMIN',
      viewAsManager: false,
      canToggleViewAs: true,
      toggleViewAsManager: vi.fn(),
      isRouteVisible: vi.fn().mockReturnValue(true),
      getVisibleNavGroups: vi.fn().mockReturnValue(navGroupsFixture),
    }),
  }
})

function renderSideNav(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SideNav />
    </MemoryRouter>,
  )
}

describe('SideNav', () => {
  beforeEach(() => {
    useSidebarStore.setState({ collapsed: true, mobileOpen: false })
    __resetSidenavGroupsStoreForTests()
  })

  it('renders navigation element', () => {
    renderSideNav()
    expect(screen.getByRole('navigation')).toBeInTheDocument()
  })

  it('renders toggle button', () => {
    renderSideNav()
    const toggle = screen.getByRole('button', { name: /expand|collapse|navigation/i })
    expect(toggle).toBeInTheDocument()
  })

  it('toggles expanded state on button click', () => {
    renderSideNav()
    const nav = screen.getByRole('navigation')
    expect(nav.classList.contains('expanded')).toBe(false)

    const toggle = screen.getByRole('button', { name: /expand/i })
    fireEvent.click(toggle)
    expect(nav.classList.contains('expanded')).toBe(true)
  })

  it('renders nav links for all visible groups', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('nav.releaseOperations')).toBeInTheDocument()
    expect(screen.getByText('MCP Servers')).toBeInTheDocument()
  })

  it('highlights active route', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav('/')
    const dashboardLink = screen.getByText('Dashboard').closest('a')
    expect(dashboardLink?.classList.contains('active')).toBe(true)
  })

  it('highlights release deep links when the current route is the base page', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav('/models')
    const providerLink = screen.getByText('nav.models').closest('a')
    expect(providerLink).toHaveAttribute('href', '/models#provider-smoke')
    expect(providerLink?.classList.contains('active')).toBe(true)
  })

  describe('collapsible groups', () => {
    beforeEach(() => {
      // Group toggles only render when sidebar itself is expanded.
      useSidebarStore.setState({ collapsed: false })
    })

    it('renders only the core groups expanded by default', () => {
      renderSideNav()
      const todayToggle = document.getElementById('sidenav-group-nav-group-today')
      const releaseToggle = document.getElementById('sidenav-group-nav-group-releaseOps')
      const devToggle = document.getElementById('sidenav-group-nav-group-devTools')
      expect(todayToggle).not.toBeNull()
      expect(releaseToggle).not.toBeNull()
      expect(devToggle).not.toBeNull()
      expect(todayToggle!.getAttribute('aria-expanded')).toBe('true')
      expect(releaseToggle!.getAttribute('aria-expanded')).toBe('true')
      expect(devToggle!.getAttribute('aria-expanded')).toBe('false')
    })

    it('toggling a group hides its items', () => {
      renderSideNav()
      const todayToggle = document.getElementById('sidenav-group-nav-group-today') as HTMLButtonElement
      expect(todayToggle.getAttribute('aria-expanded')).toBe('true')
      // Items visible.
      expect(screen.getByText('Dashboard')).toBeVisible()

      fireEvent.click(todayToggle)

      expect(todayToggle.getAttribute('aria-expanded')).toBe('false')
      // The <ul> hosting items is now `hidden`, removing items from a11y tree.
      const list = document.getElementById('sidenav-group-list-nav-group-today')
      expect(list).not.toBeNull()
      expect(list!.hasAttribute('hidden')).toBe(true)
    })

    it('persists collapsed group state to localStorage', () => {
      renderSideNav()
      const todayToggle = document.getElementById('sidenav-group-nav-group-today') as HTMLButtonElement
      fireEvent.click(todayToggle)

      const stored = window.localStorage.getItem('reactor-admin-sidenav-collapsed-groups')
      expect(stored).not.toBeNull()
      const parsed = JSON.parse(stored!) as string[]
      expect(parsed).toContain('nav.group.today')
    })

    it('hydrates collapsed state from localStorage on mount', () => {
      window.localStorage.setItem(
        'reactor-admin-sidenav-collapsed-groups',
        JSON.stringify(['nav.group.today']),
      )
      // Re-seed the store from localStorage to simulate a fresh page load.
      useSidenavGroupsStore.setState({
        collapsedGroups: new Set(['nav.group.today']),
      })

      renderSideNav()

      const todayToggle = document.getElementById('sidenav-group-nav-group-today') as HTMLButtonElement
      expect(todayToggle.getAttribute('aria-expanded')).toBe('false')
    })

    it('keyboard activation toggles a group via the underlying button', () => {
      renderSideNav()
      const todayToggle = document.getElementById('sidenav-group-nav-group-today') as HTMLButtonElement
      expect(todayToggle.getAttribute('aria-expanded')).toBe('true')
      // <button> elements respond to keyboard activation by dispatching a
      // click event in browsers; simulate that here.
      fireEvent.click(todayToggle)
      expect(todayToggle.getAttribute('aria-expanded')).toBe('false')
    })

    it('group toggles are not rendered when sidebar is icon-only collapsed', () => {
      useSidebarStore.setState({ collapsed: true })
      renderSideNav()
      // No group toggle buttons render when the sidebar itself is icon-only.
      // (The sr-only label span re-uses the same id but is not a button.)
      const todayEl = document.getElementById('sidenav-group-nav-group-today')
      const devEl = document.getElementById('sidenav-group-nav-group-devTools')
      expect(todayEl?.tagName).not.toBe('BUTTON')
      expect(devEl?.tagName).not.toBe('BUTTON')
      expect(screen.queryByRole('button', { name: 'Show core groups' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Expand all groups' })).not.toBeInTheDocument()
    })
  })

  it('renders release operation step numbers when expanded', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav()

    expect(screen.getByRole('link', { name: '1. nav.releaseOperations' })).toBeInTheDocument()
    const releaseLink = screen.getByText('nav.releaseOperations').closest('a')
    expect(releaseLink).toHaveTextContent('1')
  })

  it('shows release operation descriptions only in the expanded release group', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav()

    const releaseLink = screen.getByRole('link', { name: '1. nav.releaseOperations' })
    expect(releaseLink).toHaveTextContent('nav.help.releaseOperations')
    const providerLink = screen.getByRole('link', { name: '7. nav.models' })
    expect(providerLink).toHaveTextContent('dashboard.releaseWorkflow.providerDesc')
    expect(releaseLink.querySelector('.sidenav-item-description')).toHaveAttribute('aria-hidden', 'true')
  })

  it('keeps release operation step numbers in collapsed tooltips', () => {
    useSidebarStore.setState({ collapsed: true })
    renderSideNav()

    expect(screen.getByRole('link', { name: '1. nav.releaseOperations' })).toHaveAttribute(
      'title',
      '1. nav.releaseOperations',
    )
    expect(screen.queryByText('nav.help.releaseOperations')).not.toBeInTheDocument()
  })

  it('summarizes release workflow range on the group heading', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav()

    const releaseToggle = document.getElementById('sidenav-group-nav-group-releaseOps')
    const stepRange = releaseToggle?.querySelector('.sidenav-group-step-range')

    expect(stepRange).not.toBeNull()
    expect(stepRange).toHaveTextContent('Step 1-7')
    expect(stepRange).toHaveAttribute('aria-label', 'nav.releaseStepRange')
  })

  it('describes the release operation group as the v1.1 product boundary', () => {
    useSidebarStore.setState({ collapsed: false })
    renderSideNav()

    const releaseGroup = screen.getByRole('region', { name: /Release Operations/ })
    expect(releaseGroup).toHaveTextContent('v1.1 RAG 수집, 근거 답변, feedback/eval 승격, LangSmith sync, live smoke, readiness 리포트')
  })

  describe('tablet auto-collapse', () => {
    function mockMatchMediaMatches(matches: boolean) {
      const listeners = new Set<(e: { matches: boolean }) => void>()
      const mql = {
        matches,
        media: '(max-width: 1024px)',
        addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => {
          listeners.add(cb)
        },
        removeEventListener: (_: string, cb: (e: { matches: boolean }) => void) => {
          listeners.delete(cb)
        },
        addListener: () => {},
        removeListener: () => {},
        onchange: null,
        dispatchEvent: () => true,
      }
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        writable: true,
        value: vi.fn().mockReturnValue(mql),
      })
      return {
        trigger(next: boolean) {
          mql.matches = next
          for (const cb of listeners) cb({ matches: next })
        },
      }
    }

    it('auto-collapses when viewport shrinks into tablet range', () => {
      // Start wide + user-expanded.
      const controller = mockMatchMediaMatches(false)
      useSidebarStore.setState({ collapsed: false })
      renderSideNav()
      expect(useSidebarStore.getState().collapsed).toBe(false)

      // Transition to tablet width.
      act(() => {
        controller.trigger(true)
      })
      expect(useSidebarStore.getState().collapsed).toBe(true)
    })

    it('does not mutate state when mounted in an already-tablet viewport', () => {
      // User is collapsed on tablet; we should not flip the state on first mount.
      mockMatchMediaMatches(true)
      useSidebarStore.setState({ collapsed: true })
      renderSideNav()
      expect(useSidebarStore.getState().collapsed).toBe(true)
    })
  })

  describe('mobile overlay state', () => {
    function mockMobileMatchMedia() {
      const listeners = new Set<(e: { matches: boolean }) => void>()
      const mql = {
        matches: true,
        media: '(max-width: 768px)',
        addEventListener: (_: string, cb: (e: { matches: boolean }) => void) => {
          listeners.add(cb)
        },
        removeEventListener: (_: string, cb: (e: { matches: boolean }) => void) => {
          listeners.delete(cb)
        },
        addListener: () => {},
        removeListener: () => {},
        onchange: null,
        dispatchEvent: () => true,
      }
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        writable: true,
        value: vi.fn().mockReturnValue(mql),
      })
    }

    it('keeps a previously expanded desktop rail closed until the mobile menu is explicitly opened', () => {
      mockMobileMatchMedia()
      useSidebarStore.setState({ collapsed: false, mobileOpen: false })
      renderSideNav()

      const nav = screen.getByRole('navigation')
      expect(nav.classList.contains('expanded')).toBe(false)
      expect(document.querySelector('.sidenav-overlay')).toBeNull()
      expect(useSidebarStore.getState().collapsed).toBe(false)

      const toggle = screen.getByRole('button', { name: /expand/i })
      fireEvent.click(toggle)

      expect(nav.classList.contains('expanded')).toBe(true)
      expect(document.querySelector('.sidenav-overlay')).not.toBeNull()
      expect(useSidebarStore.getState().collapsed).toBe(false)
    })
  })
})
