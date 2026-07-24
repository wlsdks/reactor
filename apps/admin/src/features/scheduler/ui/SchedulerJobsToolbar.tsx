import { useTranslation } from 'react-i18next'
import {
  RefreshButton,
  SavedViewsControl,
} from '../../../shared/ui'
import { formatDateTimeCompact } from '../../../shared/lib'
import { applyScopedParams, extractScopedParams } from '../../../shared/lib/useUrlState'

interface SchedulerJobsToolbarProps {
  isFetching: boolean
  lastLoadedAt: number | null
  hasRevalidationError: boolean
  jobsLength: number
  searchParams: URLSearchParams
  onSearchParamsChange: (params: URLSearchParams) => void
  onRefresh: () => void | Promise<void>
  onCreate: () => void
}

export function SchedulerJobsToolbar({
  isFetching,
  lastLoadedAt,
  hasRevalidationError,
  jobsLength,
  searchParams,
  onSearchParamsChange,
  onRefresh,
  onCreate,
}: SchedulerJobsToolbarProps) {
  const { t } = useTranslation()

  return (
    <>
      <div className="scheduler-workspace__toolbar">
        <p className="scheduler-workspace__sync">
          {lastLoadedAt
            ? t('scheduler.lastSync', { time: formatDateTimeCompact(lastLoadedAt) })
            : t('scheduler.lastSyncUnknown')}
        </p>
        <div className="row-actions">
            <SavedViewsControl
              scope="scheduler"
              currentParams={extractScopedParams(searchParams, 'scheduler')}
              onApply={(params) => onSearchParamsChange(applyScopedParams(searchParams, 'scheduler', params))}
            />
            <RefreshButton
              onRefresh={() => { void onRefresh() }}
              isFetching={isFetching}
            />
            <button className="btn btn-primary" onClick={onCreate}>
              {t('scheduler.create')}
            </button>
        </div>
      </div>

      {hasRevalidationError && jobsLength > 0 && (
        <div className="scheduler-revalidation" role="status">
          <div>
            <strong>{t('scheduler.revalidationTitle')}</strong>
            <span>{t('scheduler.revalidationDescription')}</span>
          </div>
          <button
            className="btn btn-sm btn-secondary"
            onClick={() => void onRefresh()}
            disabled={isFetching}
          >
            {isFetching ? t('scheduler.retrying') : t('common.retry')}
          </button>
        </div>
      )}
    </>
  )
}
