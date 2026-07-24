import { create } from 'zustand'
import { STORAGE_KEYS, safeGetJson, safeRemove, safeSetJson } from '../lib/safeLocalStorage'

/**
 * Per-user sidebar group collapse preferences.
 *
 * Each entry in the persisted set is a `NavGroup.titleKey` (e.g. `nav.group.today`).
 * Membership in the set means the group is collapsed; absence means open.
 *
 * Existing preferences always win, including an explicitly persisted empty
 * array. New or malformed preferences start in the product-focused view:
 * Today and Release Operations stay open while secondary operator groups are
 * collapsed.
 */
const CORE_GROUP_KEYS = new Set([
  'nav.group.today',
  'nav.group.releaseOps',
  'nav.managerGroup.todayGlance',
  'nav.managerGroup.usage',
  'nav.managerGroup.organization',
])

const DEFAULT_COLLAPSED_GROUP_KEYS = [
  'nav.group.aiConfig',
  'nav.group.safetyPolicy',
  'nav.group.monitoring',
  'nav.group.analytics',
  'nav.group.administration',
  'nav.group.devTools',
] as const

function defaultCollapsedGroups(): Set<string> {
  return new Set(DEFAULT_COLLAPSED_GROUP_KEYS)
}

function loadCollapsedGroups(): Set<string> {
  const parsed = safeGetJson<unknown>(STORAGE_KEYS.sidenavCollapsedGroups)
  if (!Array.isArray(parsed)) return defaultCollapsedGroups()
  return new Set(parsed.filter((v): v is string => typeof v === 'string'))
}

function persistCollapsedGroups(set: Set<string>): void {
  safeSetJson(STORAGE_KEYS.sidenavCollapsedGroups, [...set])
}

interface SidenavGroupsStore {
  collapsedGroups: Set<string>
  isCollapsed: (titleKey: string) => boolean
  isCoreView: (visibleTitleKeys: string[]) => boolean
  areAllGroupsExpanded: (visibleTitleKeys: string[]) => boolean
  toggleGroup: (titleKey: string) => void
  focusCoreGroups: (visibleTitleKeys: string[]) => void
  expandAllGroups: (visibleTitleKeys: string[]) => void
}

function updateVisibleGroups(
  collapsedGroups: Set<string>,
  visibleTitleKeys: string[],
  shouldCollapse: (titleKey: string) => boolean,
): Set<string> {
  const visibleKeys = new Set(visibleTitleKeys)
  const next = new Set([...collapsedGroups].filter((key) => !visibleKeys.has(key)))
  for (const titleKey of visibleTitleKeys) {
    if (shouldCollapse(titleKey)) next.add(titleKey)
  }
  return next
}

export const useSidenavGroupsStore = create<SidenavGroupsStore>((set, get) => ({
  collapsedGroups: loadCollapsedGroups(),
  isCollapsed: (titleKey) => get().collapsedGroups.has(titleKey),
  isCoreView: (visibleTitleKeys) => visibleTitleKeys.every((titleKey) => (
    CORE_GROUP_KEYS.has(titleKey)
      ? !get().collapsedGroups.has(titleKey)
      : get().collapsedGroups.has(titleKey)
  )),
  areAllGroupsExpanded: (visibleTitleKeys) => (
    visibleTitleKeys.every((titleKey) => !get().collapsedGroups.has(titleKey))
  ),
  toggleGroup: (titleKey) =>
    set((state) => {
      const next = new Set(state.collapsedGroups)
      if (next.has(titleKey)) {
        next.delete(titleKey)
      } else {
        next.add(titleKey)
      }
      persistCollapsedGroups(next)
      return { collapsedGroups: next }
    }),
  focusCoreGroups: (visibleTitleKeys) =>
    set((state) => {
      const next = updateVisibleGroups(
        state.collapsedGroups,
        visibleTitleKeys,
        (titleKey) => !CORE_GROUP_KEYS.has(titleKey),
      )
      persistCollapsedGroups(next)
      return { collapsedGroups: next }
    }),
  expandAllGroups: (visibleTitleKeys) =>
    set((state) => {
      const next = updateVisibleGroups(state.collapsedGroups, visibleTitleKeys, () => false)
      persistCollapsedGroups(next)
      return { collapsedGroups: next }
    }),
}))

// Test helper — resets store + storage. Not used in production code.
export function __resetSidenavGroupsStoreForTests(): void {
  safeRemove(STORAGE_KEYS.sidenavCollapsedGroups)
  useSidenavGroupsStore.setState({ collapsedGroups: defaultCollapsedGroups() })
}

export function __reloadSidenavGroupsStoreForTests(): void {
  useSidenavGroupsStore.setState({ collapsedGroups: loadCollapsedGroups() })
}
