import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog, DataTable, EmptyState, LoadingSpinner, TableSkeleton } from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useToastStore } from '../../../shared/store/toast.store'
import * as api from '../api'
import { ExperimentForm } from './ExperimentForm'
import { ExperimentResults } from './ExperimentResults'
import type {
  VersionResponse,
  PromptExperiment,
  CreatePromptExperimentRequest,
} from '../types'

interface ExperimentsTabProps {
  templateId: string
  templateName: string
  versions: VersionResponse[]
}

type ViewState = 'list' | 'form' | 'detail'

export function ExperimentsTab({ templateId, templateName, versions }: ExperimentsTabProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const [view, setView] = useState<ViewState>('list')
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)

  const statusLabel = (status: string) => {
    switch (status) {
      case 'PENDING': return t('promptStudio.experimentStatus.ready')
      case 'RUNNING': return t('promptStudio.experimentStatus.running')
      case 'COMPLETED': return t('promptStudio.experimentStatus.completed')
      case 'FAILED': return t('promptStudio.experimentStatus.failed')
      case 'CANCELLED': return t('promptStudio.experimentStatus.cancelled')
      default: return t('promptStudio.experimentStatus.unknown')
    }
  }

  // --- Data fetching ---

  const { data: allExperiments = [], isLoading: loadingList } = useQuery({
    queryKey: queryKeys.promptLab.list(),
    queryFn: () => api.listExperiments(),
  })

  const experiments = allExperiments.filter((exp) => exp.templateId === templateId)

  const { data: selectedExperiment = null, isLoading: loadingDetail } = useQuery({
    queryKey: queryKeys.promptLab.detail(selectedExperimentId ?? ''),
    queryFn: () => api.getExperiment(selectedExperimentId!),
    enabled: !!selectedExperimentId,
  })

  const selectedStatus = selectedExperiment?.status ?? null

  const { data: trials = [] } = useQuery({
    queryKey: queryKeys.promptLab.trials(selectedExperimentId ?? ''),
    queryFn: () => api.getExperimentTrials(selectedExperimentId!),
    enabled: !!selectedExperimentId && selectedStatus !== 'PENDING',
  })

  const { data: report = null } = useQuery({
    queryKey: queryKeys.promptLab.report(selectedExperimentId ?? ''),
    queryFn: () => api.getExperimentReport(selectedExperimentId!),
    enabled: !!selectedExperimentId && selectedStatus === 'COMPLETED',
  })

  // --- Mutations ---

  const createMutation = useMutation({
    mutationFn: (data: CreatePromptExperimentRequest) => api.createExperiment(data),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.list() })
      setSelectedExperimentId(created.id)
      setView('detail')
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
    },
  })

  const runMutation = useMutation({
    mutationFn: (id: string) => api.runExperiment(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.status(id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.detail(id) })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.cancelExperiment(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.status(id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.detail(id) })
    },
  })

  const activateMutation = useMutation({
    mutationFn: (id: string) => api.activateExperimentRecommendation(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.all() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('promptStudio.activateVersion', { version: '' }) })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteExperiment(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.promptLab.list() })
      setSelectedExperimentId(null)
      setView('list')
    },
  })

  // --- Handlers ---

  function handleCreateAndRun(data: CreatePromptExperimentRequest) {
    createMutation.mutate(data, {
      onSuccess: (created) => {
        runMutation.mutate(created.id)
      },
    })
  }

  function handleSelectExperiment(experiment: PromptExperiment) {
    setSelectedExperimentId(experiment.id)
    setView('detail')
  }

  function handleBackToList() {
    setSelectedExperimentId(null)
    setView('list')
  }

  // --- Columns ---

  const columns: Column<PromptExperiment>[] = [
    {
      key: 'name',
      header: t('promptStudio.experimentName'),
      width: '45%',
      render: (row) => row.name,
    },
    {
      key: 'status',
      header: t('common.status'),
      width: '20%',
      render: (row) => (
        <span className={`experiment-state experiment-state--${row.status.toLowerCase()}`}>
          <span aria-hidden="true" />
          {statusLabel(row.status)}
        </span>
      ),
    },
    {
      key: 'createdAt',
      header: t('common.createdAt'),
      width: '20%',
      render: (row) => formatDateTime(row.createdAt),
      responsivePriority: 3,
    },
    {
      key: 'versions',
      header: t('promptStudio.comparisonTargets'),
      width: '15%',
      render: (row) => t('promptStudio.comparisonTargetCount', {
        count: 1 + row.candidateVersionIds.length,
      }),
      responsivePriority: 4,
    },
  ]

  // --- Render: Empty state ---

  if (!loadingList && experiments.length === 0 && view === 'list') {
    return (
      <div className="experiments-tab">
        <div className="experiments-tab-header">
          <button
            className="btn btn-primary"
            onClick={() => setView('form')}
          >
            {t('promptStudio.newExperiment')}
          </button>
        </div>
        <EmptyState
          message={t('promptStudio.experimentsEmpty')}
          description={t('promptStudio.experimentsEmptyDesc')}
        />
        <ol className="prompt-comparison-guide">
          {[1, 2, 3].map((step) => (
            <li key={step}>
              <strong>{t(`promptStudio.comparisonGuide.step${step}Title`)}</strong>
              <span>{t(`promptStudio.comparisonGuide.step${step}Description`)}</span>
            </li>
          ))}
        </ol>
      </div>
    )
  }

  // --- Render: Form view ---

  if (view === 'form') {
    return (
      <div className="experiments-tab">
        <ExperimentForm
          templateId={templateId}
          templateName={templateName}
          versions={versions}
          onSubmit={handleCreateAndRun}
          onCancel={() => setView('list')}
          saving={createMutation.isPending || runMutation.isPending}
        />
      </div>
    )
  }

  // --- Render: Detail view ---

  if (view === 'detail' && selectedExperimentId) {
    if (loadingDetail) {
      return (
        <div className="experiments-tab">
          <LoadingSpinner />
        </div>
      )
    }

    if (!selectedExperiment) {
      return (
        <div className="experiments-tab">
          <EmptyState message={t('promptStudio.experimentsEmpty')} />
          <button className="btn btn-secondary" onClick={handleBackToList}>
            {t('common.back')}
          </button>
        </div>
      )
    }

    return (
      <div className="experiments-tab">
        <div className="experiment-detail-header">
          <button className="btn btn-secondary btn-sm" onClick={handleBackToList}>
            {t('common.back')}
          </button>
          <h3>{selectedExperiment.name}</h3>
          <span className={`experiment-state experiment-state--${selectedExperiment.status.toLowerCase()}`}>
            <span aria-hidden="true" />
            {statusLabel(selectedExperiment.status)}
          </span>
        </div>

        {selectedExperiment.status === 'PENDING' && (
          <div className="experiment-detail-actions">
            <button
              className="btn btn-primary"
              onClick={() => runMutation.mutate(selectedExperimentId)}
              disabled={runMutation.isPending}
            >
              {runMutation.isPending ? <LoadingSpinner size="sm" /> : t('promptStudio.runExperiment')}
            </button>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => setDeleteTarget(selectedExperimentId)}
              disabled={deleteMutation.isPending}
            >
              {t('common.delete')}
            </button>
          </div>
        )}

        {selectedExperiment.status === 'RUNNING' && (
          <div className="experiment-detail-actions">
            <LoadingSpinner size="sm" />
            <span className="text-muted">{t('promptStudio.running')}</span>
            <button
              className="btn btn-secondary"
              onClick={() => cancelMutation.mutate(selectedExperimentId)}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending ? <LoadingSpinner size="sm" /> : t('promptStudio.cancelExperiment')}
            </button>
          </div>
        )}

        {selectedExperiment.status === 'COMPLETED' && report && (
          <ExperimentResults
            report={report}
            trials={trials}
            onActivateWinner={() => activateMutation.mutate(selectedExperimentId)}
            activating={activateMutation.isPending}
          />
        )}

        {selectedExperiment.status === 'FAILED' && (
          <div className="alert alert-error">
            {selectedExperiment.description || t('error.crashDescription')}
          </div>
        )}

        {deleteTarget && (
          <ConfirmDialog
            title={t('common.delete')}
            message={t('promptStudio.deleteExperimentConfirm')}
            onConfirm={() => { deleteMutation.mutate(deleteTarget); setDeleteTarget(null) }}
            onCancel={() => setDeleteTarget(null)}
            danger
          />
        )}
      </div>
    )
  }

  // --- Render: List view ---

  return (
    <div className="experiments-tab">
      <div className="experiments-tab-header">
        <button
          className="btn btn-primary"
          onClick={() => setView('form')}
        >
          {t('promptStudio.newExperiment')}
        </button>
      </div>

      {loadingList ? (
        <TableSkeleton />
      ) : (
        <DataTable
          columns={columns}
          data={experiments}
          keyFn={(row) => row.id}
          onRowClick={handleSelectExperiment}
          selectedKey={selectedExperimentId}
        />
      )}
    </div>
  )
}
