import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, renderHook } from '../../../test/utils'
import { RoleVisibilityProvider, useRoleVisibility } from '../RoleVisibilityProvider'

const mockUseAuth = vi.fn()
vi.mock('../../auth', () => ({
  useAuth: () => mockUseAuth(),
}))

function VisibilityStatus() {
  const { role, isRouteVisible } = useRoleVisibility()
  return (
    <div>
      <div data-testid="role">{role ?? 'none'}</div>
      <div data-testid="dashboard">{String(isRouteVisible('/'))}</div>
      <div data-testid="personas">{String(isRouteVisible('/personas'))}</div>
    </div>
  )
}

describe('RoleVisibilityProvider', () => {
  beforeEach(() => {
    mockUseAuth.mockReset()
  })

  it('throws when used outside provider', () => {
    mockUseAuth.mockReturnValue({ user: null })
    expect(() => renderHook(() => useRoleVisibility())).toThrow(
      /useRoleVisibility must be used within RoleVisibilityProvider/,
    )
  })

  it('returns role: undefined and isRouteVisible: false when user has no role', () => {
    mockUseAuth.mockReturnValue({ user: null })
    render(
      <RoleVisibilityProvider>
        <VisibilityStatus />
      </RoleVisibilityProvider>,
    )
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(screen.getByTestId('dashboard')).toHaveTextContent('false')
  })

  it('exposes ADMIN role and visible routes', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 'u1', name: 'A', email: 'a@x', role: 'ADMIN' },
    })
    render(
      <RoleVisibilityProvider>
        <VisibilityStatus />
      </RoleVisibilityProvider>,
    )
    expect(screen.getByTestId('role')).toHaveTextContent('ADMIN')
    expect(screen.getByTestId('dashboard')).toHaveTextContent('true')
    expect(screen.getByTestId('personas')).toHaveTextContent('true')
  })

  it('exposes ADMIN_MANAGER role and hides developer-only routes', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 'u2', name: 'M', email: 'm@x', role: 'ADMIN_MANAGER' },
    })
    render(
      <RoleVisibilityProvider>
        <VisibilityStatus />
      </RoleVisibilityProvider>,
    )
    expect(screen.getByTestId('role')).toHaveTextContent('ADMIN_MANAGER')
    // PR6a: /personas is restricted to ['ADMIN', 'ADMIN_DEVELOPER']
    expect(screen.getByTestId('personas')).toHaveTextContent('false')
    // Dashboard is shared and remains visible
    expect(screen.getByTestId('dashboard')).toHaveTextContent('true')
  })

  it('returns undefined role for non-admin USER role', () => {
    mockUseAuth.mockReturnValue({
      user: { id: 'u3', name: 'U', email: 'u@x', role: 'USER' },
    })
    render(
      <RoleVisibilityProvider>
        <VisibilityStatus />
      </RoleVisibilityProvider>,
    )
    expect(screen.getByTestId('role')).toHaveTextContent('none')
    expect(screen.getByTestId('dashboard')).toHaveTextContent('false')
  })
})
