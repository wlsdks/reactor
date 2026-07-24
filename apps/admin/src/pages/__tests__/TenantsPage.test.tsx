import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider, useLocation } from 'react-router-dom'
import { render, screen } from '../../test/utils'
import userEvent from '@testing-library/user-event'
import { TenantsPage } from '../TenantsPage'
import { usePlatformAdminData } from '../../features/platform-admin'

vi.mock('../../features/platform-admin', () => ({
  usePlatformAdminData: vi.fn(),
  PlatformTenantsTab: ({
    onSelectTenant,
    onOpenTenantOperations,
  }: {
    onSelectTenant: (id: string | null) => void
    onOpenTenantOperations: (id: string) => void
  }) => (
    <div>
      <button type="button" onClick={() => onSelectTenant('tenant-2')}>Select tenant 2</button>
      <button type="button" onClick={() => onOpenTenantOperations('tenant-1')}>Open tenant 1 operations</button>
    </div>
  ),
}))

vi.mock('../../features/tenant-admin/ui/TenantAdminManager', () => ({
  TenantAdminManager: ({ tenantId, embedded }: { tenantId?: string; embedded?: boolean }) => (
    <div data-testid="tenant-operations" data-tenant-id={tenantId} data-embedded={String(embedded)} />
  ),
}))

const usePlatformAdminDataMock = vi.mocked(usePlatformAdminData)

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderPage(initialEntry = '/tenants') {
  const router = createMemoryRouter([
    {
      path: '/tenants',
      element: <><TenantsPage /><LocationProbe /></>,
    },
  ], { initialEntries: [initialEntry] })
  render(<RouterProvider router={router} />)
}

describe('TenantsPage', () => {
  beforeEach(() => {
    usePlatformAdminDataMock.mockReturnValue({
      tenants: [],
      isLoading: false,
      selectedTenant: null,
      tenantForm: { name: '', slug: '', plan: 'FREE' },
      saving: false,
      error: null,
      notice: null,
      setSelectedTenantId: vi.fn(),
      setTenantForm: vi.fn(),
      handleCreateTenant: vi.fn(),
      suspendMutation: { mutate: vi.fn() },
      activateMutation: { mutate: vi.fn() },
      handleRefresh: vi.fn(),
    } as never)
  })

  it('owns the page heading above the roster and operations tabs', () => {
    renderPage()

    const heading = screen.getByRole('heading', { level: 1, name: 'tenantsPage.title' })
    const tablist = screen.getByRole('tablist', { name: 'tenantsPage.tabsLabel' })
    expect(heading.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByRole('tab', { name: 'tenantsPage.tabRoster' })).toBeVisible()
    expect(screen.getByRole('tab', { name: 'tenantsPage.tabOperations' })).toBeVisible()
  })

  it('preserves roster selection in the URL and initializes the selected tenant query', async () => {
    const user = userEvent.setup()
    renderPage('/tenants?tab=admin&tenantId=tenant-1')

    expect(usePlatformAdminDataMock).toHaveBeenCalledWith('tenant-1', { tenants: true })
    await user.click(screen.getByRole('button', { name: 'Select tenant 2' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/tenants?tab=admin&tenantId=tenant-2')
  })

  it('opens selected tenant operations as an addressable embedded workspace', async () => {
    const user = userEvent.setup()
    renderPage('/tenants?tab=admin&tenantId=tenant-1')

    await user.click(screen.getByRole('button', { name: 'Open tenant 1 operations' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/tenants?tab=tenant&tenantId=tenant-1')
    expect(screen.getByTestId('tenant-operations')).toHaveAttribute('data-tenant-id', 'tenant-1')
    expect(screen.getByTestId('tenant-operations')).toHaveAttribute('data-embedded', 'true')
  })
})
