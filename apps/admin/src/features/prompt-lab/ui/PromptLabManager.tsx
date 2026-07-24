import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  PageHeader,
  RefreshButton,
  TableSkeleton,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { formatDateTime } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as promptLabApi from '../api'
import type { PromptExperiment, PromptExperimentStatus, PromptFeedbackAnalysis } from '../types'
import { AnalyzeFeedbackDialog } from './AnalyzeFeedbackDialog'
import { AutoOptimizeDialog } from './AutoOptimizeDialog'
import { CreateExperimentDialog } from './CreateExperimentDialog'
import { ExperimentDetail } from './ExperimentDetail'
import './prompt-lab.css'

function statusTone(status: PromptExperimentStatus): 'pass' | 'warn' | 'fail' | 'muted' {
  if (status === 'COMPLETED') return 'pass'
  if (status === 'FAILED') return 'fail'
  if (status === 'RUNNING') return 'warn'
  return 'muted'
}

function statusLabel(t: ReturnType<typeof useTranslation>['t'], status: PromptExperimentStatus): string {
  switch (status) {
    case 'PENDING': return t('promptLabPage.statuses.waiting')
    case 'RUNNING': return t('promptLabPage.statuses.running')
    case 'COMPLETED': return t('promptLabPage.statuses.completed')
    case 'FAILED': return t('promptLabPage.statuses.needsReview')
    case 'CANCELLED': return t('promptLabPage.statuses.stopped')
  }
}

export function PromptLabManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<PromptExperimentStatus | ''>('')
  const [operationError, setOperationError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [actioning, setActioning] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<PromptExperiment | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [showOptimizeDialog, setShowOptimizeDialog] = useState(false)
  const [showAnalyzeDialog, setShowAnalyzeDialog] = useState(false)
  const [autoResult, setAutoResult] = useState<{ jobId: string; templateId: string } | null>(null)
  const [analysis, setAnalysis] = useState<PromptFeedbackAnalysis | null>(null)
  const pageSize = 30

  const {
    data: experiments = [],
    isLoading,
    isFetching,
    error: listError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.promptLab.list(statusFilter || undefined),
    queryFn: () => promptLabApi.listExperiments(statusFilter || undefined),
  })

  const {
    data: selected = null,
    isLoading: loadingDetails,
    error: detailError,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: queryKeys.promptLab.detail(selectedId ?? ''),
    queryFn: () => promptLabApi.getExperiment(selectedId!),
    enabled: !!selectedId,
  })

  const { data: experimentStatus = null } = useQuery({
    queryKey: queryKeys.promptLab.status(selectedId ?? ''),
    queryFn: () => promptLabApi.getExperimentStatus(selectedId!).catch(() => null),
    enabled: !!selectedId,
  })

  const { data: trials = [] } = useQuery({
    queryKey: queryKeys.promptLab.trials(selectedId ?? ''),
    queryFn: () => promptLabApi.getExperimentTrials(selectedId!).catch(() => []),
    enabled: !!selectedId,
  })

  const { data: report = null } = useQuery({
    queryKey: queryKeys.promptLab.report(selectedId ?? ''),
    queryFn: () => promptLabApi.getExperimentReport(selectedId!).catch(() => null),
    enabled: !!selectedId,
  })

  const createMutation = useMutation({
    mutationFn: promptLabApi.createExperiment,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.all() })
      setShowCreate(false)
    },
    onError: (err: Error) => setOperationError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => promptLabApi.deleteExperiment(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.all() })
      if (selectedId === id) setSelectedId(null)
      setDeleteTarget(null)
    },
    onError: (err: Error) => {
      setOperationError(err.message)
      setDeleteTarget(null)
    },
  })

  useEscapeKey(!!selectedId && !showCreate && !deleteTarget, () => setSelectedId(null))

  async function handleRun(row: PromptExperiment) {
    setActioning(`run-${row.id}`)
    setOperationError(null)
    try {
      await promptLabApi.runExperiment(row.id)
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.all() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.detail(row.id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.status(row.id) })
    } catch (error) {
      setOperationError(getErrorMessage(error))
    } finally {
      setActioning(null)
    }
  }

  async function handleCancel(row: PromptExperiment) {
    setActioning(`cancel-${row.id}`)
    setOperationError(null)
    try {
      await promptLabApi.cancelExperiment(row.id)
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.all() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.detail(row.id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.status(row.id) })
    } catch (error) {
      setOperationError(getErrorMessage(error))
    } finally {
      setActioning(null)
    }
  }

  async function handleActivate(row: PromptExperiment) {
    setActioning(`activate-${row.id}`)
    setOperationError(null)
    try {
      await promptLabApi.activateExperimentRecommendation(row.id)
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.detail(row.id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.report(row.id) })
    } catch (error) {
      setOperationError(getErrorMessage(error))
    } finally {
      setActioning(null)
    }
  }

  async function handleAutoOptimize(request: { templateId: string; candidateCount?: number; judgeModel?: string }) {
    setOperationError(null)
    setAutoResult(null)
    try {
      const result = await promptLabApi.autoOptimize(request)
      setAutoResult(result)
      setShowOptimizeDialog(false)
    } catch (error) {
      setOperationError(getErrorMessage(error))
    }
  }

  async function handleAnalyze(request: { templateId: string; maxSamples?: number }) {
    setOperationError(null)
    try {
      const result = await promptLabApi.analyzeFeedback(request)
      setAnalysis(result)
      setShowAnalyzeDialog(false)
    } catch (error) {
      setOperationError(getErrorMessage(error))
    }
  }

  const columns = [
    {
      key: 'name',
      header: t('common.name'),
      width: '40%',
      responsivePriority: 1,
      render: (row: PromptExperiment) => row.name,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: '20%',
      responsivePriority: 1,
      render: (row: PromptExperiment) => (
        <span className={`prompt-lab-state prompt-lab-state--${statusTone(row.status)}`}>
          <span aria-hidden="true" />{statusLabel(t, row.status)}
        </span>
      ),
    },
    {
      key: 'versions',
      header: t('promptLabPage.versions'),
      width: '16%',
      responsivePriority: 2,
      render: (row: PromptExperiment) => 1 + row.candidateVersionIds.length,
    },
    {
      key: 'createdAt',
      header: t('common.createdAt'),
      width: '24%',
      responsivePriority: 2,
      render: (row: PromptExperiment) => formatDateTime(row.createdAt),
    },
  ]

  if (listError) {
    return (
      <div className="page prompt-lab-workspace">
        <PageHeader title={t('nav.promptLab')} description={t('nav.help.promptLab')} />
        <WorkspaceUnavailable
          title={t('promptLabPage.unavailableTitle')}
          description={t('promptLabPage.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('promptLabPage.openHealth'), to: '/health' }}
          guide={{
            title: t('promptLabPage.recoveryGuideTitle'),
            steps: [
              t('promptLabPage.recoveryGuide.account'),
              t('promptLabPage.recoveryGuide.status'),
              t('promptLabPage.recoveryGuide.retry'),
            ],
            technicalLabel: t('promptLabPage.technicalError'),
            technicalDetail: getErrorMessage(listError),
          }}
        />
      </div>
    )
  }

  return (
    <div className="page prompt-lab-workspace">
      <PageHeader
        title={t('nav.promptLab')}
        description={t('nav.help.promptLab')}
        actions={
          <div className="prompt-lab-toolbar">
            <label className="sr-only" htmlFor="prompt-lab-status-filter">{t('promptLabPage.filterStatus')}</label>
            <select
              id="prompt-lab-status-filter"
              value={statusFilter}
              onChange={(event) => { setStatusFilter(event.target.value as PromptExperimentStatus | ''); setPage(1) }}
            >
              <option value="">{t('promptLabPage.allExperiments')}</option>
              <option value="PENDING">{t('promptLabPage.statuses.waiting')}</option>
              <option value="RUNNING">{t('promptLabPage.statuses.running')}</option>
              <option value="COMPLETED">{t('promptLabPage.statuses.completed')}</option>
              <option value="FAILED">{t('promptLabPage.statuses.needsReview')}</option>
              <option value="CANCELLED">{t('promptLabPage.statuses.stopped')}</option>
            </select>
            <RefreshButton onRefresh={() => void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.all() })} />
            <button className="btn btn-secondary" onClick={() => setShowOptimizeDialog(true)}>{t('promptLabPage.autoOptimize')}</button>
            <button className="btn btn-secondary" onClick={() => setShowAnalyzeDialog(true)}>{t('promptLabPage.analyzeFeedback')}</button>
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>{t('promptLabPage.newExperiment')}</button>
          </div>
        }
      />

      {operationError ? (
        <section className="prompt-lab-operation-error" role="alert">
          <div>
            <strong>{t('promptLabPage.operationFailed')}</strong>
            <p>{t('promptLabPage.operationFailedDescription')}</p>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => setOperationError(null)}>{t('common.close')}</button>
          <details className="prompt-lab-technical-details">
            <summary>{t('promptLabPage.technicalError')}</summary>
            <code>{operationError}</code>
          </details>
        </section>
      ) : null}

      {autoResult ? (
        <section className="prompt-lab-operation-note">
          <strong>{t('promptLabPage.autoOptimizeStarted')}</strong>
          <p>{t('promptLabPage.autoOptimizeStartedDescription')}</p>
          <details className="prompt-lab-technical-details">
            <summary>{t('promptLabPage.technicalOperation')}</summary>
            <dl>
              <div><dt>{t('promptLabPage.jobIdentifier')}</dt><dd><code>{autoResult.jobId}</code></dd></div>
              <div><dt>{t('promptLabPage.templateIdentifier')}</dt><dd><code>{autoResult.templateId}</code></dd></div>
            </dl>
          </details>
        </section>
      ) : null}

      <div className={`split-layout ${(selectedId || analysis) ? '' : 'split-layout--collapsed'}`}>
        <div className="split-left">
          {isLoading ? (
            <TableSkeleton />
          ) : experiments.length === 0 ? (
            <EmptyState message={t('promptLabPage.noExperiments')} description={t('promptLabPage.emptyDescription')} />
          ) : (
            <>
              <p className="prompt-lab-count">
                {t('common.showingCount', { shown: experiments.slice((page - 1) * pageSize, page * pageSize).length, total: experiments.length })}
              </p>
              <DataTable
                columns={columns}
                data={experiments.slice((page - 1) * pageSize, page * pageSize)}
                keyFn={(row) => row.id}
                onRowClick={(row) => setSelectedId(row.id)}
                selectedKey={selectedId}
                page={page}
                pageSize={pageSize}
                totalCount={experiments.length}
                onPageChange={setPage}
              />
            </>
          )}
        </div>

        {(selectedId || analysis) ? (
          <div className="split-right">
            {analysis ? (
              <section className="prompt-feedback-analysis" aria-labelledby="prompt-feedback-analysis-title">
                <div className="prompt-feedback-analysis__heading">
                  <div>
                    <h2 id="prompt-feedback-analysis-title">{t('promptLabPage.feedbackAnalysisResult')}</h2>
                    <p>{t('promptLabPage.feedbackAnalysisDescription')}</p>
                  </div>
                  <button className="detail-close-btn" aria-label={t('common.close')} onClick={() => setAnalysis(null)}>
                    <X className="prompt-lab-close-icon" aria-hidden="true" />
                  </button>
                </div>
                <dl className="prompt-lab-facts">
                  <div><dt>{t('promptLabPage.totalFeedback')}</dt><dd>{analysis.totalFeedback}</dd></div>
                  <div><dt>{t('promptLabPage.negative')}</dt><dd>{analysis.negativeCount}</dd></div>
                  <div><dt>{t('promptLabPage.sampleQueries')}</dt><dd>{analysis.sampleQueryCount}</dd></div>
                  <div><dt>{t('promptLabPage.analyzedAt')}</dt><dd>{formatDateTime(analysis.analyzedAt)}</dd></div>
                </dl>
                {analysis.weaknesses.length > 0 ? (
                  <ol className="prompt-feedback-analysis__list">
                    {analysis.weaknesses.map((weakness) => (
                      <li key={weakness.category}>
                        <div><strong>{weakness.category}</strong><span>{t('promptLabPage.feedbackOccurrences', { count: weakness.frequency })}</span></div>
                        <p>{weakness.description}</p>
                        {weakness.exampleQueries.length > 0 ? (
                          <details className="prompt-lab-technical-details">
                            <summary>{t('promptLabPage.feedbackExamples')}</summary>
                            <ul>{weakness.exampleQueries.map((query) => <li key={query}>{query}</li>)}</ul>
                          </details>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                ) : <p className="prompt-feedback-analysis__empty">{t('promptLabPage.noWeaknesses')}</p>}
              </section>
            ) : null}

            {loadingDetails ? <TableSkeleton /> : null}
            {!loadingDetails && detailError ? (
              <section className="prompt-lab-detail-unavailable" aria-labelledby="prompt-lab-detail-unavailable-title">
                <h2 id="prompt-lab-detail-unavailable-title">{t('promptLabPage.detailUnavailableTitle')}</h2>
                <p>{t('promptLabPage.detailUnavailableDescription')}</p>
                <div className="detail-actions">
                  <button className="btn btn-secondary" onClick={() => void refetchDetail()}>{t('common.retry')}</button>
                  <button className="btn btn-secondary" onClick={() => setSelectedId(null)}>{t('promptLabPage.chooseAnother')}</button>
                </div>
                <details className="prompt-lab-technical-details">
                  <summary>{t('promptLabPage.technicalError')}</summary>
                  <code>{getErrorMessage(detailError)}</code>
                </details>
              </section>
            ) : null}
            {!loadingDetails && !detailError && selected ? (
              <ExperimentDetail
                experiment={selected}
                experimentStatus={experimentStatus}
                trials={trials}
                report={report}
                actioning={actioning}
                onRun={handleRun}
                onCancel={handleCancel}
                onActivate={handleActivate}
                onDelete={setDeleteTarget}
                onClose={() => setSelectedId(null)}
              />
            ) : null}
          </div>
        ) : null}
      </div>

      <CreateExperimentDialog
        open={showCreate}
        isPending={createMutation.isPending}
        onSubmit={(request) => {
          setOperationError(null)
          createMutation.mutate(request)
        }}
        onClose={() => setShowCreate(false)}
        onError={setOperationError}
      />

      {showOptimizeDialog ? <AutoOptimizeDialog onSubmit={handleAutoOptimize} onClose={() => setShowOptimizeDialog(false)} onError={setOperationError} /> : null}
      {showAnalyzeDialog ? <AnalyzeFeedbackDialog onSubmit={handleAnalyze} onClose={() => setShowAnalyzeDialog(false)} onError={setOperationError} /> : null}

      {deleteTarget ? (
        <ConfirmDialog
          title={t('promptLabPage.deleteTitle')}
          message={t('promptLabPage.deleteConfirm', { name: deleteTarget.name })}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
          danger
        />
      ) : null}
    </div>
  )
}
