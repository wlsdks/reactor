import { useEffect, type RefObject } from 'react'

const DEFAULT_FORM_FIELD_SELECTOR = [
  'input:not([type="hidden"]):not([disabled]):not([readonly])',
  'textarea:not([disabled]):not([readonly])',
  'select:not([disabled])',
].join(', ')

interface UseFormFirstFieldFocusOptions {
  /**
   * Delay (ms) before attempting to focus. Allows modal open / mount
   * animations to finish so the first field is actually visible.
   * @default 50
   */
  delay?: number
  /**
   * Override the default focusable form-field selector.
   *
   * The default selector targets enabled, non-hidden, non-readonly inputs,
   * textareas, and selects. Elements that are also `aria-hidden="true"` are
   * filtered out post-query so a custom selector does not need to handle them.
   */
  selector?: string
}

/**
 * When `open` becomes true, focus the first focusable form input inside
 * `containerRef`. Skips disabled, readonly, hidden, and `aria-hidden`
 * elements.
 *
 * Designed for form modals that should auto-focus the first user-editable
 * field (rather than the modal's close button) on open. Pair with
 * `useFocusTrap` on the surrounding modal so Tab cycling still works.
 *
 * Default selector:
 *   `input:not([type="hidden"]):not([disabled]):not([readonly]),
 *    textarea:not([disabled]):not([readonly]),
 *    select:not([disabled])`
 */
export function useFormFirstFieldFocus(
  containerRef: RefObject<HTMLElement | null>,
  open: boolean,
  options?: UseFormFirstFieldFocusOptions,
): void {
  const delay = options?.delay ?? 50
  const selector = options?.selector ?? DEFAULT_FORM_FIELD_SELECTOR

  useEffect(() => {
    if (!open) return

    const timeoutId = window.setTimeout(() => {
      const container = containerRef.current
      if (!container) return

      const candidates = container.querySelectorAll<HTMLElement>(selector)
      for (const candidate of candidates) {
        // Filter out aria-hidden and elements inside aria-hidden subtrees.
        if (candidate.closest('[aria-hidden="true"]')) continue
        candidate.focus({ preventScroll: false })
        return
      }
    }, delay)

    return () => {
      window.clearTimeout(timeoutId)
    }
  }, [open, containerRef, delay, selector])
}
