import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useEscapeClose } from '../lib/useEscapeClose'

/**
 * A single row-level action surfaced inside `RowContextMenu`.
 *
 * The action functions are called with the row that opened the menu, which
 * keeps the action definitions stateless and lets callers reuse a single
 * action list across many rows.
 */
export interface RowAction<T> {
  /** Stable identifier used as a React key and `data-action-id` attribute. */
  id: string
  /** Localized label shown in the menu. */
  label: string
  /** Optional leading icon node. */
  icon?: ReactNode
  /** Invoked when the action is selected. */
  perform: (row: T) => void
  /** Returns true to dim the action and ignore clicks. */
  disabled?: (row: T) => boolean
  /** Returns true to omit the action entirely from the menu. */
  hidden?: (row: T) => boolean
  /** Renders the label in the destructive (error) accent colour. */
  destructive?: boolean
}

interface RowContextMenuProps<T> {
  /** The row that opened the menu. Passed to every action callback. */
  row: T
  /** Action definitions; hidden entries are filtered out before rendering. */
  actions: RowAction<T>[]
  /**
   * Anchor coordinates in viewport space. The menu is clamped to fit inside
   * the viewport (with an 8px margin) so it never spills off-screen. When
   * `null`, nothing is rendered.
   */
  position: { x: number; y: number } | null
  /** Called when the menu should close (Escape, outside click, or invoke). */
  onClose: () => void
}

/** Margin between the menu and the viewport edge when clamping. */
const VIEWPORT_MARGIN_PX = 8

export function RowContextMenu<T>({ row, actions, position, onClose }: RowContextMenuProps<T>) {
  const { t } = useTranslation()
  const menuRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([])
  const [activeIndex, setActiveIndex] = useState(0)

  // Filter hidden actions once per render — `enabledActions` is the canonical
  // list keyboard navigation walks across.
  const enabledActions = actions.filter((a) => !a.hidden?.(row))

  useEscapeClose(onClose, { active: position != null })

  // Clamp the menu inside the viewport once layout has settled. We mutate the
  // DOM directly (no setState) so the layout effect cannot cascade renders;
  // the menu is rendered with `visibility: hidden` until the clamp resolves
  // to avoid any pre-clamp flash.
  useLayoutEffect(() => {
    const node = menuRef.current
    if (position == null || !node) return
    const rect = node.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    let left = position.x
    let top = position.y
    if (left + rect.width > vw - VIEWPORT_MARGIN_PX) {
      left = Math.max(VIEWPORT_MARGIN_PX, vw - rect.width - VIEWPORT_MARGIN_PX)
    }
    if (top + rect.height > vh - VIEWPORT_MARGIN_PX) {
      top = Math.max(VIEWPORT_MARGIN_PX, vh - rect.height - VIEWPORT_MARGIN_PX)
    }
    if (left < VIEWPORT_MARGIN_PX) left = VIEWPORT_MARGIN_PX
    if (top < VIEWPORT_MARGIN_PX) top = VIEWPORT_MARGIN_PX
    node.style.left = `${left}px`
    node.style.top = `${top}px`
    node.style.visibility = 'visible'
    // Reset selection + focus the first item now that the menu is in place.
    itemRefs.current[0]?.focus()
  }, [position, enabledActions.length])

  // Note: the parent (DataTable) sets `menuState` to null between opens, so
  // this component fully unmounts when closed. That means `useState(0)` above
  // already gives us a fresh selection on every fresh anchor — no reset
  // effect needed.

  // Outside-click closes the menu. Listener is attached only while open so we
  // don't pay the cost on every page.
  useEffect(() => {
    if (position == null) return
    function handlePointerDown(event: MouseEvent) {
      const node = menuRef.current
      if (!node) return
      if (event.target instanceof Node && node.contains(event.target)) return
      onClose()
    }
    // Use capture so we beat any stopPropagation handlers on the page.
    document.addEventListener('mousedown', handlePointerDown, true)
    return () => document.removeEventListener('mousedown', handlePointerDown, true)
  }, [position, onClose])

  // Move focus when the active index changes (keyboard navigation).
  useLayoutEffect(() => {
    if (position == null) return
    itemRefs.current[activeIndex]?.focus()
  }, [activeIndex, position])

  if (position == null || enabledActions.length === 0) return null

  function invoke(action: RowAction<T>) {
    if (action.disabled?.(row)) return
    action.perform(row)
    onClose()
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((prev) => (prev + 1) % enabledActions.length)
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((prev) => (prev - 1 + enabledActions.length) % enabledActions.length)
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const action = enabledActions[activeIndex]
      if (action) invoke(action)
    }
  }

  // Initial render uses the raw position; the layout effect immediately
  // measures, clamps, and flips visibility on. `visibility: hidden` keeps the
  // menu measurable while invisible to avoid flicker.
  const style: React.CSSProperties = {
    position: 'fixed',
    left: position.x,
    top: position.y,
    visibility: 'hidden',
  }

  return createPortal(
    <div
      ref={menuRef}
      className="row-context-menu"
      role="menu"
      aria-label={t('common.rowActions.menuLabel')}
      style={style}
      onKeyDown={handleKeyDown}
      onContextMenu={(event) => event.preventDefault()}
    >
      {enabledActions.map((action, index) => {
        const isDisabled = !!action.disabled?.(row)
        const classes = [
          'row-context-menu__item',
          action.destructive ? 'row-context-menu__item--destructive' : '',
          isDisabled ? 'row-context-menu__item--disabled' : '',
          index === activeIndex ? 'row-context-menu__item--active' : '',
        ].filter(Boolean).join(' ')
        return (
          <button
            key={action.id}
            ref={(el) => { itemRefs.current[index] = el }}
            type="button"
            role="menuitem"
            className={classes}
            data-action-id={action.id}
            aria-disabled={isDisabled || undefined}
            disabled={isDisabled}
            onMouseEnter={() => setActiveIndex(index)}
            onClick={(event) => {
              event.stopPropagation()
              invoke(action)
            }}
          >
            {action.icon && (
              <span className="row-context-menu__icon" aria-hidden="true">{action.icon}</span>
            )}
            <span className="row-context-menu__label">{action.label}</span>
          </button>
        )
      })}
    </div>,
    document.body,
  )
}
