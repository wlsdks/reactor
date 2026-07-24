import { useTranslation } from 'react-i18next'
import { formatPercent } from '../../../shared/lib/formatters'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import type { CacheStats, VectorStoreStats, RagPolicyState } from '../types'
import './rag-cache-insight.css'

export interface RagCacheInsightBarProps {
  cacheStats: CacheStats | null
  vectorStoreStats: VectorStoreStats | null
  ragPolicy: RagPolicyState | null
  pendingCandidatesCount: number
  cacheError?: boolean
  onJumpToCandidates: () => void
  onRefresh: () => void
}

type Status = 'ok' | 'warn' | 'err' | 'unknown'

function resolveStatus(
  cacheStats: CacheStats | null,
  ragPolicy: RagPolicyState | null,
  pendingCandidatesCount: number,
  cacheError: boolean,
): Status {
  if (!cacheStats && cacheError) return 'err'
  if (!cacheStats || !ragPolicy) return 'unknown'
  const ragEnabled = ragPolicy.effective.enabled
  const cacheEnabled = cacheStats.enabled
  if (!cacheEnabled) return 'warn'
  if (!ragEnabled) return 'warn'
  if (pendingCandidatesCount >= 10) return 'warn'
  return 'ok'
}

// The shared formatPercent returns "-" for null/undefined; this view-specific
// wrapper preserves the em-dash placeholder used across the insight bar.
function formatInsightPercent(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '—'
  return formatPercent(value)
}

export function RagCacheInsightBar({
  cacheStats,
  vectorStoreStats,
  ragPolicy,
  pendingCandidatesCount,
  cacheError = false,
  onJumpToCandidates,
  onRefresh,
}: RagCacheInsightBarProps) {
  const { t } = useTranslation()
  const status = resolveStatus(cacheStats, ragPolicy, pendingCandidatesCount, cacheError)

  const statusLabel =
    status === 'ok'
      ? t('ragCachePage.insightBar.statusOk')
      : status === 'warn'
        ? t('ragCachePage.insightBar.statusWarning')
        : status === 'err'
          ? t('ragCachePage.insightBar.statusError')
          : t('ragCachePage.insightBar.statusUnknown')

  const hasPending = pendingCandidatesCount > 0

  return (
    <section className="rag-insight-bar" aria-label={t('ragCachePage.insightBar.summaryLabel')}>
      <div className="rag-insight-bar__summary" role="status" aria-live="polite">
        <div className="rag-insight-status">
          <span
            className={`rag-insight-status__dot rag-insight-status__dot--${status}`}
            aria-hidden="true"
          />
          <span>{statusLabel}</span>
        </div>
      </div>

      <dl className="rag-insight-items">
        <div className="rag-insight-item">
          <dt className="rag-insight-item__label">
            {t('ragCachePage.insightBar.cacheLabel')}
          </dt>
          <dd className="rag-insight-item__value">
            {cacheStats ? formatInsightPercent(cacheStats.hitRate) : '—'}
          </dd>
        </div>

        <div className="rag-insight-item">
          <dt className="rag-insight-item__label">
            {t('ragCachePage.insightBar.ragDocsLabel')}
          </dt>
          <dd className="rag-insight-item__value">
            {vectorStoreStats ? formatLocaleNumber(vectorStoreStats.documentCount) : '—'}
          </dd>
        </div>

        <div className="rag-insight-item">
          <dt className="rag-insight-item__label">
            {t('ragCachePage.insightBar.pendingLabel')}
          </dt>
          <dd
            className={`rag-insight-item__value${hasPending ? ' rag-insight-item__value--warn' : ''}`}
          >
            {formatLocaleNumber(pendingCandidatesCount)}
          </dd>
        </div>
      </dl>

      <div className="rag-insight-bar__actions">
        {hasPending ? (
          <button
            type="button"
            className="btn btn-secondary btn-sm rag-insight-cta"
            onClick={onJumpToCandidates}
            title={t('ragCachePage.insightBar.reviewQueueTitle')}
            aria-label={t('ragCachePage.insightBar.reviewQueueAriaLabel', {
              count: pendingCandidatesCount,
            })}
          >
            {t('ragCachePage.insightBar.reviewQueueLabel', { count: pendingCandidatesCount })}
          </button>
        ) : (
          <span className="rag-insight-empty">
            {t('ragCachePage.insightBar.noPending')}
          </span>
        )}
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRefresh}>
          {t('common.refresh')}
        </button>
      </div>
    </section>
  )
}
