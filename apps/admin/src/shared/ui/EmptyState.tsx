import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

interface EmptyStateProps {
  /**
   * Primary message. When `filtered` is true and no `message` is provided,
   * falls back to `common.emptyState.filteredTitle`. When `forbidden` is true
   * and no `message` is provided, falls back to
   * `common.emptyState.forbiddenTitle`.
  */
  message?: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  /**
   * Optional sample preview rendered below the action button on a dim panel
   * to help admins recognise the kind of data this page expects.
   */
  example?: ReactNode
  /** Optional URL for a small "도움말 보기 →" text link rendered below the example. */
  helpHref?: string
  /** Optional override for the help link label. Falls back to common.emptyState.helpLink. */
  helpLabel?: string
  /** When true, renders the filter-aware variant and clear-filter action. */
  filtered?: boolean
  /** Plain-language summary of the active filters. Only rendered when filtered. */
  filterSummary?: string
  /**
   * When provided alongside `filtered`, surfaces a "필터 해제" ghost button
   * as the primary action.
   */
  onClearFilters?: () => void
  /**
   * When true, renders the permission-denied (HTTP 403) copy and a
   * "관리자 문의" action when `contactHref` is supplied.
   *
   * Use for query-time 403s where the entire page or a major panel cannot
   * be loaded by the current role. For action-time 403s (e.g. mutation
   * failures), prefer `showApiErrorToast` which already exposes the same
   * recovery affordance inline.
   */
  forbidden?: boolean
  /**
   * Optional description for the forbidden variant. When omitted, falls back
   * to `common.emptyState.forbiddenHint` ("이 영역은 ADMIN 또는
   * ADMIN_DEVELOPER 역할이 필요합니다"). Use this to spell out the specific
   * resource or role context (e.g. "이 페이지는 ADMIN 권한이 필요합니다").
   */
  forbiddenContext?: string
  /**
   * Contact link surfaced on the forbidden variant. Defaults to
   * `mailto:admin@example.com` when `forbidden` is true and no override is
   * given, so admins always have a path forward instead of a dead end.
   */
  contactHref?: string
}

const DEFAULT_CONTACT_HREF = 'mailto:admin@example.com'

export function EmptyState({
  message,
  description,
  actionLabel,
  onAction,
  example,
  helpHref,
  helpLabel,
  filtered = false,
  filterSummary,
  onClearFilters,
  forbidden = false,
  forbiddenContext,
  contactHref,
}: EmptyStateProps) {
  const { t } = useTranslation()

  const displayMessage =
    message ??
    (forbidden
      ? t('common.emptyState.forbiddenTitle')
      : filtered
        ? t('common.emptyState.filteredTitle')
        : '')
  const displayDescription =
    description ??
    (forbidden
      ? (forbiddenContext ?? t('common.emptyState.forbiddenHint'))
      : filtered
        ? t('common.emptyState.filteredHint')
        : undefined)

  // Forbidden takes precedence over filtered: a permission boundary is a
  // stronger signal than an active filter, and the two states should not
  // visually mix (the filter chrome would suggest the user can recover by
  // clearing filters, which is misleading for 403).
  const variantClass = forbidden
    ? ' empty-state--forbidden'
    : filtered
      ? ' empty-state--filtered'
      : ''
  const className = `empty-state${variantClass}`

  const resolvedContactHref = forbidden
    ? (contactHref ?? DEFAULT_CONTACT_HREF)
    : undefined

  return (
    <div className={className}>
      {filtered && !forbidden && (
        <span className="empty-state-context">{t('common.emptyState.filteredContext')}</span>
      )}
      {forbidden && (
        <span className="empty-state-context empty-state-context--warning">
          {t('common.emptyState.forbiddenContextLabel')}
        </span>
      )}
      <p className="empty-state-title">{displayMessage}</p>
      {displayDescription && (
        <span className="empty-state-description">{displayDescription}</span>
      )}
      {filtered && filterSummary && !forbidden && (
        <p
          className="empty-state-filter-summary"
          aria-label={t('common.emptyState.filterSummary', { summary: filterSummary })}
        >
          {filterSummary}
        </p>
      )}
      {/* Action priority: explicit action > forbidden contact link > clear-filters */}
      {actionLabel && onAction && (
        <button className="btn btn-secondary btn-sm" onClick={onAction}>
          {actionLabel}
        </button>
      )}
      {forbidden && resolvedContactHref && !(actionLabel && onAction) && (
        <a
          className="btn btn-secondary btn-sm empty-state-contact"
          href={resolvedContactHref}
          target={resolvedContactHref.startsWith('mailto:') ? undefined : '_blank'}
          rel={
            resolvedContactHref.startsWith('mailto:')
              ? undefined
              : 'noopener noreferrer'
          }
        >
          {t('common.emptyState.contactAdmin')}
        </a>
      )}
      {filtered && onClearFilters && !forbidden && !(actionLabel && onAction) && (
        <button
          className="btn btn-ghost btn-sm empty-state-clear-filters"
          onClick={onClearFilters}
        >
          {t('common.emptyState.clearFilters')}
        </button>
      )}
      {example && (
        <div
          className="empty-state-example"
          aria-label={t('common.emptyState.exampleLabel')}
        >
          {example}
        </div>
      )}
      {helpHref && (
        <a
          className="empty-state-help"
          href={helpHref}
          target="_blank"
          rel="noopener noreferrer"
        >
          {helpLabel ?? t('common.emptyState.helpLink')}
        </a>
      )}
    </div>
  )
}
