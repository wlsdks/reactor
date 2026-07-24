import { useEffect } from 'react'

/**
 * Custom hook that executes a handler when the Escape key is pressed.
 * @param enabled - Activation condition (e.g., selectedId !== null && !deleteTarget)
 * @param handler - Function to execute when Escape key is pressed
 */
export function useEscapeKey(enabled: boolean, handler: () => void) {
  useEffect(() => {
    if (!enabled) return
    const fn = (e: KeyboardEvent) => { if (e.key === 'Escape') handler() }
    document.addEventListener('keydown', fn)
    return () => document.removeEventListener('keydown', fn)
  }, [enabled, handler])
}
