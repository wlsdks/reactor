import { createContext, useContext, useState, type ReactNode } from 'react'
import { useAuth } from '../auth'
import { getVisibleNavGroupsByRole, isRouteVisibleByRole } from './navigation'
import { STORAGE_KEYS, safeGet, safeRemove, safeSet } from '../../shared/lib/safeLocalStorage'
import type { AdminRole, NavGroup } from '../../shared/types/navigation'

interface RoleVisibilityValue {
  /** The user's actual auth role. Undefined for non-admin users. */
  role: AdminRole | undefined
  /**
   * The role used for UI filtering. Usually equal to `role`, but ADMIN users
   * can preview the ADMIN_MANAGER view via the `viewAsManager` toggle.
   */
  effectiveRole: AdminRole | undefined
  /** Whether the ADMIN user is currently previewing the manager view. */
  viewAsManager: boolean
  /** Whether the ADMIN preview toggle is available to the current user. */
  canToggleViewAs: boolean
  /** Toggle the ADMIN preview mode (only effective for ADMIN role). */
  toggleViewAsManager: () => void
  /** Check whether a route is visible to the effective role. */
  isRouteVisible: (path: string) => boolean
  /** Get the filtered nav groups for the effective role. */
  getVisibleNavGroups: (isRouteAvailable: (path: string) => boolean) => NavGroup[]
}

const RoleVisibilityContext = createContext<RoleVisibilityValue | undefined>(undefined)

function toAdminRole(role: string | undefined): AdminRole | undefined {
  if (role === 'ADMIN' || role === 'ADMIN_MANAGER' || role === 'ADMIN_DEVELOPER') return role
  return undefined
}

function readStoredViewAs(): boolean {
  return safeGet(STORAGE_KEYS.viewAs) === 'manager'
}

function writeStoredViewAs(viewAsManager: boolean): void {
  if (viewAsManager) {
    safeSet(STORAGE_KEYS.viewAs, 'manager')
  } else {
    safeRemove(STORAGE_KEYS.viewAs)
  }
}

export function RoleVisibilityProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const role = toAdminRole(user?.role)
  const canToggleViewAs = role === 'ADMIN'

  const [viewAsManagerRaw, setViewAsManagerRaw] = useState<boolean>(() =>
    canToggleViewAs ? readStoredViewAs() : false,
  )

  // If the user can't toggle (non-ADMIN or logged out), force false.
  const viewAsManager = canToggleViewAs ? viewAsManagerRaw : false

  const toggleViewAsManager = () => {
    setViewAsManagerRaw((prev) => {
      const next = !prev
      writeStoredViewAs(next)
      return next
    })
  }

  const effectiveRole: AdminRole | undefined = !role
    ? undefined
    : canToggleViewAs && viewAsManager
      ? 'ADMIN_MANAGER'
      : role

  const value: RoleVisibilityValue = {
    role,
    effectiveRole,
    viewAsManager,
    canToggleViewAs,
    toggleViewAsManager,
    isRouteVisible: (path: string) => {
      if (!effectiveRole) return false
      return isRouteVisibleByRole(path, effectiveRole)
    },
    getVisibleNavGroups: (isRouteAvailable) => {
      if (!effectiveRole) return []
      return getVisibleNavGroupsByRole(effectiveRole, isRouteAvailable)
    },
  }

  return (
    <RoleVisibilityContext.Provider value={value}>
      {children}
    </RoleVisibilityContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useRoleVisibility(): RoleVisibilityValue {
  const ctx = useContext(RoleVisibilityContext)
  if (!ctx) throw new Error('useRoleVisibility must be used within RoleVisibilityProvider')
  return ctx
}
