import { describe, it, expect, beforeEach } from 'vitest'
import {
  __reloadSidenavGroupsStoreForTests,
  __resetSidenavGroupsStoreForTests,
  useSidenavGroupsStore,
} from '../sidenav-groups.store'

const STORAGE_KEY = 'reactor-admin-sidenav-collapsed-groups'

describe('sidenav-groups.store', () => {
  beforeEach(() => {
    __resetSidenavGroupsStoreForTests()
  })

  it('starts with only the core operation groups expanded', () => {
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.today')).toBe(false)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.releaseOps')).toBe(false)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.aiConfig')).toBe(true)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.devTools')).toBe(true)
  })

  it('preserves an explicitly saved all-expanded preference', () => {
    window.localStorage.setItem(STORAGE_KEY, '[]')
    __reloadSidenavGroupsStoreForTests()

    expect(useSidenavGroupsStore.getState().collapsedGroups.size).toBe(0)
  })

  it('toggleGroup adds the key on first call and removes it on second', () => {
    const { toggleGroup, isCollapsed } = useSidenavGroupsStore.getState()

    toggleGroup('nav.group.today')
    expect(isCollapsed('nav.group.today')).toBe(true)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.today')).toBe(true)

    toggleGroup('nav.group.today')
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.today')).toBe(false)
  })

  it('persists toggled groups to localStorage as a JSON array', () => {
    useSidenavGroupsStore.getState().toggleGroup('nav.group.today')
    useSidenavGroupsStore.getState().toggleGroup('nav.group.aiConfig')

    const raw = window.localStorage.getItem(STORAGE_KEY)
    expect(raw).not.toBeNull()
    const parsed = JSON.parse(raw!) as string[]
    expect(parsed).toContain('nav.group.today')
    expect(parsed).not.toContain('nav.group.aiConfig')
  })

  it('removes the key from localStorage when toggled back open', () => {
    useSidenavGroupsStore.getState().expandAllGroups([
      'nav.group.today',
      'nav.group.aiConfig',
      'nav.group.safetyPolicy',
      'nav.group.monitoring',
      'nav.group.analytics',
      'nav.group.administration',
      'nav.group.devTools',
    ])
    useSidenavGroupsStore.getState().toggleGroup('nav.group.today')
    useSidenavGroupsStore.getState().toggleGroup('nav.group.today')

    const raw = window.localStorage.getItem(STORAGE_KEY)
    expect(raw).toBe('[]')
  })

  it('falls back to the core view for malformed localStorage payloads', () => {
    window.localStorage.setItem(STORAGE_KEY, 'not-valid-json')
    __reloadSidenavGroupsStoreForTests()

    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.today')).toBe(false)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.monitoring')).toBe(true)
  })

  it('switches only visible groups between core and expanded views', () => {
    const visibleGroups = [
      'nav.group.today',
      'nav.group.releaseOps',
      'nav.group.monitoring',
    ]
    const store = useSidenavGroupsStore.getState()

    store.expandAllGroups(visibleGroups)
    expect(useSidenavGroupsStore.getState().areAllGroupsExpanded(visibleGroups)).toBe(true)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.devTools')).toBe(true)

    store.focusCoreGroups(visibleGroups)
    expect(useSidenavGroupsStore.getState().isCoreView(visibleGroups)).toBe(true)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.today')).toBe(false)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.releaseOps')).toBe(false)
    expect(useSidenavGroupsStore.getState().isCollapsed('nav.group.monitoring')).toBe(true)
  })
})
