import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import { FeatureRoute } from '../FeatureRoute'
import { useFeatureAvailability } from '../context'
import { useRoleVisibility } from '../../workspace'

vi.mock('../context', () => ({
  useFeatureAvailability: vi.fn(),
}))

vi.mock('../../workspace', () => ({
  useRoleVisibility: vi.fn(),
}))

const useFeatureAvailabilityMock = vi.mocked(useFeatureAvailability)
const useRoleVisibilityMock = vi.mocked(useRoleVisibility)

function setRoleVisibility(isVisible: boolean) {
  useRoleVisibilityMock.mockReturnValue({
    role: 'ADMIN',
    effectiveRole: 'ADMIN',
    viewAsManager: false,
    canToggleViewAs: true,
    toggleViewAsManager: vi.fn(),
    isRouteVisible: vi.fn().mockReturnValue(isVisible),
    getVisibleNavGroups: vi.fn().mockReturnValue([]),
  })
}

describe('FeatureRoute', () => {
  beforeEach(() => {
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => false,
    })
    setRoleVisibility(true)
  })

  // ────────────────────────────────────────────────────────────────────────
  // Loading state
  // ────────────────────────────────────────────────────────────────────────

  it('renders the loading spinner while capability data is loading', () => {
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: true,
      mode: 'manifest',
      isRouteAvailable: () => true,
    })

    const { container } = render(
      <MemoryRouter>
        <FeatureRoute routePath="/x" titleKey="nav.foo">
          <div>protected-content</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    expect(container.querySelector('.page-loading')).not.toBeNull()
    expect(screen.queryByText('protected-content')).not.toBeInTheDocument()
  })

  // ────────────────────────────────────────────────────────────────────────
  // Happy path: route available + visible
  // ────────────────────────────────────────────────────────────────────────

  it('renders children when capability is available and role has access', () => {
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => true,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/dashboard" titleKey="nav.dashboard">
          <div>dashboard-content</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    expect(screen.getByText('dashboard-content')).toBeInTheDocument()
  })

  // ────────────────────────────────────────────────────────────────────────
  // allowWhenUnavailable bypass
  // ────────────────────────────────────────────────────────────────────────

  it('renders recovery pages even when the capability manifest hides the route', () => {
    render(
      <MemoryRouter>
        <FeatureRoute routePath="/tool-policy" titleKey="nav.toolPolicy" allowWhenUnavailable>
          <div>recovery-console</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    expect(screen.getByText('recovery-console')).toBeInTheDocument()
  })

  it('still blocks allowWhenUnavailable routes when role visibility denies access', () => {
    // Permission denied takes precedence over allowWhenUnavailable.
    setRoleVisibility(false)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => false,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/tool-policy" titleKey="nav.toolPolicy" allowWhenUnavailable>
          <div>should-not-render</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('permission-denied-page')).toBeInTheDocument()
    expect(screen.queryByText('should-not-render')).not.toBeInTheDocument()
  })

  // ────────────────────────────────────────────────────────────────────────
  // Permission-denied page (BX audit blind spot #6)
  // ────────────────────────────────────────────────────────────────────────

  it('renders the permission-denied page when the role lacks visibility for the route', () => {
    setRoleVisibility(false)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => true,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/dev-tools/foo" titleKey="nav.devTools">
          <div>dev-only-content</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('permission-denied-page')).toBeInTheDocument()
    // 처음으로 recovery action — escapes the dead-end. Tests run with the
    // i18n stub that returns keys verbatim, so match on the translation key.
    const homeLink = screen.getByRole('link', { name: 'error.permissionDeniedAction' })
    expect(homeLink).toHaveAttribute('href', '/')
    // The protected children must NOT render
    expect(screen.queryByText('dev-only-content')).not.toBeInTheDocument()
  })

  it('shows the route titleKey within the permission-denied page header', () => {
    setRoleVisibility(false)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => true,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/admin/secret" titleKey="nav.adminSecret">
          <div>nope</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    // Page header title text comes from the i18n stub which echoes the key.
    expect(screen.getByText('nav.adminSecret')).toBeInTheDocument()
  })

  // ────────────────────────────────────────────────────────────────────────
  // Feature-disabled fallback
  // ────────────────────────────────────────────────────────────────────────

  it('shows the feature-disabled empty state when capability is unavailable and visibility allows', () => {
    setRoleVisibility(true)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => false,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/tool-policy" titleKey="nav.toolPolicy">
          <div>protected-content</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    // Feature-disabled wrapper should render and protected children should not.
    expect(screen.queryByText('protected-content')).not.toBeInTheDocument()
    expect(screen.queryByTestId('permission-denied-page')).not.toBeInTheDocument()
    // Title from PageHeader is echoed by the i18n stub.
    expect(screen.getByText('nav.toolPolicy')).toBeInTheDocument()
  })

  it('explains an unavailable server capability without a nested empty-state card', () => {
    setRoleVisibility(true)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => false,
    })

    const { container } = render(
      <MemoryRouter>
        <FeatureRoute routePath="/sessions" titleKey="nav.sessions">
          <div>protected-content</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('feature-unavailable-page')).toBeInTheDocument()
    expect(screen.getByText('common.featureUnavailableTitle')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'common.openStatusPage' })).toHaveAttribute('href', '/health')
    expect(container.querySelector('.detail-panel')).toBeNull()
    expect(container.querySelector('pre')).toBeNull()
  })

  it('does not render the dev-only requirements details block in production mode', () => {
    // import.meta.env.DEV is true under vitest by default; spy via stubEnv.
    vi.stubEnv('DEV', false as unknown as string)
    setRoleVisibility(true)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => false,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/tool-policy" titleKey="nav.toolPolicy">
          <div>protected</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    // technicalDetails summary should not be present in production mode.
    expect(screen.queryByText('common.technicalDetails')).not.toBeInTheDocument()
    vi.unstubAllEnvs()
  })

  it('renders the dev-only requirements details block in dev mode (mode echoed in details)', () => {
    vi.stubEnv('DEV', true as unknown as string)
    setRoleVisibility(true)
    useFeatureAvailabilityMock.mockReturnValue({
      isLoading: false,
      mode: 'manifest',
      isRouteAvailable: () => false,
    })

    render(
      <MemoryRouter>
        <FeatureRoute routePath="/tool-policy" titleKey="nav.toolPolicy">
          <div>protected</div>
        </FeatureRoute>
      </MemoryRouter>,
    )

    // The collapsed <details> should be present with the developer-information summary.
    expect(screen.getByText('common.featureUnavailableTechnical')).toBeInTheDocument()
    vi.unstubAllEnvs()
  })
})
