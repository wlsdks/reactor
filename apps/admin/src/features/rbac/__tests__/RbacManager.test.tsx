import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor, fireEvent, i18n } from '../../../test/utils'
import { RbacManager } from '../ui/RbacManager'
import * as rbacApi from '../api'
import type { Role, Permission } from '../types'
import { ApiError } from '../../../shared/api/errors'

vi.mock('../api', () => ({
  listRoles: vi.fn(),
  assignUserRole: vi.fn(),
}))

vi.mock('../../../shared/store/toast.store', () => ({
  useToastStore: {
    getState: () => ({ addToast: vi.fn() }),
  },
}))

const listRolesMock = vi.mocked(rbacApi.listRoles)

function perm(resource: string, action: string): Permission {
  return { id: `${resource}:${action}`, resource, action }
}

const adminRole: Role = {
  id: 'ADMIN',
  name: 'ADMIN',
  description: 'FULL',
  isSystem: true,
  permissions: [
    perm('persona', 'read'), perm('persona', 'write'),
    perm('session', 'read'), perm('session', 'export'),
    perm('user', 'read'), perm('user', 'write'),
  ],
  memberCount: 0,
  createdAt: 0,
}

const devRole: Role = {
  id: 'ADMIN_DEVELOPER',
  name: 'ADMIN_DEVELOPER',
  description: 'DEVELOPER',
  isSystem: true,
  permissions: [
    perm('persona', 'read'), perm('persona', 'write'),
    perm('session', 'read'),
  ],
  memberCount: 0,
  createdAt: 0,
}

const userRole: Role = {
  id: 'USER',
  name: 'USER',
  description: '',
  isSystem: true,
  permissions: [perm('chat', 'use'), perm('persona', 'select')],
  memberCount: 0,
  createdAt: 0,
}

describe('RbacManager', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.retry': 'Retry',
      'common.retrying': 'Retrying',
      'common.openStatusPage': 'Open status',
      'common.technicalDetails': 'Technical details',
      'rbacPage.title': 'Access control',
      'rbacPage.subtitle': 'Review role permissions.',
      'rbacPage.roleSelectorDescription': 'Select a role to review its permissions.',
      'rbacPage.roleSelectorHint': 'Select one role to review it or two to compare them.',
      'rbacPage.selectedRoleCount': '{{count}} role selected',
      'rbacPage.comparingRoles': 'Comparing two roles.',
      'rbacPage.selectRole': 'Select a role.',
      'rbacPage.roles': 'Roles',
      'rbacPage.noRoles': 'No roles',
      'rbacPage.noRolesDescription': 'Roles will appear here.',
      'rbacPage.unavailableTitle': 'Role permissions unavailable',
      'rbacPage.unavailableDescription': 'Changes are paused.',
      'rbacPage.accessDeniedTitle': 'Role permissions denied',
      'rbacPage.accessDeniedDescription': 'Check access.',
      'rbacPage.recoveryTitle': 'How to check',
      'rbacPage.recoveryAccount': 'Check account.',
      'rbacPage.recoveryConnection': 'Check connection.',
      'rbacPage.refreshFailed': 'Showing the last verified roles.',
      'rbacPage.permissionCount': '{{count}} permissions',
      'rbacPage.onlyThisRole': 'Only this role',
      'rbacPage.missingPermissions': 'Only the other role',
      'rbacPage.commonPermissions': 'Shared permissions',
      'rbacPage.roleNames.ADMIN': 'Full admin',
      'rbacPage.roleNames.ADMIN_DEVELOPER': 'Developer admin',
      'rbacPage.roleNames.ADMIN_MANAGER': 'Operations admin',
      'rbacPage.roleNames.USER': 'User',
      'rbacPage.roleNames.unknown': 'Unknown role',
      'rbacPage.roleDescriptions.ADMIN': 'Manages all operations.',
      'rbacPage.roleDescriptions.ADMIN_DEVELOPER': 'Manages developer operations.',
      'rbacPage.roleDescriptions.ADMIN_MANAGER': 'Manages daily operations.',
      'rbacPage.roleDescriptions.USER': 'Uses approved features.',
      'rbacPage.roleDescriptions.unknown': 'Review this role carefully.',
      'rbacPage.groups.ai': 'AI settings',
      'rbacPage.groups.security': 'Safety operations',
      'rbacPage.groups.system': 'System management',
      'rbacPage.groups.chat': 'Chat features',
      'rbacPage.actions.read': 'Read',
      'rbacPage.actions.write': 'Change',
      'rbacPage.actions.export': 'Export',
      'rbacPage.actions.use': 'Use',
      'rbacPage.actions.select': 'Select',
      'rbacPage.actions.unknown': 'Permission needs review',
      'rbacPage.resources.persona': 'Persona',
      'rbacPage.resources.prompt': 'Prompt',
      'rbacPage.resources.eval': 'Evaluation',
      'rbacPage.resources.session': 'Sessions',
      'rbacPage.resources.feedback': 'Feedback',
      'rbacPage.resources.guard': 'Safety rules',
      'rbacPage.resources.mcp': 'External tools',
      'rbacPage.resources.scheduler': 'Automation',
      'rbacPage.resources.tenant': 'Organization management',
      'rbacPage.resources.slack': 'Slack connection',
      'rbacPage.resources.audit': 'Audit history',
      'rbacPage.resources.user': 'Members',
      'rbacPage.resources.settings': 'Settings',
      'rbacPage.resources.agent-spec': 'AI roles',
      'rbacPage.resources.chat': 'AI chat',
      'rbacPage.resources.unknown': 'Unknown permission target',
    }, true, true)
    listRolesMock.mockResolvedValue([adminRole, devRole, userRole])
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders a role list instead of pills after loading', async () => {
    const view = render(<MemoryRouter><RbacManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Access control')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { pressed: true })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /Full admin/i })).toBeInTheDocument()
    expect(view.container.querySelector('.rbac-pill')).not.toBeInTheDocument()
    expect(view.container.querySelector('.rbac-role-selector__row')).toBeInTheDocument()
  })

  it('keeps role review focused without a release workflow backlink', async () => {
    render(<MemoryRouter><RbacManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Access control')).toBeInTheDocument()
    })

    expect(screen.queryByRole('link', { name: 'common.releaseWorkflowBacklinkStep' })).not.toBeInTheDocument()
  })

  it('shows an open permission list for the default role', async () => {
    const view = render(<MemoryRouter><RbacManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Safety operations')).toBeInTheDocument()
    })
    expect(screen.getByRole('heading', { level: 2, name: 'Full admin' })).toBeInTheDocument()
    expect(view.container.querySelector('.rbac-card')).not.toBeInTheDocument()
    expect(view.container.querySelector('.rbac-role-detail')).toBeInTheDocument()
  })

  it('shows diff view when two pills are selected', async () => {
    render(<MemoryRouter><RbacManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Safety operations')).toBeInTheDocument()
    })

    const adminRoleButton = screen.getByRole('button', { name: /Full admin/i })
    fireEvent.click(adminRoleButton)

    const devRoleButton = screen.getByRole('button', { name: /Developer admin/i })
    fireEvent.click(devRoleButton)

    await waitFor(() => {
      expect(screen.getAllByText('Shared permissions')).toHaveLength(2)
    })
  })

  it('deselects second pill to return to single card view', async () => {
    render(<MemoryRouter><RbacManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('Safety operations')).toBeInTheDocument()
    })

    const adminRoleButton = screen.getByRole('button', { name: /Full admin/i })
    fireEvent.click(adminRoleButton)

    const devRoleButton = screen.getByRole('button', { name: /Developer admin/i })
    fireEvent.click(devRoleButton)

    await waitFor(() => {
      expect(screen.getAllByText('Shared permissions')).toHaveLength(2)
    })

    fireEvent.click(devRoleButton)

    await waitFor(() => {
      expect(screen.queryAllByText('Shared permissions')).toHaveLength(0)
    })
    expect(screen.getByText('Safety operations')).toBeInTheDocument()
  })

  it('shows empty state when no roles from API', async () => {
    listRolesMock.mockResolvedValue([])
    render(<MemoryRouter><RbacManager /></MemoryRouter>)
    await waitFor(() => {
      expect(screen.getByText('No roles')).toBeInTheDocument()
    })
  })

  it('shows skeleton placeholder while fetching', () => {
    listRolesMock.mockReturnValue(new Promise(() => {}))
    render(<MemoryRouter><RbacManager /></MemoryRouter>)
    expect(document.querySelector('.skeleton-table-v2')).toBeInTheDocument()
  })

  it('fails closed when listRoles returns 403', async () => {
    listRolesMock.mockRejectedValue(
      new ApiError(403, 'FORBIDDEN', 'Forbidden'),
    )
    render(<MemoryRouter><RbacManager /></MemoryRouter>)

    await waitFor(() => {
      expect(screen.getByText('Role permissions denied')).toBeInTheDocument()
    })
    expect(screen.queryByText('No roles')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
  })

  it('does not represent a failed role request as an empty role list', async () => {
    listRolesMock.mockRejectedValue(new Error('HTTP 503'))
    render(<MemoryRouter><RbacManager embedded /></MemoryRouter>)

    expect(await screen.findByText('Role permissions unavailable')).toBeVisible()
    expect(screen.queryByText('No roles')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Access control' })).not.toBeInTheDocument()
  })

  it('does not expose unknown role or permission identifiers to operators', async () => {
    listRolesMock.mockResolvedValue([{
      ...adminRole,
      id: 'INTERNAL_ROLE',
      name: 'INTERNAL_ROLE',
      permissions: [perm('internal_resource', 'operate')],
    }])

    render(<MemoryRouter><RbacManager /></MemoryRouter>)

    expect(await screen.findAllByText('Unknown role')).toHaveLength(2)
    expect(screen.getByText('Unknown permission target')).toBeInTheDocument()
    expect(screen.getByText('Permission needs review')).toBeInTheDocument()
    expect(screen.queryByText('INTERNAL_ROLE')).not.toBeInTheDocument()
    expect(screen.queryByText('internal_resource')).not.toBeInTheDocument()
    expect(screen.queryByText('operate')).not.toBeInTheDocument()
  })

  it('uses human labels for every permission resource returned by the Reactor role contract', async () => {
    listRolesMock.mockResolvedValue([{
      ...adminRole,
      permissions: [perm('eval', 'read'), perm('tenant', 'write'), perm('slack', 'write')],
    }])

    render(<MemoryRouter><RbacManager /></MemoryRouter>)

    expect(await screen.findByText('Evaluation')).toBeInTheDocument()
    expect(screen.getByText('Organization management')).toBeInTheDocument()
    expect(screen.getByText('Slack connection')).toBeInTheDocument()
    expect(screen.queryByText('Unknown permission target')).not.toBeInTheDocument()
    expect(screen.queryByText('eval')).not.toBeInTheDocument()
    expect(screen.queryByText('tenant')).not.toBeInTheDocument()
    expect(screen.queryByText('slack')).not.toBeInTheDocument()
  })
})
