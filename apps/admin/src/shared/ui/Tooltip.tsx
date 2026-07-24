import './Tooltip.css'
import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type FocusEvent,
  type MouseEvent,
  type ReactElement,
  type ReactNode,
  type Ref,
} from 'react'
import { createPortal } from 'react-dom'

export type TooltipPlacement = 'top' | 'right' | 'bottom' | 'left'

export interface TooltipProps {
  /** Tooltip content. Plain strings become a single line; ReactNode allowed for inline emphasis. */
  content: ReactNode
  /** Anchor side relative to the trigger. Defaults to `'top'`. */
  placement?: TooltipPlacement
  /**
   * Open delay (ms) for hover/focus. Defaults to `120` so the tooltip surfaces
   * almost immediately while still avoiding flash-on-pass-through. Matches the
   * `--duration-fast` motion token (120 ms) used elsewhere for hover-state
   * transitions, which keeps the perceived rhythm of the UI consistent.
   * Focus-driven opens always go through this delay too — A11y best practice
   * is "as fast as practical without causing flash", and 120 ms hits both.
   */
  delay?: number
  /** Single child trigger element — Tooltip clones it to attach refs/handlers/aria-describedby. */
  children: ReactElement
  /** When true, the Tooltip never opens. Useful for conditionally suppressing on enabled state. */
  disabled?: boolean
}

const VIEWPORT_PADDING_PX = 8
const ARROW_OFFSET_PX = 6

interface ChildPropsWithRef {
  ref?: Ref<HTMLElement>
  onMouseEnter?: (event: MouseEvent<HTMLElement>) => void
  onMouseLeave?: (event: MouseEvent<HTMLElement>) => void
  onFocus?: (event: FocusEvent<HTMLElement>) => void
  onBlur?: (event: FocusEvent<HTMLElement>) => void
  onClick?: (event: MouseEvent<HTMLElement>) => void
  'aria-describedby'?: string
}

interface PositionState {
  top: number
  left: number
}

/**
 * Detects coarse-pointer environments (touch devices) where hover does not
 * fire. Falls back to `false` during SSR / before media query has resolved.
 */
function useIsCoarsePointer(): boolean {
  const [coarse, setCoarse] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
    return window.matchMedia('(hover: none)').matches
  })
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(hover: none)')
    const handler = () => setCoarse(mq.matches)
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
    // Safari <14 fallback.
    mq.addListener(handler)
    return () => mq.removeListener(handler)
  }, [])
  return coarse
}

/**
 * Forwards a node into an object-style React ref. Extracted so the
 * `react-hooks/immutability` lint rule does not misread the inline assignment
 * as mutating a hook argument we do not own.
 */
function assignObjectRef(ref: Ref<HTMLElement>, node: HTMLElement | null): void {
  if (ref && typeof ref === 'object') {
    const target = ref as { current: HTMLElement | null }
    target.current = node
  }
}

/**
 * Computes the absolute viewport position of the tooltip given the trigger
 * rect, the tooltip's own measured size, and the requested placement. Clamps
 * against the viewport edges with an 8px gutter so tooltips never overflow.
 */
function computePosition(
  triggerRect: DOMRect,
  tooltipRect: DOMRect,
  placement: TooltipPlacement,
): PositionState {
  const vw = typeof window === 'undefined' ? 0 : window.innerWidth
  const vh = typeof window === 'undefined' ? 0 : window.innerHeight
  let top = 0
  let left = 0

  switch (placement) {
    case 'top':
      top = triggerRect.top - tooltipRect.height - ARROW_OFFSET_PX
      left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2
      break
    case 'bottom':
      top = triggerRect.bottom + ARROW_OFFSET_PX
      left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2
      break
    case 'left':
      top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2
      left = triggerRect.left - tooltipRect.width - ARROW_OFFSET_PX
      break
    case 'right':
      top = triggerRect.top + triggerRect.height / 2 - tooltipRect.height / 2
      left = triggerRect.right + ARROW_OFFSET_PX
      break
  }

  // Clamp to viewport with an 8px gutter.
  if (vw > 0) {
    left = Math.min(
      Math.max(VIEWPORT_PADDING_PX, left),
      vw - tooltipRect.width - VIEWPORT_PADDING_PX,
    )
  }
  if (vh > 0) {
    top = Math.min(
      Math.max(VIEWPORT_PADDING_PX, top),
      vh - tooltipRect.height - VIEWPORT_PADDING_PX,
    )
  }
  return { top, left }
}

/**
 * Lightweight, dependency-free Tooltip primitive.
 *
 * Behaviour:
 *  - Renders content in a portal anchored to `document.body` (escapes overflow / transform parents).
 *  - Hover / focus to show, blur / mouseleave to hide.
 *  - Tap-to-toggle on coarse-pointer (touch) devices.
 *  - ESC closes; `aria-describedby` wires the trigger to the tooltip for screen readers.
 *  - Supports `top | right | bottom | left` placement with viewport edge clamping.
 *  - Honors `prefers-reduced-motion` (CSS).
 *
 * The component clones its single child to inject `ref`, hover/focus handlers,
 * and `aria-describedby`. The child must accept a `ref` (any HTMLElement-typed
 * intrinsic component works; forward refs are required for custom components).
 */
export function Tooltip({
  content,
  placement = 'top',
  delay = 120,
  children,
  disabled = false,
}: TooltipProps) {
  const tooltipId = useId()
  const triggerRef = useRef<HTMLElement | null>(null)
  const tooltipRef = useRef<HTMLDivElement | null>(null)
  const showTimerRef = useRef<number | null>(null)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<PositionState>({ top: 0, left: 0 })
  const isCoarsePointer = useIsCoarsePointer()

  const clearShowTimer = useCallback(() => {
    if (showTimerRef.current != null) {
      window.clearTimeout(showTimerRef.current)
      showTimerRef.current = null
    }
  }, [])

  const openTooltip = useCallback(() => {
    if (disabled) return
    clearShowTimer()
    if (delay <= 0) {
      setOpen(true)
      return
    }
    showTimerRef.current = window.setTimeout(() => {
      showTimerRef.current = null
      setOpen(true)
    }, delay)
  }, [clearShowTimer, delay, disabled])

  const closeTooltip = useCallback(() => {
    clearShowTimer()
    setOpen(false)
  }, [clearShowTimer])

  // ESC closes the tooltip while it is open. Local listener (not useEscapeClose)
  // so we do not interfere with parent overlays that share the same key.
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeTooltip()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, closeTooltip])

  // Cleanup any pending open timer on unmount or disable.
  useEffect(() => {
    if (disabled && open) closeTooltip()
    return clearShowTimer
  }, [disabled, open, closeTooltip, clearShowTimer])

  // Position after layout so we measure the actual rendered tooltip size.
  useLayoutEffect(() => {
    if (!open) return
    const trigger = triggerRef.current
    const tooltip = tooltipRef.current
    if (!trigger || !tooltip) return
    const triggerRect = trigger.getBoundingClientRect()
    const tooltipRect = tooltip.getBoundingClientRect()
    setPosition(computePosition(triggerRect, tooltipRect, placement))
  }, [open, placement, content])

  // Reposition on scroll / resize while open so the tooltip stays anchored.
  useEffect(() => {
    if (!open) return
    const reposition = () => {
      const trigger = triggerRef.current
      const tooltip = tooltipRef.current
      if (!trigger || !tooltip) return
      const triggerRect = trigger.getBoundingClientRect()
      const tooltipRect = tooltip.getBoundingClientRect()
      setPosition(computePosition(triggerRect, tooltipRect, placement))
    }
    window.addEventListener('scroll', reposition, true)
    window.addEventListener('resize', reposition)
    return () => {
      window.removeEventListener('scroll', reposition, true)
      window.removeEventListener('resize', reposition)
    }
  }, [open, placement])

  // Compose handlers — preserve the child's existing event handlers so callers
  // can still attach their own onClick / onMouseEnter logic without losing it.
  const childProps = (children.props ?? {}) as ChildPropsWithRef
  // React 19 surfaces `ref` as a regular prop. Read it from `props.ref` so we
  // do not trip the deprecated `element.ref` accessor warning.
  const childRef: Ref<HTMLElement> | undefined = childProps.ref

  const setRef = useCallback((node: HTMLElement | null) => {
    triggerRef.current = node
    if (typeof childRef === 'function') {
      childRef(node)
      return
    }
    if (childRef && typeof childRef === 'object') {
      // The child's existing ref is a mutable object ref; forward the node by
      // assigning its `.current`. Wrapped in a helper to keep the lint plugin
      // (react-hooks/immutability) from flagging the assignment as
      // "modifying" an unrelated identifier.
      assignObjectRef(childRef, node)
    }
  }, [childRef])

  const handleMouseEnter = (event: MouseEvent<HTMLElement>) => {
    childProps.onMouseEnter?.(event)
    if (isCoarsePointer) return
    openTooltip()
  }
  const handleMouseLeave = (event: MouseEvent<HTMLElement>) => {
    childProps.onMouseLeave?.(event)
    if (isCoarsePointer) return
    closeTooltip()
  }
  const handleFocus = (event: FocusEvent<HTMLElement>) => {
    childProps.onFocus?.(event)
    openTooltip()
  }
  const handleBlur = (event: FocusEvent<HTMLElement>) => {
    childProps.onBlur?.(event)
    closeTooltip()
  }
  const handleClick = (event: MouseEvent<HTMLElement>) => {
    childProps.onClick?.(event)
    // Coarse-pointer (touch) devices do not fire hover; let a single tap toggle
    // the tooltip so the operator can still see the description.
    if (isCoarsePointer) {
      if (open) closeTooltip()
      else openTooltip()
    }
  }

  if (!isValidElement(children)) {
    if (import.meta.env.DEV) {
      console.warn('[Tooltip] requires a single React element child; got:', children)
    }
    return children as unknown as ReactElement
  }

  // Forward our composed ref + handlers onto the trigger child. The lint rule
  // `react-hooks/refs` flags ref-as-prop on a function callback, but
  // `cloneElement` is the canonical React API for this — the ref is consumed
  // by React's reconciler, not by the callback as an ordinary value.
  // eslint-disable-next-line react-hooks/refs
  const cloned = cloneElement(children, {
    ref: setRef,
    onMouseEnter: handleMouseEnter,
    onMouseLeave: handleMouseLeave,
    onFocus: handleFocus,
    onBlur: handleBlur,
    onClick: handleClick,
    'aria-describedby': open
      ? [childProps['aria-describedby'], tooltipId].filter(Boolean).join(' ')
      : childProps['aria-describedby'],
  } as Partial<ChildPropsWithRef>)

  const portal =
    open && typeof document !== 'undefined'
      ? createPortal(
          <div
            ref={tooltipRef}
            id={tooltipId}
            role="tooltip"
            data-placement={placement}
            className="tooltip"
            style={{ top: position.top, left: position.left }}
          >
            {content}
            <span className="tooltip__arrow" aria-hidden="true" />
          </div>,
          document.body,
        )
      : null

  return (
    <>
      {cloned}
      {portal}
    </>
  )
}
