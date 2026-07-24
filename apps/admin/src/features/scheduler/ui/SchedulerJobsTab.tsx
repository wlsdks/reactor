import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useUnsavedChanges, useEscapeKey, getErrorMessage, showApiErrorToast, isForbiddenError } from '../../../shared/lib'
import { useToastStore } from '../../../shared/store/toast.store'
import {
  ConfirmDialog,
  EmptyState,
  WorkspaceUnavailable,
  useAnnouncer,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as schedulerApi from '../api'
import {
  createEmptySchedulerJobForm,
  schedulerJobToForm,
  type SchedulerJobFormState,
  validateSchedulerJobForm,
} from '../schedulerForm'
import {
  filterSchedulerJobs,
  summarizeSchedulerOps,
  type SchedulerQuickFilter,
} from '../schedulerOps'
import type { ScheduledJobExecutionResponse, ScheduledJobResponse } from '../types'
import { SchedulerJobDetail } from './SchedulerJobDetail'
import { SchedulerJobFormModal } from './SchedulerJobFormModal'
import { SchedulerJobsTable } from './SchedulerJobsTable'
import { SchedulerJobsToolbar } from './SchedulerJobsToolbar'
import { SchedulerOpsPanel } from './SchedulerOpsPanel'

// ── Helpers ────────────────────────────────────────────────────────────────

const schedulerQuickFilters: SchedulerQuickFilter[] = ['all', 'attention', 'failed', 'neverRun', 'stuckRunning', 'noRetry']

// ── Component ──────────────────────────────────────────────────────────────

export function SchedulerJobsTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()
  const [searchParams, setSearchParams] = useSearchParams()

  // ── Server state ─────────────────────────────────────────────────────────
  const {
    data: jobs = [],
    isLoading: loading,
    isFetching,
    error: listError,
    dataUpdatedAt,
    refetch,
  } = useQuery({
    queryKey: queryKeys.scheduler.list(),
    queryFn: schedulerApi.listJobs,
  })

  // ── Local UI state ────────────────────────────────────────────────────────
  const [selected, setSelected] = useState<ScheduledJobResponse | null>(null)
  const [executions, setExecutions] = useState<ScheduledJobExecutionResponse[]>([])
  const [selectedExecution, setSelectedExecution] = useState<ScheduledJobExecutionResponse | null>(null)
  const [loadingExec, setLoadingExec] = useState(false)
  const [executionError, setExecutionError] = useState<string | null>(null)
  const [quickFilter, setQuickFilter] = useState<SchedulerQuickFilter>('all')

  const [showForm, setShowForm] = useState(false)
  const [editingJob, setEditingJob] = useState<ScheduledJobResponse | null>(null)
  const [form, setForm] = useState<SchedulerJobFormState>(createEmptySchedulerJobForm())
  const [initialForm, setInitialForm] = useState<SchedulerJobFormState>(createEmptySchedulerJobForm())
  const [formError, setFormError] = useState<string | null>(null)
  const [loadingEditJobId, setLoadingEditJobId] = useState<string | null>(null)
  const [actionResult, setActionResult] = useState<string | null>(null)
  const [running, setRunning] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ScheduledJobResponse | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

  const isDirty = showForm && JSON.stringify(form) !== JSON.stringify(initialForm)
  const blocker = useUnsavedChanges(isDirty)

  // ── Derived state ─────────────────────────────────────────────────────────
  const loadFailure = listError ? getErrorMessage(listError) : null
  const lastLoadedAt = dataUpdatedAt > 0 ? dataUpdatedAt : null
  const opsSummary = summarizeSchedulerOps(jobs, loadFailure)
  const unavailableState = loadFailure != null && jobs.length === 0
  const hasRevalidationError = loadFailure != null && jobs.length > 0

  const visibleJobs = filterSchedulerJobs(jobs, opsSummary.attentionItems, quickFilter)
  const selectedAttention = selected
    ? opsSummary.attentionItems.find((item) => item.job.id === selected.id) ?? null
    : null

  // ── Mutations ─────────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async (formState: SchedulerJobFormState) => {
      const validation = validateSchedulerJobForm(formState)
      if ('errorId' in validation) throw new Error(t(`scheduler.validation.${validation.errorId}`))
      if (editingJob) {
        return schedulerApi.updateJob(editingJob.id, validation.request)
      } else {
        return schedulerApi.createJob(validation.request)
      }
    },
    onSuccess: () => {
      useToastStore.getState().addToast({ type: 'success', message: t(editingJob ? 'common.toast.updated' : 'common.toast.created') })
      announce(t(editingJob ? 'common.a11y.updated' : 'common.a11y.created'))
      setShowForm(false)
      setEditingJob(null)
      setForm(createEmptySchedulerJobForm())
      void queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.all() })
    },
    onError: (err: Error) => {
      setFormError(err.message)
      announce(err.message, { priority: 'assertive' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (job: ScheduledJobResponse) => schedulerApi.deleteJob(job.id),
    onSuccess: (_, deletedJob) => {
      if (selected?.id === deletedJob.id) {
        setSelected(null)
        setExecutions([])
        setSelectedExecution(null)
        setExecutionError(null)
      }
      setDeleteTarget(null)
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.deleted') })
      announce(t('common.a11y.deleted'))
      void queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.all() })
      // Doctor summary aggregates scheduler health/attention items; refresh it
      // so the global health banner clears any stale alerts that referenced
      // the just-deleted job.
      void queryClient.invalidateQueries({ queryKey: queryKeys.doctor.summary() })
    },
    onError: (err, job) => {
      const resolved = showApiErrorToast(err, {
        onRetry: () => deleteMutation.mutate(job),
      })
      announce(resolved.message, { priority: 'assertive' })
      setDeleteTarget(null)
    },
  })

  // ── Effects ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (selected && !visibleJobs.some((job) => job.id === selected.id)) {
      setSelected(null)
      setExecutions([])
      setSelectedExecution(null)
      setExecutionError(null)
    }
  }, [selected, visibleJobs])

  useEscapeKey(!!selected && !showForm && !deleteTarget, () => {
    setSelected(null)
    setExecutions([])
    setSelectedExecution(null)
    setExecutionError(null)
  })

  useEffect(() => {
    if (!selected || typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 1024px)').matches) return

    detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [selected])

  // ── Data actions ──────────────────────────────────────────────────────────

  async function loadExecutions(jobId: string, preserveSnapshot = false) {
    setLoadingExec(true)
    setExecutionError(null)
    if (!preserveSnapshot) {
      setExecutions([])
      setSelectedExecution(null)
    }
    try {
      const history = await schedulerApi.getExecutions(jobId)
      setExecutions(history)
      setSelectedExecution((current) => history.find((item) => item.id === current?.id) ?? history[0] ?? null)
    } catch (e) {
      setExecutionError(getErrorMessage(e))
    } finally {
      setLoadingExec(false)
    }
  }

  async function openDetail(job: ScheduledJobResponse) {
    setSelected(job)
    setActionResult(null)
    await loadExecutions(job.id)
  }

  function openCreate() {
    setEditingJob(null)
    const fresh = createEmptySchedulerJobForm()
    setForm(fresh)
    setInitialForm(fresh)
    setFormError(null)
    setShowForm(true)
  }

  async function openEdit(job: ScheduledJobResponse) {
    setLoadingEditJobId(job.id)
    setFormError(null)
    try {
      const detail = await schedulerApi.getJob(job.id)
      setEditingJob(detail)
      const loaded = schedulerJobToForm(detail)
      setForm(loaded)
      setInitialForm(loaded)
      setShowForm(true)
    } catch (e) {
      showApiErrorToast(e, { onRetry: () => { void openEdit(job) } })
    } finally {
      setLoadingEditJobId(null)
    }
  }

  async function handleTrigger(id: string) {
    setRunning(`trigger-${id}`)
    setActionResult(null)
    try {
      const result = await schedulerApi.triggerJob(id)
      setActionResult(result)
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      void queryClient.invalidateQueries({ queryKey: queryKeys.scheduler.all() })
      await loadExecutions(id, true)
    } catch (e) {
      const resolved = showApiErrorToast(e, { onRetry: () => { void handleTrigger(id) } })
      setActionResult(t('scheduler.actionError', { message: resolved.message }))
    } finally {
      setRunning(null)
    }
  }

  async function handleDryRun(id: string) {
    setRunning(`dryrun-${id}`)
    setActionResult(null)
    try {
      const result = await schedulerApi.dryRunJob(id)
      setActionResult(t('scheduler.dryRunResult', { result }))
      await loadExecutions(id, true)
    } catch (e) {
      setActionResult(t('scheduler.actionError', { message: getErrorMessage(e) }))
    } finally {
      setRunning(null)
    }
  }

  async function refreshList() {
    const result = await refetch()
    if (!result.error) {
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.refreshed') })
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  // 403 from the jobs query: "create job" would also be denied server-side,
  // so render a forbidden EmptyState instead of a header with a disabled
  // create button + "load failed" alert that imply the data is just missing.
  if (isForbiddenError(listError) && jobs.length === 0) {
    return (
      <>
        <EmptyState
          forbidden
          forbiddenContext={t('common.emptyState.forbiddenContext.scheduler')}
        />
      </>
    )
  }

  if (unavailableState) {
    return (
      <WorkspaceUnavailable
        title={t('scheduler.unavailableTitle')}
        description={t('scheduler.unavailableDescription')}
        retryLabel={t('scheduler.retry')}
        retryingLabel={t('scheduler.retrying')}
        onRetry={refreshList}
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

  return (
    <>
      <SchedulerJobsToolbar
        lastLoadedAt={lastLoadedAt}
        hasRevalidationError={hasRevalidationError}
        jobsLength={jobs.length}
        searchParams={searchParams}
        onSearchParamsChange={(params) => setSearchParams(params, { replace: true })}
        onRefresh={refreshList}
        isFetching={isFetching}
        onCreate={openCreate}
      />

      {jobs.length > 0 && (
        <SchedulerOpsPanel
          opsSummary={opsSummary}
          onOpenDetail={(job) => { void openDetail(job) }}
        />
      )}

      <div className={`split-layout ${selected ? '' : 'split-layout--collapsed'}`}>
        <div className="split-left">
          <SchedulerJobsTable
            jobs={jobs}
            visibleJobs={visibleJobs}
            selected={selected}
            loading={loading}
            quickFilter={quickFilter}
            quickFilters={schedulerQuickFilters}
            onQuickFilterChange={setQuickFilter}
            onRowClick={(job) => { void openDetail(job) }}
          />
        </div>

        {selected && (
        <div className="split-right" ref={detailRef} tabIndex={-1}>
            <SchedulerJobDetail
              selected={selected}
              selectedAttention={selectedAttention}
              executions={executions}
              selectedExecution={selectedExecution}
              loadingExec={loadingExec}
              executionError={executionError}
              actionResult={actionResult}
              running={running}
              loadingEdit={loadingEditJobId === selected.id}
              onClose={() => {
                setSelected(null)
                setExecutions([])
                setSelectedExecution(null)
                setExecutionError(null)
              }}
              onTrigger={(id) => { void handleTrigger(id) }}
              onDryRun={(id) => { void handleDryRun(id) }}
              onEdit={(job) => { void openEdit(job) }}
              onRequestDelete={setDeleteTarget}
              onSelectExecution={setSelectedExecution}
            />
        </div>
        )}
      </div>

      {showForm && (
        <SchedulerJobFormModal
          form={form}
          editingJob={editingJob}
          formError={formError}
          isSaving={saveMutation.isPending}
          onFormChange={setForm}
          onSave={() => saveMutation.mutate(form)}
          onClose={() => {
            setShowForm(false)
            setEditingJob(null)
            setForm(createEmptySchedulerJobForm())
          }}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={t('scheduler.deleteTitle')}
          message={t('scheduler.deleteConfirm', { name: deleteTarget.name })}
          onConfirm={() => deleteMutation.mutate(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
          danger
          confirmText={deleteTarget.name}
        />
      )}

      {blocker.state === 'blocked' && (
        <ConfirmDialog
          title={t('common.unsavedChanges')}
          message={t('common.unsavedChangesMessage')}
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
          danger
        />
      )}
    </>
  )
}
