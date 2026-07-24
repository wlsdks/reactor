import { describe, expect, it, vi } from 'vitest'
import type { ComponentProps } from 'react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { PlatformTenantsTab } from '../ui/PlatformTenantsTab'
import type { Tenant } from '../types'

const tenant: Tenant = {
  id: 'tenant-1',
  name: 'Reactor Team',
  slug: 'reactor-team',
  plan: 'BUSINESS',
  status: 'ACTIVE',
  quota: { maxRequestsPerMonth: 1000, maxTokensPerMonth: 100000, maxUsers: 10, maxAgents: 5, maxMcpServers: 5 },
  billingCycleStart: 1,
  billingEmail: null,
  sloAvailability: 99.9,
  sloLatencyP99Ms: 3000,
  metadata: {},
  createdAt: '2026-07-01T00:00:00Z',
  updatedAt: '2026-07-01T00:00:00Z',
}

const baseProps = {
  tenants: [] as Tenant[],
  isLoading: false,
  selectedTenant: null,
  tenantForm: { name: '', slug: '', plan: 'FREE' as const },
  saving: false,
  tenantsError: null,
  selectedTenantError: null,
  onRetry: vi.fn(),
  onSelectTenant: vi.fn(),
  onOpenTenantOperations: vi.fn(),
  onTenantFormChange: vi.fn(),
  onCreateTenant: vi.fn(),
  onSuspendTenant: vi.fn(),
  onActivateTenant: vi.fn(),
}

function renderTab(overrides: Partial<ComponentProps<typeof PlatformTenantsTab>> = {}) {
  return render(<MemoryRouter><PlatformTenantsTab {...baseProps} {...overrides} /></MemoryRouter>)
}

describe('PlatformTenantsTab', () => {
  it('keeps creation collapsed until the operator requests it', async () => {
    const user = userEvent.setup()
    renderTab()

    expect(document.querySelector('form')).not.toBeInTheDocument()
    await user.click(screen.getAllByRole('button', { name: 'Create Tenant' })[0])
    expect(document.querySelector('form')).toBeInTheDocument()
  })

  it('renders human status labels and only the valid state transition in the selected detail', () => {
    renderTab({ tenants: [tenant], selectedTenant: tenant })

    expect(screen.getAllByText('비즈니스')).toHaveLength(2)
    expect(screen.getAllByText('운영 중')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'platformAdminPage.suspend' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'platformAdminPage.activate' })).not.toBeInTheDocument()
    expect(document.querySelectorAll('.badge')).toHaveLength(0)
  })

  it('keeps state-changing actions out of the organization list', () => {
    renderTab({ tenants: [tenant] })

    expect(screen.queryByRole('button', { name: 'platformAdminPage.suspend' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'platformAdminPage.activate' })).not.toBeInTheDocument()
  })

  it('keeps organization-wide usage out of the roster until an organization is selected', () => {
    renderTab({ tenants: [tenant] })

    expect(screen.queryByRole('heading', { name: 'platformAdminPage.tenantAnalytics' })).not.toBeInTheDocument()
    expect(screen.queryByText('platformAdminPage.noAnalytics')).not.toBeInTheDocument()
  })

  it('distinguishes a failed tenant request from a valid empty roster', () => {
    renderTab({ tenantsError: new Error('HTTP 503') })

    expect(screen.getByText('tenantsPage.loadErrorTitle')).toBeInTheDocument()
    expect(screen.getByText('HTTP 503')).toBeInTheDocument()
    expect(screen.queryByText('platformAdminPage.noTenants')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create Tenant' })).not.toBeInTheDocument()
    expect(screen.queryByText('platformAdminPage.tenantAnalytics')).not.toBeInTheDocument()
  })

})
