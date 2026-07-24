import { useEffect, useRef, useState, type RefObject } from 'react'

export interface ScrollAffordance<T extends HTMLElement> {
  /** Attach to the scrollable container. */
  ref: RefObject<T | null>
  /** True when the user can still scroll up (top fade should show). */
  canScrollUp: boolean
  /** True when the user can still scroll down (bottom fade should show). */
  canScrollDown: boolean
}

/** Distance (in px) from each edge before the affordance flips off. */
const EDGE_THRESHOLD = 10

/**
 * Tracks scroll position on a container ref and returns whether top/bottom
 * fade indicators should be visible. Re-evaluates on `scroll` events and on
 * size changes via `ResizeObserver`.
 *
 * @param deps Re-runs the subscription when any value changes (e.g. when
 *   the rendered list mutates and changes the scroll height).
 */
export function useScrollAffordance<T extends HTMLElement = HTMLDivElement>(
  deps: ReadonlyArray<unknown> = [],
): ScrollAffordance<T> {
  const ref = useRef<T | null>(null)
  const [canScrollUp, setCanScrollUp] = useState(false)
  const [canScrollDown, setCanScrollDown] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    function updateScrollState() {
      if (!el) return
      const { scrollTop, scrollHeight, clientHeight } = el
      setCanScrollUp(scrollTop > EDGE_THRESHOLD)
      setCanScrollDown(scrollTop + clientHeight < scrollHeight - EDGE_THRESHOLD)
    }

    updateScrollState()
    el.addEventListener('scroll', updateScrollState, { passive: true })

    const observer = new ResizeObserver(updateScrollState)
    observer.observe(el)

    return () => {
      el.removeEventListener('scroll', updateScrollState)
      observer.disconnect()
    }
  }, deps)

  return { ref, canScrollUp, canScrollDown }
}
