import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  EmptyState,
  TableSkeleton,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { getErrorMessage, isForbiddenError } from '../../../shared/lib'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as schedulerApi from '../api'
import { executionTimestamp, formatSchedulerDuration } from '../presenters'
import type { ScheduledJobExecutionResponse } from '../types'
import { SchedulerExecutionDetail } from './SchedulerExecutionDetail'

const EXECUTION_API_LIMIT = 100

// ── Component ──────────────────────────────────────────────────────────────

export function SchedulerExecutionsTab() {
  const {
    data: jobsData,
    isLoading: loading,
    isFetching,
    error: listError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.scheduler.list(),
    queryFn: schedulerApi.listJobs,
  })
  const { t } = useTranslation()

  const jobs = jobsData ?? []

  const PAGE_SIZE = 20
  const [page, setPage] = useState(1)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [executions, setExecutions] = useState<ScheduledJobExecutionResponse[]>([])
  const [selectedExecution, setSelectedExecution] = useState<ScheduledJobExecutionResponse | null>(null)
  const [loadingExec, setLoadingExec] = useState(false)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)
  const loadFailure = listError ? getErrorMessage(listError) : null
  const unavailableState = loadFailure != null && jobs.length === 0
  const hasRevalidationError = loadFailure != null && jobs.length > 0
  const statusText = (status: string) => t(`common.statuses.${status}`, { defaultValue: t('common.statuses.WARN') })
  const statusTone = (status: string) => status === 'FAILED'
    ? 'fail'
    : status === 'RUNNING'
      ? 'warn'
      : 'pass'
  const executionOutcome = (status: string) => {
    switch (status) {
      case 'SUCCESS': return t('scheduler.executionOutcomes.success')
      case 'FAILED': return t('scheduler.executionOutcomes.failed')
      case 'RUNNING': return t('scheduler.executionOutcomes.running')
      case 'SKIPPED': return t('scheduler.executionOutcomes.skipped')
      default: return t('scheduler.executionOutcomes.review')
    }
  }

  async function loadExecutions(jobId: string) {
    setLoadingExec(true)
    setExecutionError(null)
    setExecutions([])
    setSelectedExecution(null)

    try {
      const history = await schedulerApi.getExecutions(jobId)
      setExecutions(history)
      setSelectedExecution(history[0] ?? null)
    } catch (e) {
      setExecutionError(getErrorMessage(e))
    } finally {
      setLoadingExec(false)
    }
  }

  function handleJobSelect(jobId: string) {
    setSelectedJobId(jobId)
    setPage(1)
    if (jobId) {
      void loadExecutions(jobId)
    } else {
      setExecutions([])
      setSelectedExecution(null)
      setExecutionError(null)
    }
  }

  const selectedJob = jobs.find((job) => job.id === selectedJobId) ?? null

  useEffect(() => {
    if (!selectedExecution || typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 1024px)').matches) return

    detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [selectedExecution])

  const executionColumns = [
    {
      key: 'status',
      header: t('common.status'),
      width: '14%',
      responsivePriority: 1,
      render: (execution: ScheduledJobExecutionResponse) => (
        <span className={`scheduler-state scheduler-state--${statusTone(execution.status)}`}>
          <span aria-hidden="true" />{statusText(execution.status)}
        </span>
      ),
      exportAccessor: (execution: ScheduledJobExecutionResponse) => execution.status,
    },
    {
      key: 'dryRun',
      header: '',
      width: '10%',
      responsivePriority: 3,
      render: (execution: ScheduledJobExecutionResponse) => (
        execution.dryRun ? <span className="execution-kind">{t('scheduler.dryRun')}</span> : null
      ),
      exportAccessor: (execution: ScheduledJobExecutionResponse) => execution.dryRun,
    },
    {
      key: 'duration',
      header: t('scheduler.duration'),
      width: '14%',
      responsivePriority: 2,
      render: (execution: ScheduledJobExecutionResponse) => formatSchedulerDuration(execution.durationMs),
      exportAccessor: (execution: ScheduledJobExecutionResponse) => execution.durationMs,
    },
    {
      key: 'startedAt',
      header: t('scheduler.startedAt'),
      width: '22%',
      responsivePriority: 1,
      render: (execution: ScheduledJobExecutionResponse) => formatDateTime(executionTimestamp(execution)),
      exportAccessor: (execution: ScheduledJobExecutionResponse) => executionTimestamp(execution),
    },
    {
      key: 'result',
      header: t('scheduler.result'),
      width: '40%',
      responsivePriority: 2,
      render: (execution: ScheduledJobExecutionResponse) => executionOutcome(execution.status),
      exportAccessor: (execution: ScheduledJobExecutionResponse) => execution.result ?? null,
    },
  ]

  if (isForbiddenError(listError) && jobs.length === 0) {
    return <EmptyState forbidden forbiddenContext={t('common.emptyState.forbiddenContext.scheduler')} />
  }

  if (unavailableState) {
    return (
      <WorkspaceUnavailable
        title={t('scheduler.executionWorkspaceUnavailableTitle')}
        description={t('scheduler.executionWorkspaceUnavailableDescription')}
        retryLabel={t('scheduler.retry')}
        retryingLabel={t('scheduler.retrying')}
        onRetry={refetch}
        isRetrying={isFetching}
        secondaryAction={{ label: t('scheduler.openHealth'), to: '/health' }}
        guide={{
          title: t('scheduler.recoveryGuideTitle'),
          steps: [
            t('scheduler.recoveryGuide.checkAccount'),
            t('scheduler.recoveryGuide.checkStatus'),
            t('scheduler.recoveryGuide.retry'),
          ],
          technicalLabel: t('scheduler.technicalError'),
          technicalDetail: loadFailure,
        }}
      />
    )
  }

  if (loading) return <TableSkeleton />

  if (jobs.length === 0) {
    return <EmptyState message={t('scheduler.empty')} description={t('scheduler.emptyDescription')} />
  }

  return (
    <>
      {hasRevalidationError && (
        <div className="scheduler-revalidation" role="status">
          <div>
            <strong>{t('scheduler.revalidationTitle')}</strong>
            <span>{t('scheduler.revalidationDescription')}</span>
          </div>
          <button className="btn btn-sm btn-secondary" type="button" onClick={() => void refetch()} disabled={isFetching}>
            {isFetching ? t('scheduler.retrying') : t('common.retry')}
          </button>
        </div>
      )}
      <div className="scheduler-execution-picker">
        <div className="form-group">
          <label htmlFor="executions-job-select">{t('scheduler.selectJobForHistory')}</label>
          <select
            id="executions-job-select"
            value={selectedJobId ?? ''}
            onChange={(event) => handleJobSelect(event.target.value)}
            disabled={loading || jobs.length === 0}
          >
            <option value="">{t('scheduler.selectJobPlaceholder')}</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>{job.name}</option>
            ))}
          </select>
        </div>
      </div>

      {!selectedJobId && (
        <EmptyState message={t('scheduler.selectJobForExecutions')} />
      )}

      {selectedJobId && selectedJob && (
        <div className={`split-layout ${selectedExecution ? '' : 'split-layout--collapsed'}`}>
          <div className="split-left">
            <section className="scheduler-execution-list">
              <div className="detail-section-header">
                <h2 className="section-title" style={{ marginBottom: 0 }}>{selectedJob.name}</h2>
                <span className={`scheduler-state scheduler-state--${selectedJob.enabled ? 'pass' : 'muted'}`}>
                  <span aria-hidden="true" />
                  {selectedJob.enabled ? t('scheduler.jobState.enabled') : t('scheduler.jobState.paused')}
                </span>
              </div>

              {executionError && (
                <>
                  <p className="scheduler-execution-list__connection-note" role="status">
                    {executions.length > 0
                      ? t('scheduler.executionSnapshotWarningPlain')
                      : t('scheduler.executionUnavailablePlain')}
                  </p>
                  <details className="scheduler-technical-details scheduler-execution-list__technical-error">
                    <summary>{t('scheduler.executionConnectionDetail')}</summary>
                    <p>{executionError}</p>
                  </details>
                </>
              )}

              {loadingExec ? (
                <TableSkeleton />
              ) : executions.length === 0 ? (
                <EmptyState message={t('scheduler.noExecutions')} />
              ) : (
                <>
                  {executions.length >= EXECUTION_API_LIMIT && (
                    <div className="alert alert-warning" style={{ marginBottom: 'var(--space-2)' }}>
                      {t('common.limitWarning', { limit: EXECUTION_API_LIMIT })}
                    </div>
                  )}
                  <div className="detail-note" style={{ marginBottom: 'var(--space-2)' }}>
                    {t('common.showingCount', { shown: executions.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE).length, total: executions.length })}
                  </div>
                  <DataTable
                    columns={executionColumns}
                    data={executions.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)}
                    keyFn={(execution) => execution.id}
                    onRowClick={setSelectedExecution}
                    selectedKey={selectedExecution?.id ?? null}
                    page={page}
                    pageSize={PAGE_SIZE}
                    totalCount={executions.length}
                    onPageChange={setPage}
                    tableId="scheduler-executions"
                    urlStateKey="scheduler-executions"
                    exportable={{ filename: 'scheduler-executions' }}
                  />
                </>
              )}
            </section>
          </div>

          {selectedExecution && (
          <div className="split-right" ref={detailRef} tabIndex={-1}>
              <SchedulerExecutionDetail execution={selectedExecution} onClose={() => setSelectedExecution(null)} />
          </div>
          )}
        </div>
      )}
    </>
  )
}
