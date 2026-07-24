import { lazy, Suspense, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { downloadFile } from '../../../../shared/lib/downloadFile'
import { getErrorMessage } from '../../../../shared/lib/getErrorMessage'
import { SkeletonChart, SkeletonCard, SkeletonText } from '../../../../shared/ui/Skeleton'
import {
  getAdminSessionDetail,
  deleteAdminSession,
  exportAdminSession,
  addSessionTag,
  removeSessionTag,
} from '../../api'
import { getSessionCosts } from '../../../token-cost/api'

// Lazy-load the recharts-based cost summary so the session detail page renders
// without pulling vendor-charts unless the operator toggles "show costs".
const CostSummaryPanel = lazy(() =>
  import('../../../token-cost/ui/CostSummaryPanel').then((m) => ({
    default: m.CostSummaryPanel,
  })),
)
import { ToggleSwitch } from '../../../../shared/ui/ToggleSwitch'
import { queryKeys } from '../../../../shared/lib/queryKeys'
import { useToastStore } from '../../../../shared/store/toast.store'
import { ConfirmDialog } from '../../../../shared/ui/ConfirmDialog'
import { Breadcrumb } from '../../../../shared/ui/Breadcrumb'
import { PageHeader } from '../../../../shared/ui/PageHeader'
import { WorkspaceUnavailable } from '../../../../shared/ui/WorkspaceUnavailable'
import { MessageList } from './MessageList'
import { SessionInfoBar } from './SessionInfoBar'
import { SessionTags } from './SessionTags'
import { SessionRuntimeSummary } from './SessionRuntimeSummary'
import type { SessionTag, SessionExportFormat } from '../../types'
import '../../../token-cost/ui/token-cost.css'

const MESSAGE_BATCH_SIZE = 50

export function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  const [visibleCount, setVisibleCount] = useState(MESSAGE_BATCH_SIZE)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [localTags, setLocalTags] = useState<SessionTag[] | null>(null)
  const [showTagForm, setShowTagForm] = useState(false)
  const [showCosts, setShowCosts] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: queryKeys.sessions.detail(sessionId ?? ''),
    queryFn: () => getAdminSessionDetail(sessionId!),
    enabled: !!sessionId,
  })

  const { data: sessionCosts = [] } = useQuery({
    queryKey: queryKeys.tokenCost.session(sessionId ?? ''),
    queryFn: () => getSessionCosts(sessionId!),
    enabled: !!sessionId && showCosts,
  })

  // Map costs by index (runId pattern: run-{sessionId}-{index})
  const costsByMessageIndex = new Map(
    sessionCosts.map((c) => {
      const parts = c.runId.split('-')
      const idx = Number(parts[parts.length - 1])
      return [idx, c] as const
    }),
  )

  // Sync local tags with server data when it first loads
  const tags = localTags ?? data?.tags ?? []

  const deleteMutation = useMutation({
    mutationFn: () => deleteAdminSession(sessionId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions.all() })
      void navigate('/sessions/feed')
    },
  })

  const addTagMutation = useMutation({
    mutationFn: ({ label, comment }: { label: string; comment?: string }) =>
      addSessionTag(sessionId!, label, comment),
    onSuccess: (newTag) => {
      setLocalTags((prev) => [...(prev ?? data?.tags ?? []), newTag])
    },
  })

  const removeTagMutation = useMutation({
    mutationFn: (tagId: string) => removeSessionTag(sessionId!, tagId),
    onSuccess: (_data, tagId) => {
      setLocalTags((prev) => (prev ?? data?.tags ?? []).filter((tag) => tag.id !== tagId))
    },
  })

  async function handleExport(format: SessionExportFormat) {
    if (!sessionId) return
    try {
      const blob = await exportAdminSession(sessionId, format)
      const extension = format === 'markdown' ? 'md' : 'json'
      downloadFile(blob, `${sessionId}.${extension}`)
    } catch {
      useToastStore.getState().addToast({ type: 'error', message: t('sessions.exportError') })
    }
  }

  function handleOpenInspector() {
    void navigate('/chat-inspector')
  }

  function handleFlag() {
    setShowTagForm(true)
  }

  function handleAddTag(label: string, comment?: string) {
    addTagMutation.mutate({ label, comment })
  }

  function handleRemoveTag(tagId: string) {
    removeTagMutation.mutate(tagId)
  }

  function loadOlder() {
    setVisibleCount((prev) => prev + MESSAGE_BATCH_SIZE)
  }

  const detailBreadcrumbItems = sessionId
    ? [
        { label: t('conversations.title'), href: '/sessions' },
        { label: t('conversations.detail.title'), href: '/sessions/feed' },
        { label: t('conversations.detail.selectedConversation') },
      ]
    : [
        { label: t('conversations.title'), href: '/sessions' },
        { label: t('conversations.detail.title') },
      ]

  const detailHeader = (
    <PageHeader
      title={t('conversations.detail.title')}
      description={t('conversations.detail.description')}
    />
  )

  if (isLoading) {
    return (
      <div className="page">
        <Breadcrumb items={detailBreadcrumbItems} />
        {detailHeader}
        <SkeletonCard height={64} />
        <SkeletonText lines={3} lastLineWidth="60%" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="page">
        <Breadcrumb items={detailBreadcrumbItems} />
        {detailHeader}
        <WorkspaceUnavailable
          title={error ? t('conversations.detail.loadErrorTitle') : t('conversations.detail.notFound')}
          description={error ? t('conversations.detail.loadErrorDescription') : t('conversations.detail.notFoundDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={() => queryClient.invalidateQueries({ queryKey: queryKeys.sessions.detail(sessionId ?? '') })}
          secondaryAction={{ label: t('conversations.detail.backToList'), to: '/sessions/feed' }}
          guide={error ? { title: t('conversations.recovery.title'), steps: [t('conversations.recovery.account'), t('conversations.recovery.connection')], technicalLabel: t('common.technicalDetails'), technicalDetail: getErrorMessage(error) } : undefined}
        />
      </div>
    )
  }

  const visibleMessages = data.messages.slice(-visibleCount)
  const hasOlderMessages = visibleMessages.length < data.messages.length

  return (
    <div className="page session-detail-page">
      <Breadcrumb items={detailBreadcrumbItems} />
      {detailHeader}

      <div className="session-detail-content">
        <section id="session-section-info">
          <SessionInfoBar
            session={data}
            onExport={(format) => void handleExport(format)}
            onDelete={() => setShowDeleteConfirm(true)}
            onOpenInspector={handleOpenInspector}
            onFlag={handleFlag}
          />
        </section>

        <section id="session-section-messages">
          {hasOlderMessages && (
            <div className="chat-load-older">
              <button className="btn btn-secondary" onClick={loadOlder}>
                {t('conversations.detail.loadOlder')}
              </button>
              <div className="message-showing" aria-live="polite">
                {t('conversations.detail.showingMessages', {
                  shown: visibleMessages.length,
                  total: data.messages.length,
                })}
              </div>
            </div>
          )}

          <MessageList
            messages={visibleMessages}
            costsByMessageIndex={costsByMessageIndex}
            showCost={showCosts}
            hasOlderMessages={hasOlderMessages}
            onLoadOlder={loadOlder}
          />
        </section>

        <section id="session-section-tags">
          <SessionTags
            tags={tags}
            trust={data.trust}
            onAddTag={handleAddTag}
            onRemoveTag={handleRemoveTag}
            showForm={showTagForm}
            onFormToggle={setShowTagForm}
          />
        </section>

        <div className="cost-toggle">
          <ToggleSwitch
            checked={showCosts}
            onChange={setShowCosts}
            label={t('tokenCost.showCosts')}
          />
          <span className="cost-toggle-label" aria-hidden="true">
            {t('tokenCost.showCosts')}
          </span>
        </div>

        {showCosts && sessionCosts.length > 0 && (
          <section id="session-section-costs">
            <Suspense fallback={<SkeletonChart height={200} />}>
              <CostSummaryPanel costs={sessionCosts} />
            </Suspense>
          </section>
        )}

        <SessionRuntimeSummary session={data} />
      </div>

      {showDeleteConfirm && (
        <ConfirmDialog
          title={t('conversations.detail.delete')}
          message={t('conversations.detail.deleteConfirm', { sessionId })}
          onConfirm={() => deleteMutation.mutate()}
          onCancel={() => setShowDeleteConfirm(false)}
          danger
        />
      )}
    </div>
  )
}
