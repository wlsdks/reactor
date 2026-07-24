import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

const TRUNCATE_LIMIT = 32

export interface BreadcrumbItem {
  /** Display text for the breadcrumb segment. */
  label: string
  /**
   * Optional react-router target. When omitted the segment is rendered as the
   * current page (`aria-current="page"`).
   */
  href?: string
  /** Optional flag — render the label with monospace styling for ID slugs. */
  mono?: boolean
}

export interface BreadcrumbProps {
  items: BreadcrumbItem[]
  /** Visual separator between segments. Defaults to `/`. */
  separator?: ReactNode
  className?: string
  /** Accessible name for the nav landmark. Defaults to `"breadcrumb"`. */
  ariaLabel?: string
}

function shouldTruncate(label: string): boolean {
  return label.length > TRUNCATE_LIMIT
}

/**
 * Reusable breadcrumb trail. Last item always renders as the current page
 * (no link, `aria-current="page"`); earlier items render as `<Link>` when an
 * `href` is provided. Long labels (>32 chars) get a `title` tooltip and are
 * CSS-truncated by `.breadcrumb__label--truncate`.
 */
export function Breadcrumb({
  items,
  separator = '/',
  className,
  ariaLabel = 'breadcrumb',
}: BreadcrumbProps) {
  if (items.length === 0) return null

  const lastIndex = items.length - 1

  return (
    <nav aria-label={ariaLabel} className={['breadcrumb', className].filter(Boolean).join(' ')}>
      <ol className="breadcrumb__list">
        {items.map((item, index) => {
          const isCurrent = index === lastIndex || item.href == null
          const truncate = shouldTruncate(item.label)
          const labelClassName = [
            'breadcrumb__label',
            isCurrent ? 'breadcrumb__label--current' : 'breadcrumb__label--ancestor',
            truncate ? 'breadcrumb__label--truncate' : null,
            item.mono ? 'breadcrumb__label--mono' : null,
          ]
            .filter(Boolean)
            .join(' ')

          return (
            <li key={`${index}-${item.label}`} className="breadcrumb__item">
              {isCurrent ? (
                <span
                  className={labelClassName}
                  aria-current="page"
                  title={truncate ? item.label : undefined}
                >
                  {item.label}
                </span>
              ) : (
                <Link
                  to={item.href!}
                  className={`breadcrumb__link ${labelClassName}`}
                  title={truncate ? item.label : undefined}
                >
                  {item.label}
                </Link>
              )}
              {index < lastIndex && (
                <span className="breadcrumb__separator" aria-hidden="true">
                  {separator}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
