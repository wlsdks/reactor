import { useTranslation } from 'react-i18next'

interface TableSkeletonProps {
  rows?: number
  columns?: number
}

export function TableSkeleton({ rows = 5, columns = 3 }: TableSkeletonProps) {
  const { t } = useTranslation()
  return (
    <div className="skeleton-table" aria-busy="true" aria-label={t('common.aria.loading')}>
      <div className="skeleton-table-header">
        {Array.from({ length: columns }, (_, i) => (
          <div key={i} className="skeleton-table-cell">
            <div className="skeleton-line" style={{ width: `${60 + (i * 17 % 30)}%` }} />
          </div>
        ))}
      </div>
      {Array.from({ length: rows }, (_, ri) => (
        <div key={ri} className="skeleton-table-row">
          {Array.from({ length: columns }, (_, ci) => (
            <div key={ci} className="skeleton-table-cell">
              <div className="skeleton-line" style={{ width: `${50 + ((ri * columns + ci) * 17 % 40)}%` }} />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}
