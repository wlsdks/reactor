import './OnboardingTour.css'
import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { useEscapeClose } from '../lib/useEscapeClose'
import { safeGet, safeSet } from '../lib/safeLocalStorage'
import { OverlayCloseButton } from './OverlayCloseButton'

export interface TourStep {
  /** Stable React key + analytics identifier. */
  id: string
  /** CSS selector targeting the element to spotlight. */
  selector: string
  /** Step title — already-resolved i18n string. */
  title: string
  /** Step description — already-resolved i18n string. */
  description: string
  /** Popover side relative to the cutout. Defaults to 'bottom'. */
  position?: 'top' | 'bottom' | 'left' | 'right'
}

export interface OnboardingTourProps {
  steps: TourStep[]
  /** localStorage key — when set, the tour is skipped on subsequent mounts. */
  storageKey: string
  /** Invoked when the user finishes the final step. */
  onComplete?: () => void
  /** Invoked when the user dismisses the tour (skip / ESC). */
  onSkip?: () => void
}

interface CutoutRect {
  top: number
  left: number
  width: number
  height: number
}

interface PopoverPosition {
  top: number
  left: number
}

const POPOVER_WIDTH = 360
const POPOVER_ESTIMATED_HEIGHT = 200
const SPOTLIGHT_PADDING = 8
const POPOVER_GAP = 16
const VIEWPORT_MARGIN = 12

function hasCompletedTour(key: string): boolean {
  return safeGet(key) !== null
}

function rectFromElement(el: Element): CutoutRect {
  const rect = el.getBoundingClientRect()
  return {
    top: rect.top - SPOTLIGHT_PADDING,
    left: rect.left - SPOTLIGHT_PADDING,
    width: rect.width + SPOTLIGHT_PADDING * 2,
    height: rect.height + SPOTLIGHT_PADDING * 2,
  }
}

/**
 * Compute popover coordinates relative to the cutout, clamped to the viewport
 * so the card never overflows the edges of small screens.
 */
function placePopover(
  rect: CutoutRect,
  position: TourStep['position'] = 'bottom',
): PopoverPosition {
  const viewportW = window.innerWidth
  const viewportH = window.innerHeight
  let top = 0
  let left = 0

  switch (position) {
    case 'top':
      top = rect.top - POPOVER_ESTIMATED_HEIGHT - POPOVER_GAP
      left = rect.left + rect.width / 2 - POPOVER_WIDTH / 2
      break
    case 'left':
      top = rect.top + rect.height / 2 - POPOVER_ESTIMATED_HEIGHT / 2
      left = rect.left - POPOVER_WIDTH - POPOVER_GAP
      break
    case 'right':
      top = rect.top + rect.height / 2 - POPOVER_ESTIMATED_HEIGHT / 2
      left = rect.left + rect.width + POPOVER_GAP
      break
    case 'bottom':
    default:
      top = rect.top + rect.height + POPOVER_GAP
      left = rect.left + rect.width / 2 - POPOVER_WIDTH / 2
      break
  }

  // Clamp to viewport so the popover stays fully visible.
  left = Math.max(VIEWPORT_MARGIN, Math.min(left, viewportW - POPOVER_WIDTH - VIEWPORT_MARGIN))
  top = Math.max(VIEWPORT_MARGIN, Math.min(top, viewportH - POPOVER_ESTIMATED_HEIGHT - VIEWPORT_MARGIN))
  return { top, left }
}

/**
 * First-login onboarding tour.
 *
 * Renders a translucent backdrop with a cutout window over each step's target
 * element and a popover beside it. Skips on subsequent mounts once the user
 * completes (or skips) the tour — persistence keyed by `storageKey`.
 */
export function OnboardingTour({ steps, storageKey, onComplete, onSkip }: OnboardingTourProps) {
  const { t } = useTranslation()
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const descriptionId = useId()
  const [active, setActive] = useState<boolean>(() => {
    if (steps.length === 0) return false
    if (typeof window === 'undefined') return false
    return !hasCompletedTour(storageKey)
  })
  const [stepIndex, setStepIndex] = useState(0)
  const [rect, setRect] = useState<CutoutRect | null>(null)

  const total = steps.length
  const current = steps[stepIndex]

  function dismiss() {
    if (!active) return
    setActive(false)
    safeSet(storageKey, new Date().toISOString())
    onSkip?.()
  }

  function complete() {
    if (!active) return
    setActive(false)
    safeSet(storageKey, new Date().toISOString())
    onComplete?.()
  }

  function next() {
    if (stepIndex >= total - 1) {
      complete()
      return
    }
    setStepIndex((i) => i + 1)
  }

  function previous() {
    setStepIndex((i) => Math.max(0, i - 1))
  }

  useEscapeClose(dismiss, { active })

  // Recompute the cutout rect whenever the active step changes or the
  // viewport scrolls / resizes. Re-runs on every step navigation.
  useEffect(() => {
    if (!active || !current) return
    function recalc() {
      const target = document.querySelector(current.selector)
      if (target) {
        setRect(rectFromElement(target))
      } else {
        setRect(null)
      }
    }
    recalc()
    window.addEventListener('resize', recalc)
    window.addEventListener('scroll', recalc, true)
    return () => {
      window.removeEventListener('resize', recalc)
      window.removeEventListener('scroll', recalc, true)
    }
  }, [active, current])

  if (!active || !current) return null

  const popover = rect ? placePopover(rect, current.position) : { top: 80, left: 80 }
  const isLast = stepIndex === total - 1
  const isFirst = stepIndex === 0

  return createPortal(
    <div className="onboarding-tour" data-testid="onboarding-tour">
      {/* Four-panel backdrop. When we don't have a rect yet (or the target
       * is missing) we fall back to a single full-screen shade so the user
       * still sees the popover with context. */}
      {rect ? (
        <>
          <div
            className="onboarding-tour__shade"
            style={{ top: 0, left: 0, right: 0, height: Math.max(0, rect.top) }}
            onClick={dismiss}
          />
          <div
            className="onboarding-tour__shade"
            style={{
              top: Math.max(0, rect.top),
              left: 0,
              width: Math.max(0, rect.left),
              height: rect.height,
            }}
            onClick={dismiss}
          />
          <div
            className="onboarding-tour__shade"
            style={{
              top: Math.max(0, rect.top),
              left: rect.left + rect.width,
              right: 0,
              height: rect.height,
            }}
            onClick={dismiss}
          />
          <div
            className="onboarding-tour__shade"
            style={{
              top: rect.top + rect.height,
              left: 0,
              right: 0,
              bottom: 0,
            }}
            onClick={dismiss}
          />
          <div
            className="onboarding-tour__cutout"
            style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
            aria-hidden="true"
          />
        </>
      ) : (
        <div
          className="onboarding-tour__shade"
          style={{ inset: 0 }}
          onClick={dismiss}
        />
      )}

      <div
        ref={dialogRef}
        className="onboarding-tour__popover"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        style={{ top: popover.top, left: popover.left, width: POPOVER_WIDTH }}
      >
        <OverlayCloseButton onClick={dismiss} label={t('common.aria.close')} />
        <span className="onboarding-tour__counter" data-testid="onboarding-tour-counter">
          {t('onboarding.tour.progress', { current: stepIndex + 1, total })}
        </span>
        <h2 id={titleId} className="onboarding-tour__title">
          {current.title}
        </h2>
        <p id={descriptionId} className="onboarding-tour__description">
          {current.description}
        </p>
        <div className="onboarding-tour__actions">
          <button
            type="button"
            className="onboarding-tour__btn onboarding-tour__btn--ghost"
            onClick={dismiss}
            data-testid="onboarding-tour-skip"
          >
            {t('onboarding.tour.skip')}
          </button>
          <div className="onboarding-tour__actions-right">
            <button
              type="button"
              className="onboarding-tour__btn"
              onClick={previous}
              disabled={isFirst}
              data-testid="onboarding-tour-previous"
            >
              {t('onboarding.tour.previous')}
            </button>
            <button
              type="button"
              className="onboarding-tour__btn onboarding-tour__btn--primary"
              onClick={next}
              data-testid="onboarding-tour-next"
            >
              {isLast ? t('onboarding.tour.complete') : t('onboarding.tour.next')}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  )
}
