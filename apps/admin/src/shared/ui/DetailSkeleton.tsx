import { useTranslation } from 'react-i18next'

export function DetailSkeleton() {
  const { t } = useTranslation()
  return (
    <div className="skeleton-detail" aria-busy="true" aria-label={t('common.loading')}>
      <div className="skeleton-line skeleton-detail-title" />
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="skeleton-detail-section">
          <div className="skeleton-line skeleton-detail-label" />
          <div className="skeleton-line skeleton-detail-value" />
        </div>
      ))}
    </div>
  )
}
