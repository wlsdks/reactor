import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from '../../../shared/ui'

export type BulkAction = 'approve' | 'reject'

interface RagCandidatesBulkBarProps {
  selectedCount: number
  bulkBusy: boolean
  onRequestBulk: (action: BulkAction) => void
  onClear: () => void
}

export function RagCandidatesBulkBar({
  selectedCount,
  bulkBusy,
  onRequestBulk,
  onClear,
}: RagCandidatesBulkBarProps) {
  const { t } = useTranslation()

  if (selectedCount === 0) return null

  return (
    <div
      className="rag-bulk-bar"
      role="region"
      aria-label={t('ragCachePage.candidates.bulkBarLabel')}
      aria-live="polite"
    >
      <span className="rag-bulk-bar__count">
        {t('ragCachePage.candidates.bulkSelected', { count: selectedCount })}
      </span>
      <div className="rag-bulk-bar__actions">
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => onRequestBulk('approve')}
          disabled={bulkBusy}
        >
          {bulkBusy
            ? <LoadingSpinner size="sm" />
            : t('ragCachePage.candidates.bulkApprove')}
        </button>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => onRequestBulk('reject')}
          disabled={bulkBusy}
        >
          {t('ragCachePage.candidates.bulkReject')}
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onClear}
          disabled={bulkBusy}
        >
          {t('ragCachePage.candidates.bulkClear')}
        </button>
      </div>
    </div>
  )
}
