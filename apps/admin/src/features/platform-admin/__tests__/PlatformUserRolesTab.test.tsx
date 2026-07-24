import { beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n, render, screen } from '../../../test/utils'
import { PlatformUserRolesTab } from '../ui/PlatformUserRolesTab'
import { ApiError } from '../../../shared/api/errors'
import { MemoryRouter } from 'react-router-dom'

const baseProps = {
  userLookupEmail: '',
  selectedUser: null,
  selectedUserRole: 'USER' as const,
  updatingUserRole: false,
  userLookupLoading: false,
  lookupError: null,
  updateError: null,
  onUserLookupEmailChange: vi.fn(),
  onSelectedUserRoleChange: vi.fn(),
  onLookupUser: vi.fn(),
  onUpdateUserRole: vi.fn(),
}

describe('PlatformUserRolesTab', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'common.retry': 'Retry',
      'common.retrying': 'Retrying',
      'common.openStatusPage': 'Open status',
      'common.technicalDetails': 'Technical details',
      'accessControlPage.memberLookupUnavailableTitle': 'Member lookup unavailable',
      'accessControlPage.memberLookupUnavailableDescription': 'Member changes are paused.',
      'accessControlPage.memberUpdateFailed': 'Could not update member access.',
      'accessControlPage.scopeNone': 'Not assigned',
      'accessControlPage.scopeUnknown': 'Unknown scope',
      'accessControlPage.roleLabels.USER': '일반 사용자',
      'accessControlPage.roleLabels.ADMIN_MANAGER': '운영 관리자',
      'accessControlPage.roleLabels.ADMIN_DEVELOPER': '개발 관리자',
      'accessControlPage.roleLabels.ADMIN': '전체 관리자',
      'accessControlPage.scopeLabels.FULL': '전체 관리',
      'accessControlPage.scopeLabels.MANAGER': '운영 관리',
      'accessControlPage.scopeLabels.DEVELOPER': '개발 관리',
    }, true, true)
  })

  it('shows an instructional state before a lookup and disables an empty search', () => {
    render(<PlatformUserRolesTab {...baseProps} />)

    expect(screen.getByText('platformAdminPage.noUserSelected')).toBeInTheDocument()
    expect(screen.getByText('accessControlPage.memberLookupEmpty')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'platformAdminPage.lookupUser' })).toBeDisabled()
    expect(document.querySelectorAll('.detail-panel')).toHaveLength(0)
  })

  it('distinguishes a failed lookup from no selection', () => {
    render(<PlatformUserRolesTab {...baseProps} userLookupEmail="missing@example.com" lookupError={new ApiError(404, 'NOT_FOUND', 'Not found')} />)

    expect(screen.getByText('accessControlPage.memberNotFoundTitle')).toBeInTheDocument()
    expect(screen.getByText('accessControlPage.memberNotFoundDescription')).toBeInTheDocument()
    expect(screen.queryByText('platformAdminPage.noUserSelected')).not.toBeInTheDocument()
  })

  it('fails closed when a member lookup cannot be verified', () => {
    render(
      <MemoryRouter>
        <PlatformUserRolesTab {...baseProps} userLookupEmail="admin@example.com" lookupError={new Error('HTTP 503')} />
      </MemoryRouter>,
    )

    expect(screen.getByText('Member lookup unavailable')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Open status' })).toHaveAttribute('href', '/health')
    expect(screen.queryByText('platformAdminPage.noUserSelected')).not.toBeInTheDocument()
  })

  it('humanizes role and scope values and prevents a no-op update', () => {
    render(<PlatformUserRolesTab {...baseProps} userLookupEmail="admin@example.com" selectedUser={{ id: 'u-1', email: 'admin@example.com', name: 'Admin', role: 'ADMIN_DEVELOPER', adminScope: 'DEVELOPER', createdAt: '2026-07-01T00:00:00Z' }} selectedUserRole="ADMIN_DEVELOPER" />)

    expect(screen.getAllByText('개발 관리자')).toHaveLength(2)
    expect(screen.getByText('개발 관리')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'platformAdminPage.updateRole' })).toBeDisabled()
    expect(screen.queryByText('ADMIN_DEVELOPER')).not.toBeInTheDocument()
  })

  it('keeps backend update detail closed behind a clear recovery message', () => {
    render(<PlatformUserRolesTab {...baseProps} userLookupEmail="admin@example.com" selectedUser={{ id: 'u-1', email: 'admin@example.com', name: 'Admin', role: 'ADMIN_DEVELOPER', adminScope: 'DEVELOPER', createdAt: '2026-07-01T00:00:00Z' }} selectedUserRole="ADMIN" updateError="HTTP 500: upstream role mutation failed" />)

    expect(screen.getByText('Could not update member access.')).toBeInTheDocument()
    const technicalDetails = screen.getByText('Technical details').closest('details')
    expect(technicalDetails).not.toHaveAttribute('open')
    expect(technicalDetails).toHaveTextContent('upstream role mutation failed')
  })
})
