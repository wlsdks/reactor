import { describe, expect, it, vi } from 'vitest'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { fireEvent, render, screen } from '../../test/utils'
import { AccessControlPage } from '../AccessControlPage'

vi.mock('../../features/rbac', () => ({
  RbacManager: ({ embedded }: { embedded?: boolean }) => <div>{embedded ? 'embedded permissions' : 'permissions'}</div>,
}))

vi.mock('../../features/platform-admin', () => ({
  usePlatformAdminData: () => ({
    userLookupEmail: '', selectedUser: null, selectedUserRole: 'USER', updatingUserRole: false,
    userLookupLoading: false, selectedUserError: null, error: null,
    setUserLookupEmail: vi.fn(), setSelectedUserRole: vi.fn(), handleLookupUser: vi.fn(), handleUpdateUserRole: vi.fn(),
  }),
  PlatformUserRolesTab: () => <div>member permissions</div>,
}))

function renderPage(initialEntry = '/access-control') {
  const router = createMemoryRouter(
    [{ path: '/access-control', element: <AccessControlPage /> }],
    { initialEntries: [initialEntry] },
  )
  render(<RouterProvider router={router} />)
  return router
}

describe('AccessControlPage', () => {
  it('renders one page heading before the URL-addressable permission tabs', () => {
    renderPage()

    expect(screen.getByRole('heading', { level: 1, name: 'accessControlPage.title' })).toBeVisible()
    expect(screen.getByText('accessControlPage.description')).toBeVisible()
    expect(screen.getByText('embedded permissions')).toBeVisible()
  })

  it('preserves the selected member workspace in the URL', async () => {
    const router = renderPage()

    fireEvent.click(screen.getByRole('tab', { name: 'accessControlPage.tabMembers' }))

    expect(await screen.findByText('member permissions')).toBeVisible()
    expect(router.state.location.search).toBe('?tab=members')
  })
})
