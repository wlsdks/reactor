import { useEffect } from 'react'

interface UseEscapeCloseOptions {
  /** Whether the listener is active. Defaults to true. */
  active?: boolean
}

/**
 * Closes an overlay (Modal / Drawer / ConfirmDialog) when the Escape key is
 * pressed. Single canonical hook used by every shared overlay primitive so we
 * don't duplicate `keydown` listeners across components.
 *
 * @param onClose - Handler invoked on Escape.
 * @param options.active - When false, no listener is attached. Defaults to true.
 *
 * @example
 *   useEscapeClose(onClose, { active: open })
 */
export function useEscapeClose(onClose: () => void, options: UseEscapeCloseOptions = {}) {
  const { active = true } = options
  useEffect(() => {
    if (!active) return
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [active, onClose])
}
