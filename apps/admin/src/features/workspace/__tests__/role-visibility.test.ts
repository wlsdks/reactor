import { describe, it, expect } from 'vitest'
import { isRouteVisibleByRole, getVisibleNavGroupsByRole } from '../navigation'

describe('isRouteVisibleByRole', () => {
  it('returns true for the root path regardless of role', () => {
    expect(isRouteVisibleByRole('/', 'ADMIN')).toBe(true)
    expect(isRouteVisibleByRole('/', 'ADMIN_MANAGER')).toBe(true)
    expect(isRouteVisibleByRole('/', 'ADMIN_DEVELOPER')).toBe(true)
  })

  it('unknown routes default-deny for ADMIN_MANAGER and default-allow for developers', () => {
    expect(isRouteVisibleByRole('/nonexistent', 'ADMIN_MANAGER')).toBe(false)
    expect(isRouteVisibleByRole('/nonexistent', 'ADMIN_DEVELOPER')).toBe(true)
    expect(isRouteVisibleByRole('/nonexistent', 'ADMIN')).toBe(true)
  })

  it('shared routes (visibleTo: "all") are visible to all admin roles', () => {
    // /feedback, /sessions, /usage, /tenants, /health, /issues are visibleTo: 'all'
    expect(isRouteVisibleByRole('/feedback', 'ADMIN_MANAGER')).toBe(true)
    expect(isRouteVisibleByRole('/feedback', 'ADMIN_DEVELOPER')).toBe(true)
    expect(isRouteVisibleByRole('/health', 'ADMIN_MANAGER')).toBe(true)
  })

  it('respects an explicit role allowlist when visibleTo restricts the item', () => {
    // /personas is restricted to ['ADMIN', 'ADMIN_DEVELOPER']
    expect(isRouteVisibleByRole('/personas', 'ADMIN')).toBe(true)
    expect(isRouteVisibleByRole('/personas', 'ADMIN_DEVELOPER')).toBe(true)
    expect(isRouteVisibleByRole('/personas', 'ADMIN_MANAGER')).toBe(false)
  })
})

describe('getVisibleNavGroupsByRole', () => {
  const allowAll = () => true

  it('returns all groups for ADMIN when all routes available', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN', allowAll)
    expect(groups.length).toBeGreaterThan(0)
    const itemCount = groups.reduce((sum, g) => sum + g.items.length, 0)
    expect(itemCount).toBeGreaterThan(0)
  })

  it('keeps release operations visible even when routes are not advertised', () => {
    const groups = getVisibleNavGroupsByRole('ADMIN', () => false)
    expect(groups).toHaveLength(2)
    expect(groups[0].titleKey).toBe('nav.group.releaseOps')
    expect(groups[0].items.some((item) => item.path.startsWith('/feedback'))).toBe(true)
    expect(groups[1].titleKey).toBe('nav.group.administration')
    expect(groups[1].items.map((item) => item.path)).toEqual(['/tenants', '/settings'])
  })

  it('ADMIN and ADMIN_DEVELOPER see the same items; ADMIN_MANAGER sees a strict subset', () => {
    const adminGroups = getVisibleNavGroupsByRole('ADMIN', allowAll)
    const managerGroups = getVisibleNavGroupsByRole('ADMIN_MANAGER', allowAll)
    const devGroups = getVisibleNavGroupsByRole('ADMIN_DEVELOPER', allowAll)

    const count = (gs: typeof adminGroups) => gs.reduce((s, g) => s + g.items.length, 0)
    // ADMIN and ADMIN_DEVELOPER see all items
    expect(count(adminGroups)).toBe(count(devGroups))
    // ADMIN_MANAGER sees fewer items (role-restricted nav)
    expect(count(managerGroups)).toBeLessThan(count(adminGroups))
    expect(count(managerGroups)).toBeGreaterThan(0)
  })
})
