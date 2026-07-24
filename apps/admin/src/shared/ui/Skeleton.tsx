import type { CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'

// ─────────────────────────────────────────────────────────────────────────────
// Skeleton primitives
//
// A small family of dark-theme shimmer placeholders used across the admin UI.
// They exist to eliminate layout shift on initial load: a skeleton should
// roughly match the final rendered block's dimensions so content "settles
// into place" rather than snapping down.
//
// Design notes:
// - Shimmer animation is driven by .skeleton-base via the existing `shimmer`
//   keyframes in shared-components.css. We deliberately reuse the same
//   animation token as the legacy .skeleton-line so bespoke skeletons and
//   these primitives share one visual rhythm.
// - prefers-reduced-motion: reduce disables the animation (see CSS below).
// - Default radius is var(--radius-sm) (4px) to match table cells and inputs.
// ─────────────────────────────────────────────────────────────────────────────

type Size = string | number

function toCss(size: Size | undefined): string | undefined {
  if (size === undefined) return undefined
  return typeof size === 'number' ? `${size}px` : size
}

interface SkeletonProps {
  width?: Size
  height?: Size
  radius?: Size
  className?: string
  style?: CSSProperties
  /** Inline block vs block. Defaults to block. */
  inline?: boolean
  /** Optional aria-label override. Defaults to i18n common.aria.loading. */
  ariaLabel?: string
}

export function Skeleton({
  width,
  height = 14,
  radius,
  className,
  style,
  inline,
  ariaLabel,
}: SkeletonProps) {
  const { t } = useTranslation()
  const classes = ['skeleton-base']
  if (inline) classes.push('skeleton-base--inline')
  if (className) classes.push(className)

  const mergedStyle: CSSProperties = {
    width: toCss(width),
    height: toCss(height),
    borderRadius: toCss(radius),
    ...style,
  }

  return (
    <span
      className={classes.join(' ')}
      style={mergedStyle}
      role="status"
      aria-busy="true"
      aria-label={ariaLabel ?? t('common.aria.loading')}
    />
  )
}

interface SkeletonTextProps {
  lines?: number
  width?: Size
  /** Optional width for the last line (e.g. '60%') to feel more natural. */
  lastLineWidth?: Size
  className?: string
}

export function SkeletonText({
  lines = 1,
  width = '100%',
  lastLineWidth,
  className,
}: SkeletonTextProps) {
  const classes = ['skeleton-text']
  if (className) classes.push(className)
  return (
    <div className={classes.join(' ')}>
      {Array.from({ length: lines }, (_, i) => {
        const isLast = i === lines - 1
        const lineWidth = isLast && lastLineWidth !== undefined ? lastLineWidth : width
        return (
          <Skeleton
            key={i}
            width={lineWidth}
            height={12}
          />
        )
      })}
    </div>
  )
}

interface SkeletonCardProps {
  height?: Size
  className?: string
  /**
   * Render multiple identical card placeholders. Defaults to 1.
   *
   * Use this when a loading state needs to mirror a fixed-size grid (e.g. a
   * 6-card stat row or a 4-card config grid) instead of writing
   * `Array.from({ length: n }).map(<SkeletonCard ... key=i />)` at every call
   * site. The repeated nodes are siblings under the parent grid container, so
   * the surrounding layout (`stat-row`, `agent-grid`, etc.) still drives the
   * column rules.
   */
  count?: number
}

export function SkeletonCard({ height = 80, className, count = 1 }: SkeletonCardProps) {
  const classes = ['skeleton-card']
  if (className) classes.push(className)
  const classNameJoined = classes.join(' ')

  const renderOne = (key?: number) => (
    <Skeleton
      key={key}
      className={classNameJoined}
      width="100%"
      height={height}
      radius="var(--radius-md)"
    />
  )

  if (count <= 1) return renderOne()

  // Render as a fragment so the parent grid (e.g. .stat-row, .agent-grid)
  // continues to control column layout — we deliberately do not introduce a
  // wrapping element that could collapse the grid.
  return <>{Array.from({ length: count }, (_, i) => renderOne(i))}</>
}

interface SkeletonTableProps {
  rows?: number
  columns?: number
  className?: string
}

export function SkeletonTable({
  rows = 6,
  columns = 4,
  className,
}: SkeletonTableProps) {
  const { t } = useTranslation()
  const classes = ['skeleton-table-v2']
  if (className) classes.push(className)
  return (
    <div
      className={classes.join(' ')}
      aria-busy="true"
      aria-label={t('common.aria.loading')}
    >
      <div className="skeleton-table-v2__header">
        {Array.from({ length: columns }, (_, i) => (
          <div key={i} className="skeleton-table-v2__cell">
            <Skeleton width={`${55 + ((i * 17) % 30)}%`} height={12} />
          </div>
        ))}
      </div>
      {Array.from({ length: rows }, (_, ri) => (
        <div key={ri} className="skeleton-table-v2__row">
          {Array.from({ length: columns }, (_, ci) => (
            <div key={ci} className="skeleton-table-v2__cell">
              <Skeleton
                width={`${45 + (((ri * columns) + ci) * 17 % 40)}%`}
                height={12}
              />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

interface SkeletonChartProps {
  height?: Size
  className?: string
}

export function SkeletonChart({ height = 280, className }: SkeletonChartProps) {
  const { t } = useTranslation()
  const classes = ['skeleton-chart']
  if (className) classes.push(className)
  return (
    <div
      className={classes.join(' ')}
      style={{ height: toCss(height) }}
      aria-busy="true"
      aria-label={t('common.aria.loading')}
    >
      <div className="skeleton-chart__bars">
        {Array.from({ length: 12 }, (_, i) => {
          // Deterministic pseudo-random heights so reloads look stable and
          // tests don't flake.
          const pct = 30 + ((i * 37) % 60)
          return (
            <span
              key={i}
              className="skeleton-chart__bar skeleton-base"
              style={{ height: `${pct}%` }}
            />
          )
        })}
      </div>
    </div>
  )
}
