import { useEffect } from 'react'
import { create } from 'zustand'

interface PageHelpState {
  /** i18n key for the active page's help content (string array). */
  helpKey: string | null
  /** Whether the help overlay is currently open. */
  isOpen: boolean
  setHelpKey: (key: string | null) => void
  open: () => void
  close: () => void
}

/**
 * Global store backing the page-level help overlay. The active page
 * registers its i18n key via {@link usePageHelp}, and the
 * {@link import('../ui/PageHelpOverlay').PageHelpOverlay} component reads
 * `helpKey` + `isOpen` to render the dynamic content section.
 */
export const usePageHelpStore = create<PageHelpState>((set) => ({
  helpKey: null,
  isOpen: false,
  setHelpKey: (key) => set({ helpKey: key }),
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
}))

interface UsePageHelpOptions {
  /**
   * i18n key whose value MUST be a string array of short Korean lines
   * describing what the page does and key actions.
   */
  helpKey: string
}

interface UsePageHelpReturn {
  /** Open the help overlay programmatically. */
  open: () => void
  /** Close the help overlay programmatically. */
  close: () => void
  /** Whether the overlay is currently open. */
  isOpen: boolean
  /** Currently registered i18n key (or null if none registered). */
  helpKey: string | null
}

/**
 * Registers a page-level help i18n key while the calling component is
 * mounted. On unmount the key is cleared (only if the current value
 * still matches the one registered by this hook), so navigating between
 * pages always shows the right help content.
 *
 * Pages should call this once near the top of their `Manager` / `View`
 * component:
 *
 * ```tsx
 * usePageHelp({ helpKey: 'dashboardPage.help' })
 * ```
 *
 * The actual `?` / `h` keypress listener and overlay rendering live in
 * {@link import('../ui/PageHelpOverlay').PageHelpOverlay}, which is
 * mounted once in `AdminLayout`.
 */
export function usePageHelp({ helpKey }: UsePageHelpOptions): UsePageHelpReturn {
  const setHelpKey = usePageHelpStore((s) => s.setHelpKey)
  const open = usePageHelpStore((s) => s.open)
  const close = usePageHelpStore((s) => s.close)
  const isOpen = usePageHelpStore((s) => s.isOpen)
  const currentKey = usePageHelpStore((s) => s.helpKey)

  useEffect(() => {
    setHelpKey(helpKey)
    return () => {
      // Only clear if the active key is still ours — prevents clobbering
      // a sibling page that already registered itself during a fast
      // route transition.
      const latest = usePageHelpStore.getState().helpKey
      if (latest === helpKey) {
        setHelpKey(null)
      }
    }
  }, [helpKey, setHelpKey])

  return { open, close, isOpen, helpKey: currentKey }
}
