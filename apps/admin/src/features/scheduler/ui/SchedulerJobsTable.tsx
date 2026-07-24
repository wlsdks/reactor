import { useTranslation } from 'react-i18next'
import {
  DataTable,
  EmptyState,
  SkeletonTable,
} from '../../../shared/ui'
import type { SchedulerQuickFilter } from '../schedulerOps'
import type { ScheduledJobResponse } from '../types'

interface SchedulerJobsTableProps {
  jobs: ScheduledJobResponse[]
  visibleJobs: ScheduledJobResponse[]
  selected: ScheduledJobResponse | null
  loading: boolean
  quickFilter: SchedulerQuickFilter
  quickFilters: readonly SchedulerQuickFilter[]
  onQuickFilterChange: (filter: SchedulerQuickFilter) => void
  onRowClick: (job: ScheduledJobResponse) => void
}

export function SchedulerJobsTable({
  jobs,
  visibleJobs,
  selected,
  loading,
  quickFilter,
  quickFilters,
  onQuickFilterChange,
  onRowClick,
}: SchedulerJobsTableProps) {
  const { t } = useTranslation()

  function scheduleLabel(cronExpression: string): string {
    const parts = cronExpression.trim().split(/\s+/)
    if (parts.length !== 5) return t('scheduler.schedule.custom')
    const [minute, hour, dayOfMonth, month, dayOfWeek] = parts

    if (minute === '0' && hour.startsWith('*/') && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return t('scheduler.schedule.everyHours', { count: Number(hour.slice(2)) })
    }
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
      return t('scheduler.schedule.dailyAt', { time: `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}` })
    }
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && dayOfMonth === '*' && month === '*' && dayOfWeek === '1-5') {
      return t('scheduler.schedule.weekdaysAt', { time: `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}` })
    }
    if (/^\d+$/.test(minute) && /^\d+$/.test(hour) && dayOfMonth === '*' && month === '*' && /^\d$/.test(dayOfWeek)) {
      return t('scheduler.schedule.weeklyAt', {
        weekday: t(`scheduler.weekdays.${dayOfWeek}`),
        time: `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`,
      })
    }
    return t('scheduler.schedule.custom')
  }

  function jobState(job: ScheduledJobResponse): string {
    return job.enabled ? t('scheduler.jobState.enabled') : t('scheduler.jobState.paused')
  }

  function lastRunState(job: ScheduledJobResponse): string {
    return job.lastStatus
      ? t(`common.statuses.${job.lastStatus}`, { defaultValue: t('common.statuses.WARN') })
      : t('scheduler.noExecutionYet')
  }

  const jobColumns = [
    {
      key: 'name',
      header: t('common.name'),
      width: '26%',
      responsivePriority: 1,
      render: (job: ScheduledJobResponse) => job.name,
      exportAccessor: (job: ScheduledJobResponse) => job.name,
    },
    {
      key: 'type',
      header: t('scheduler.jobType'),
      width: '16%',
      responsivePriority: 3,
      render: (job: ScheduledJobResponse) => t(`scheduler.jobTypes.${job.jobType}`),
      exportAccessor: (job: ScheduledJobResponse) => job.jobType,
    },
    {
      key: 'cron',
      header: t('scheduler.scheduleLabel'),
      width: '24%',
      responsivePriority: 1,
      render: (job: ScheduledJobResponse) => scheduleLabel(job.cronExpression),
      exportAccessor: (job: ScheduledJobResponse) => job.cronExpression,
    },
    {
      key: 'enabled',
      header: t('common.status'),
      width: '16%',
      responsivePriority: 1,
      render: (job: ScheduledJobResponse) => (
        <span className={`scheduler-state scheduler-state--${job.enabled ? 'pass' : 'muted'}`}>
          <span aria-hidden="true" />
          {jobState(job)}
        </span>
      ),
      exportAccessor: (job: ScheduledJobResponse) => job.enabled ? 'ENABLED' : 'DISABLED',
    },
    {
      key: 'lastStatus',
      header: t('scheduler.lastRun'),
      width: '18%',
      responsivePriority: 3,
      render: (job: ScheduledJobResponse) => (
        <span className={`scheduler-state scheduler-state--${job.lastStatus === 'FAILED' ? 'fail' : job.lastStatus === 'RUNNING' ? 'warn' : job.lastStatus ? 'pass' : 'muted'}`}>
          <span aria-hidden="true" />
          {lastRunState(job)}
        </span>
      ),
      exportAccessor: (job: ScheduledJobResponse) => job.lastStatus ?? null,
    },
  ]

  return (
    <section className={`scheduler-jobs-table${jobs.length === 0 ? ' scheduler-jobs-table--empty' : ''}`} aria-labelledby="scheduler-jobs-title">
      {jobs.length > 0 && (
        <>
          <div className="section-toolbar">
            <h2 id="scheduler-jobs-title" className="section-title">{t('scheduler.jobsTitle')}</h2>
            <span className="page-subtitle">{t('scheduler.filterDescription')}</span>
          </div>
          <div className="detail-actions" style={{ marginBottom: 'var(--space-3)' }}>
            {quickFilters.map((mode) => (
              <button
                key={mode}
                className={`btn ${quickFilter === mode ? 'btn-primary' : 'btn-secondary'} btn-sm`}
                onClick={() => onQuickFilterChange(mode)}
              >
                {t(`scheduler.quickFilters.${mode}`)}
              </button>
            ))}
          </div>
          <p className="detail-note" style={{ marginTop: 0, marginBottom: 'var(--space-3)' }}>
            {t('scheduler.showingRows', { shown: visibleJobs.length, total: jobs.length })}
          </p>
        </>
      )}

      {loading && jobs.length === 0 ? (
        // Job table keeps five identifying columns. All mutations live in the selected detail.
        // Align the skeleton to match the real grid so rows don't jump.
        <SkeletonTable rows={6} columns={5} />
      ) : jobs.length === 0 ? (
        <EmptyState
          message={t('scheduler.empty')}
          description={t('scheduler.emptyDescription')}
        />
      ) : visibleJobs.length === 0 ? (
        <EmptyState
          message={t('scheduler.filterEmpty')}
          description={t('scheduler.filterEmptyDescription')}
        />
      ) : (
        <DataTable
          columns={jobColumns}
          data={visibleJobs}
          keyFn={(job) => job.id}
          onRowClick={onRowClick}
          selectedKey={selected?.id ?? null}
          tableId="scheduler-jobs"
          urlStateKey="scheduler"
          exportable={{ filename: 'scheduler-jobs' }}
        />
      )}
    </section>
  )
}
