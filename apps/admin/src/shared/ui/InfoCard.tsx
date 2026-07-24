import type { ReactNode } from 'react'

export type InfoCardVariant = 'default' | 'success' | 'warning' | 'error'

export interface InfoCardProps {
  /**
   * Header title — string or any node (e.g. wrapping <code> or <strong>).
   * Rendered as a strong-styled element on the left of the header row.
   */
  title: ReactNode
  /**
   * Optional element rendered to the right of the title. Most commonly a
   * <StatusBadge>. Allows the header row to mirror the existing
   * `detail-section-header` pattern (title left, badge/meta right).
   */
  headerExtra?: ReactNode
  /**
   * Optional sub-line rendered underneath the title row.
   */
  subtitle?: ReactNode
  /**
   * Body content — can include text, meta-grid, tag-list, code blocks, etc.
   */
  children?: ReactNode
  /**
   * Optional bottom action row (e.g. <button> or <Link>). Rendered after body
   * with consistent spacing.
   */
  actions?: ReactNode
  /**
   * Visual variant. `success`/`warning`/`error` add a left accent border.
   * Default has the standard border treatment.
   */
  variant?: InfoCardVariant
  /**
   * When provided, the whole card becomes a clickable <button> with keyboard
   * support and a focus-visible ring.
   */
  onClick?: () => void
  /**
   * Accessible label override. Defaults to the string form of `title` when
   * omitted; callers should set this explicitly when `title` is non-string.
   */
  ariaLabel?: string
  /**
   * Stable key passthrough for tests. Falls through to the rendered root.
   */
  testId?: string
}

function deriveAriaLabel(title: ReactNode, ariaLabel?: string): string | undefined {
  if (ariaLabel) return ariaLabel
  if (typeof title === 'string') return title
  if (typeof title === 'number') return String(title)
  return undefined
}

export function InfoCard({
  title,
  headerExtra,
  subtitle,
  children,
  actions,
  variant = 'default',
  onClick,
  ariaLabel,
  testId,
}: InfoCardProps) {
  const variantClass = variant === 'default' ? '' : ` info-card--${variant}`
  const clickableClass = onClick ? ' info-card--clickable' : ''
  const className = `info-card${variantClass}${clickableClass}`
  const resolvedAriaLabel = deriveAriaLabel(title, ariaLabel)

  const inner = (
    <>
      <div className="info-card-header">
        <strong className="info-card-title">{title}</strong>
        {headerExtra ? <div className="info-card-header-extra">{headerExtra}</div> : null}
      </div>
      {subtitle ? <div className="info-card-subtitle">{subtitle}</div> : null}
      {children ? <div className="info-card-body">{children}</div> : null}
      {actions ? <div className="info-card-actions">{actions}</div> : null}
    </>
  )

  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        onClick={onClick}
        aria-label={resolvedAriaLabel}
        data-testid={testId}
      >
        {inner}
      </button>
    )
  }

  return (
    <article
      className={className}
      aria-label={resolvedAriaLabel}
      data-testid={testId}
    >
      {inner}
    </article>
  )
}
