import { lazy, Suspense, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import i18n from 'i18next'
import { ConfirmDialog, PageHeader, SkeletonChart, WorkspaceUnavailable } from '../../../shared/ui'
import { useUnsavedChanges, getErrorMessage } from '../../../shared/lib'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { RELEASE_DOCUMENT_INGESTION_ANCHOR_ID } from '../../../shared/releaseWorkflow'
import * as documentsApi from '../api'
import type { IngestionCandidate } from '../types'
import type { RagPolicyFormState } from './DocumentPolicyTab'
import { DocumentSearchTab } from './DocumentSearchTab'
import { DocumentRegisterSection } from './DocumentRegisterSection'
import { DocumentIngestionTab } from './DocumentIngestionTab'
import { DocumentPolicyTab } from './DocumentPolicyTab'
import { BulkSeedModal } from './BulkSeedModal'
import './documents.css'

// Lazy-load RagAnalyticsTab — pulls recharts via vendor-charts. The tab is
// only opened when the operator picks "analytics", so deferring keeps the
// default search/register experience free of the chart bundle.
const RagAnalyticsTab = lazy(() =>
  import('../../rag-analytics/ui/RagAnalyticsTab').then((m) => ({ default: m.RagAnalyticsTab })),
)

type DocumentsTab = 'search' | 'register' | 'ingestion' | 'policy' | 'analytics'

function parseDocumentsTab(value: string | null): DocumentsTab {
  if (
    value === 'search' ||
    value === 'register' ||
    value === 'ingestion' ||
    value === 'policy' ||
    value === 'analytics'
  ) {
    return value
  }
  return 'search'
}

function safeJsonParse(value: string): Record<string, unknown> {
  if (!value.trim()) return {}
  const parsed = JSON.parse(value)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(i18n.t('documentsPage.validation.jsonObjectRequired'))
  }
  return parsed as Record<string, unknown>
}

function parseCsv(raw: string): string[] {
  return raw
    .split(',')
    .map(item => item.trim().toLowerCase())
    .filter(Boolean)
}

export function DocumentsManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const [activeTab, setActiveTab] = useState<DocumentsTab>(() => parseDocumentsTab(searchParams.get('tab')))
  const [error, setError] = useState<string | null>(null)
  const [policyDirty, setPolicyDirty] = useState(false)
  const [bulkSeedOpen, setBulkSeedOpen] = useState(false)

  // Filter state lives in DocumentIngestionTab but we need it for query keys
  const [candidateStatus, setCandidateStatus] = useState<string | undefined>(undefined)
  const [candidateChannel, setCandidateChannel] = useState<string | undefined>(undefined)

  const {
    data: candidates = [],
    isLoading: loadingCandidates,
    isFetching: isRefreshingCandidates,
    error: candidatesError,
    refetch: refetchCandidates,
  } = useQuery({
    queryKey: queryKeys.documents.candidates(candidateStatus, candidateChannel),
    queryFn: () => documentsApi.listIngestionCandidates(
      candidateStatus ? (candidateStatus as 'PENDING' | 'INGESTED' | 'REJECTED') : undefined,
      candidateChannel || undefined,
    ),
    enabled: activeTab === 'ingestion',
    retry: false,
  })

  const { data: policyState = null, isLoading: loadingPolicy, error: policyError } = useQuery({
    queryKey: queryKeys.documents.policy(),
    queryFn: async () => {
      try {
        return await documentsApi.getRagIngestionPolicy()
      } catch (e) {
        const message = getErrorMessage(e)
        if (message.includes('HTTP 404')) {
          return null
        }
        throw e
      }
    },
    enabled: activeTab === 'policy',
    retry: false,
  })

  const [reviewingId, setReviewingId] = useState<string | null>(null)

  const approveMutation = useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => documentsApi.acceptCandidate(id, comment),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.candidates() })
    },
    onError: (err: Error) => setError(err.message),
    onSettled: () => setReviewingId(null),
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, comment }: { id: string; comment?: string }) => documentsApi.rejectCandidate(id, comment),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.candidates() })
    },
    onError: (err: Error) => setError(err.message),
    onSettled: () => setReviewingId(null),
  })

  const blocker = useUnsavedChanges(policyDirty)

  function selectTab(tab: DocumentsTab) {
    setActiveTab(tab)
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (tab === 'search') next.delete('tab')
      else next.set('tab', tab)
      return next
    }, { replace: true })
  }

  // Callbacks passed to DocumentSearchTab
  async function handleAddDocument(content: string, metadataRaw: string) {
    if (!content.trim()) {
      setError(t('documentsPage.validation.contentRequired'))
      throw new Error(t('documentsPage.validation.contentRequired'))
    }
    setError(null)
    try {
      const metadata = safeJsonParse(metadataRaw)
      const document = await documentsApi.addDocument({ content, metadata })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.candidates() })
      return document
    } catch (e) {
      const msg = getErrorMessage(e)
      setError(msg)
      useToastStore.getState().addToast({ type: 'error', message: msg })
      throw e
    }
  }

  async function handleBatchAdd(batchRaw: string) {
    setError(null)
    try {
      const parsed = JSON.parse(batchRaw)
      if (!Array.isArray(parsed)) throw new Error(t('documentsPage.validation.jsonArrayRequired'))
      const documents = parsed.map((item, index) => {
        if (!item || typeof item !== 'object') {
          throw new Error(t('documentsPage.validation.invalidDocument', { position: index + 1 }))
        }
        const row = item as { content?: unknown; metadata?: unknown }
        if (typeof row.content !== 'string' || !row.content.trim()) {
          throw new Error(t('documentsPage.validation.documentContentRequired', { position: index + 1 }))
        }
        if (row.metadata != null && (typeof row.metadata !== 'object' || Array.isArray(row.metadata))) {
          throw new Error(t('documentsPage.validation.documentMetadataMustBeObject', { position: index + 1 }))
        }
        return {
          content: row.content,
          metadata: row.metadata as Record<string, unknown> | undefined,
        }
      })

      await documentsApi.addDocumentsBatch({ documents })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.candidates() })
    } catch (e) {
      setError(getErrorMessage(e))
      throw e
    }
  }

  async function handleSearch(query: string, topK: number, threshold: number) {
    if (!query.trim()) {
      setError(t('documentsPage.validation.searchQueryRequired'))
      throw new Error(t('documentsPage.validation.searchQueryRequired'))
    }
    setError(null)
    try {
      return await documentsApi.searchDocuments({
        query,
        topK,
        similarityThreshold: threshold,
      })
    } catch (e) {
      setError(getErrorMessage(e))
      throw e
    }
  }

  async function handleDeleteResult(id: string) {
    setError(null)
    try {
      await documentsApi.deleteDocuments([id])
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.deleted') })
    } catch (e) {
      const msg = getErrorMessage(e)
      setError(msg)
      useToastStore.getState().addToast({ type: 'error', message: msg })
      throw e
    }
  }

  // Callbacks passed to DocumentIngestionTab
  function handleApprove(candidate: IngestionCandidate, comment?: string) {
    setReviewingId(candidate.id)
    setError(null)
    approveMutation.mutate({ id: candidate.id, comment })
  }

  function handleReject(candidate: IngestionCandidate, comment?: string) {
    setReviewingId(candidate.id)
    setError(null)
    rejectMutation.mutate({ id: candidate.id, comment })
  }

  function handleFilter(status: string, channel: string) {
    setCandidateStatus(status || undefined)
    setCandidateChannel(channel || undefined)
  }

  // Callbacks passed to DocumentPolicyTab
  async function handleSavePolicy(form: RagPolicyFormState) {
    setError(null)
    try {
      await documentsApi.updateRagIngestionPolicy({
        enabled: form.enabled,
        requireReview: form.requireReview,
        allowedChannels: parseCsv(form.allowedChannelsRaw),
        minQueryChars: Math.max(1, Number(form.minQueryChars) || 1),
        minResponseChars: Math.max(1, Number(form.minResponseChars) || 1),
        blockedPatterns: parseCsv(form.blockedPatternsRaw),
      })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.policy() })
    } catch (e) {
      const msg = getErrorMessage(e)
      setError(msg)
      useToastStore.getState().addToast({ type: 'error', message: msg })
      throw e
    }
  }

  async function handleResetPolicy() {
    setError(null)
    try {
      await documentsApi.resetRagIngestionPolicy()
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents.policy() })
    } catch (e) {
      setError(getErrorMessage(e))
      throw e
    }
  }

  function handleRefresh() {
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents.candidates() })
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents.policy() })
    useToastStore.getState().addToast({ type: 'success', message: t('common.toast.refreshed') })
  }

  return (
    <div className="page">
      <PageHeader
        title={t('nav.documents')}
        description={t('nav.help.documents')}
        actions={activeTab === 'policy' ? (
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setBulkSeedOpen(true)}
            >
              {t('documentsPage.bulkSeed.buttonLabel')}
            </button>
          </>
        ) : undefined}
      />

      <BulkSeedModal open={bulkSeedOpen} onClose={() => setBulkSeedOpen(false)} />

      {error && (
        <div className="alert alert-error alert-with-retry">
          <span className="alert-message">{error}</span>
          <button className="btn btn-sm btn-secondary" onClick={handleRefresh}>
            {t('common.retry')}
          </button>
        </div>
      )}

      <div className="detail-tabs" role="tablist" aria-label={t('documentsPage.tablistLabel')}>
        <button id="documents-tab-search" className={`tab-btn${activeTab === 'search' ? ' active' : ''}`} role="tab" type="button" aria-selected={activeTab === 'search'} aria-controls="documents-tabpanel-search" onClick={() => selectTab('search')}>
          {t('documentsPage.tabSearch')}
        </button>
        <button id="documents-tab-register" className={`tab-btn${activeTab === 'register' ? ' active' : ''}`} role="tab" type="button" aria-selected={activeTab === 'register'} aria-controls="documents-tabpanel-register" onClick={() => selectTab('register')}>
          {t('documentsPage.tabRegister')}
        </button>
        <button id="documents-tab-ingestion" className={`tab-btn${activeTab === 'ingestion' ? ' active' : ''}`} role="tab" type="button" aria-selected={activeTab === 'ingestion'} aria-controls={RELEASE_DOCUMENT_INGESTION_ANCHOR_ID} onClick={() => selectTab('ingestion')}>
          {t('documentsPage.tabIngestion')}
        </button>
        <button id="documents-tab-policy" className={`tab-btn${activeTab === 'policy' ? ' active' : ''}`} role="tab" type="button" aria-selected={activeTab === 'policy'} aria-controls="documents-tabpanel-policy" onClick={() => selectTab('policy')}>
          {t('documentsPage.tabPolicy')}
        </button>
        <button id="documents-tab-analytics" className={`tab-btn${activeTab === 'analytics' ? ' active' : ''}`} role="tab" type="button" aria-selected={activeTab === 'analytics'} aria-controls="documents-tabpanel-analytics" onClick={() => selectTab('analytics')}>
          {t('documentsPage.tabAnalytics')}
        </button>
      </div>

      {activeTab === 'search' && (
        <div id="documents-tabpanel-search" role="tabpanel" aria-labelledby="documents-tab-search">
          <DocumentSearchTab
            onSearch={handleSearch}
            onDeleteResult={handleDeleteResult}
            onRegister={() => selectTab('register')}
          />
        </div>
      )}

      {activeTab === 'register' && (
        <div id="documents-tabpanel-register" role="tabpanel" aria-labelledby="documents-tab-register">
          <DocumentRegisterSection
            onAddDocument={handleAddDocument}
            onBatchAdd={handleBatchAdd}
          />
        </div>
      )}

      {activeTab === 'ingestion' && (
        <div id={RELEASE_DOCUMENT_INGESTION_ANCHOR_ID} role="tabpanel" aria-labelledby="documents-tab-ingestion">
          {candidatesError ? (
            <WorkspaceUnavailable
              title={t('documentsPage.ingestion.unavailableTitle')}
              description={t('documentsPage.ingestion.unavailableDescription')}
              retryLabel={t('common.retry')}
              retryingLabel={t('common.retrying')}
              onRetry={refetchCandidates}
              isRetrying={isRefreshingCandidates}
              secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
              guide={{
                title: t('documentsPage.ingestion.recoveryGuideTitle'),
                steps: [
                  t('documentsPage.ingestion.recoveryCheckConnection'),
                  t('documentsPage.ingestion.recoveryCheckStorage'),
                  t('documentsPage.ingestion.recoveryRetry'),
                ],
                technicalLabel: t('documentsPage.ingestion.technicalError'),
                technicalDetail: getErrorMessage(candidatesError),
              }}
            />
          ) : (
            <DocumentIngestionTab
              candidates={candidates}
              loadingCandidates={loadingCandidates}
              onFilter={handleFilter}
              onApprove={handleApprove}
              onReject={handleReject}
              reviewingId={reviewingId}
              onRefresh={() => { void refetchCandidates() }}
            />
          )}
        </div>
      )}

      {activeTab === 'policy' && (
        <div id="documents-tabpanel-policy" role="tabpanel" aria-labelledby="documents-tab-policy">
          <DocumentPolicyTab
            policyState={policyState}
            loadingPolicy={loadingPolicy}
            policyError={policyError}
            onReloadPolicy={() => queryClient.invalidateQueries({ queryKey: queryKeys.documents.policy() })}
            onSavePolicy={handleSavePolicy}
            onResetPolicy={handleResetPolicy}
            onDirtyChange={setPolicyDirty}
          />
        </div>
      )}

      {activeTab === 'analytics' && (
        <div id="documents-tabpanel-analytics" role="tabpanel" aria-labelledby="documents-tab-analytics">
          <Suspense fallback={<SkeletonChart height={260} />}>
            <RagAnalyticsTab />
          </Suspense>
        </div>
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
    </div>
  )
}
