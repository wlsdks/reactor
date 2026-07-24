import { create } from 'zustand'

/**
 * Per-user desktop/tablet rail preference. Phone navigation uses a separate,
 * non-persistent overlay flag so a saved wide-screen preference cannot cover
 * the workspace after a viewport change.
 */
const STORAGE_KEY = 'reactor-admin-sidebar-collapsed'
/** Legacy key kept for one-way migration so existing users do not lose their setting. */
const LEGACY_STORAGE_KEY = 'reactor-sidebar-collapsed'

function loadCollapsed(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored !== null) return stored === 'true'
    // Migrate legacy key (best-effort; ignore storage errors).
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY)
    if (legacy !== null) {
      try { localStorage.setItem(STORAGE_KEY, legacy) } catch { /* noop */ }
      return legacy === 'true'
    }
    return true
  } catch {
    return true
  }
}

interface SidebarStore {
  collapsed: boolean
  /** Mobile navigation is intentionally ephemeral. A desktop/sidebar preference
   * must not reopen an off-canvas menu over a phone-sized workspace. */
  mobileOpen: boolean
  toggle: () => void
  close: () => void
  open: () => void
  toggleMobile: () => void
  closeMobile: () => void
}

export const useSidebarStore = create<SidebarStore>((set) => ({
  collapsed: loadCollapsed(),
  mobileOpen: false,
  toggle: () =>
    set((state) => {
      const next = !state.collapsed
      try { localStorage.setItem(STORAGE_KEY, String(next)) } catch { /* noop */ }
      return { collapsed: next }
    }),
  close: () => {
    try { localStorage.setItem(STORAGE_KEY, 'true') } catch { /* noop */ }
    set({ collapsed: true })
  },
  open: () => {
    try { localStorage.setItem(STORAGE_KEY, 'false') } catch { /* noop */ }
    set({ collapsed: false })
  },
  toggleMobile: () => set((state) => ({ mobileOpen: !state.mobileOpen })),
  closeMobile: () => set({ mobileOpen: false }),
}))
