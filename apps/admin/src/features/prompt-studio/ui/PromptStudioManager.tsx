import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import './prompt-studio.css'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useToastStore } from '../../../shared/store/toast.store'
import {
  ConfirmDialog,
  DraftRecoveryBanner,
  EmptyState,
  LoadingSpinner,
  PageHeader,
  RefreshButton,
  TableSkeleton,
  Tabs,
  WorkspaceUnavailable,
} from '../../../shared/ui'
import { useUnsavedChanges, useEscapeKey, getErrorMessage, useFormDraft } from '../../../shared/lib'
import { scheduleUndoableDelete } from '../../../shared/lib/scheduleUndoableDelete'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import { formatDateTime } from '../../../shared/lib/formatters'
import * as api from '../api'
import type { TemplateResponse } from '../types'
import { TemplateList } from './TemplateList'
import { VersionsTab } from './VersionsTab'
import { ExperimentsTab } from './ExperimentsTab'
import { SettingsTab } from './SettingsTab'

export function PromptStudioManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  // --- Selection state ---
  const [selectedId, setSelectedId] = useState<string | null>(() => searchParams.get('template'))
  const sectionParam = searchParams.get('view')
  const activeSection = ['info', 'content', 'compare', 'history'].includes(sectionParam ?? '')
    ? sectionParam!
    : 'info'

  // --- Template form modal state ---
  const [showTemplateForm, setShowTemplateForm] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<TemplateResponse | null>(null)
  const [templateForm, setTemplateForm] = useState({ name: '', description: '' })
  const [initialTemplateForm, setInitialTemplateForm] = useState({ name: '', description: '' })
  const [formError, setFormError] = useState<string | null>(null)

  // --- Delete confirmation ---
  const [deleteTarget, setDeleteTarget] = useState<TemplateResponse | null>(null)

  // --- Unsaved changes guard ---
  const templateFormDirty = showTemplateForm && JSON.stringify(templateForm) !== JSON.stringify(initialTemplateForm)
  const blocker = useUnsavedChanges(templateFormDirty)

  // --- Draft auto-save (per the create / edit branch) ---
  const draftStorageKey = editingTemplate
    ? `prompt-studio:edit:${editingTemplate.id}`
    : 'prompt-studio:edit'
  const {
    recoveredDraft,
    recoveredAt,
    acceptRecovery,
    dismissRecovery,
    clearDraft: clearTemplateDraft,
  } = useFormDraft<{ name: string; description: string }>({
    storageKey: draftStorageKey,
    values: templateForm,
    enabled: showTemplateForm,
  })

  // --- Queries ---
  // Cap retries to 1 (default is 2) to avoid console flooding when the
  // backend `/api/prompt-templates` endpoint is unavailable or returns 5xx.
  // Two consumers (this page + chat-inspector) plus refetch-on-reconnect
  // can otherwise produce ~9 failed requests in dev tools per session.
  const { data: templates = [], isLoading, isFetching, error, refetch: refetchTemplates } = useQuery({
    queryKey: queryKeys.prompts.list(),
    queryFn: api.listTemplates,
    retry: 1,
    retryDelay: 800,
  })

  const { data: selected = null, isLoading: loadingDetail, isFetching: detailFetching, error: detailError, refetch: refetchDetail } = useQuery({
    queryKey: queryKeys.prompts.detail(selectedId ?? ''),
    queryFn: () => api.getTemplate(selectedId!),
    enabled: !!selectedId,
  })

  // --- Mutations ---
  const createTemplateMutation = useMutation({
    mutationFn: api.createTemplate,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
      clearTemplateDraft()
      setShowTemplateForm(false)
      setEditingTemplate(null)
    },
    onError: (err: Error) => {
      setFormError(err.message)
    },
  })

  const updateTemplateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name: string; description: string } }) =>
      api.updateTemplate(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      clearTemplateDraft()
      setShowTemplateForm(false)
      setEditingTemplate(null)
    },
    onError: (err: Error) => {
      setFormError(err.message)
    },
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (id: string) => api.deleteTemplate(id),
    onSuccess: () => {
      // Authoritative refetch after the grace period commits the delete.
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
    },
    onError: (err) => {
      // Optimistic UI removed the template from the cached list; re-sync so
      // the user can retry from the restored row.
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      showApiErrorToast(err)
    },
  })

  const createVersionMutation = useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: { content: string; changeLog: string } }) =>
      api.createVersion(templateId, data),
    onSuccess: (_data, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.detail(templateId) })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
    },
  })

  const activateVersionMutation = useMutation({
    mutationFn: ({ templateId, versionId }: { templateId: string; versionId: string }) =>
      api.activateVersion(templateId, versionId),
    onSuccess: (_data, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.detail(templateId) })
    },
  })

  const archiveVersionMutation = useMutation({
    mutationFn: ({ templateId, versionId }: { templateId: string; versionId: string }) =>
      api.archiveVersion(templateId, versionId),
    onSuccess: (_data, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.detail(templateId) })
    },
  })

  const saving = createTemplateMutation.isPending || updateTemplateMutation.isPending

  // --- Keyboard navigation ---
  useEscapeKey(!!selectedId && !showTemplateForm && !deleteTarget, () => {
    setSelectedId(null)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.delete('template')
      next.delete('view')
      return next
    }, { replace: true })
  })

  useEffect(() => {
    if (!selectedId || showTemplateForm || deleteTarget) return

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
      e.preventDefault()
      const idx = templates.findIndex((tpl) => tpl.id === selectedId)
      if (idx === -1) return
      if (e.key === 'ArrowUp' && idx > 0) {
        setSelectedId(templates[idx - 1].id)
      } else if (e.key === 'ArrowDown' && idx < templates.length - 1) {
        setSelectedId(templates[idx + 1].id)
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [selectedId, templates, showTemplateForm, deleteTarget])

  // --- Handlers ---
  function openTemplateForm(template?: TemplateResponse) {
    if (template) {
      setEditingTemplate(template)
      const loaded = { name: template.name, description: template.description }
      setTemplateForm(loaded)
      setInitialTemplateForm(loaded)
    } else {
      setEditingTemplate(null)
      const fresh = { name: '', description: '' }
      setTemplateForm(fresh)
      setInitialTemplateForm(fresh)
    }
    setFormError(null)
    setShowTemplateForm(true)
  }

  function selectTemplate(id: string) {
    setSelectedId(id)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('template', id)
      if (!next.get('view')) next.set('view', 'info')
      return next
    }, { replace: true })
  }

  function selectSection(nextSection: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('view', nextSection)
      return next
    }, { replace: true })
  }

  function handleSaveTemplate() {
    if (!templateForm.name.trim()) {
      setFormError(t('prompts.nameRequired'))
      return
    }
    setFormError(null)
    if (editingTemplate) {
      updateTemplateMutation.mutate({ id: editingTemplate.id, data: templateForm })
    } else {
      createTemplateMutation.mutate(templateForm)
    }
  }

  function handleDeleteTemplate() {
    if (!deleteTarget) return
    const target = deleteTarget
    const listKey = queryKeys.prompts.list()

    setDeleteTarget(null)
    const snapshot = queryClient.getQueryData<TemplateResponse[]>(listKey)

    scheduleUndoableDelete({
      message: t('prompts.deletedNamed', { name: target.name }),
      undoLabel: t('common.undo'),
      undoneMessage: t('common.toast.undone'),
      optimistic: () => {
        if (snapshot) {
          queryClient.setQueryData<TemplateResponse[]>(
            listKey,
            snapshot.filter((tpl) => tpl.id !== target.id),
          )
        }
        if (selectedId === target.id) {
          setSelectedId(null)
          setSearchParams((current) => {
            const next = new URLSearchParams(current)
            next.delete('template')
            next.delete('view')
            return next
          }, { replace: true })
        }
      },
      restore: () => {
        if (snapshot) {
          queryClient.setQueryData<TemplateResponse[]>(listKey, snapshot)
        } else {
          void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
        }
      },
      commit: () => deleteTemplateMutation.mutateAsync(target.id),
    })
  }

  function handleCreateVersion(data: { content: string; changeLog: string }) {
    if (!selectedId) return
    createVersionMutation.mutate({ templateId: selectedId, data })
  }

  function handleActivateVersion(v: { id: string }) {
    if (!selectedId) return
    activateVersionMutation.mutate({ templateId: selectedId, versionId: v.id })
  }

  function handleArchiveVersion(v: { id: string }) {
    if (!selectedId) return
    archiveVersionMutation.mutate({ templateId: selectedId, versionId: v.id })
  }

  function handleSettingsUpdate(data: { name: string; description: string }) {
    if (!selectedId) return
    updateTemplateMutation.mutate({ id: selectedId, data })
  }

  function handleSettingsDelete() {
    if (!selected) return
    setDeleteTarget(selected as TemplateResponse)
  }

  // --- Build activeVersions record for TemplateList ---
  const activeVersions: Record<string, { version: number; status: 'ACTIVE' }> = {}
  if (selected?.activeVersion && selectedId) {
    activeVersions[selectedId] = {
      version: selected.activeVersion.version,
      status: 'ACTIVE',
    }
  }

  // --- Activity log: derive from version history (newest first) ---
  const activityEntries = selected?.versions
    ? [...selected.versions].sort((a, b) => b.createdAt - a.createdAt).slice(0, 10)
    : []

  if (error && !isLoading) {
    return (
      <div className="page">
        <PageHeader title={t('nav.promptStudio')} description={t('promptStudio.pageGuide')} />
        <WorkspaceUnavailable
          title={t('promptStudio.loadErrorTitle')}
          description={t('promptStudio.loadErrorDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.loading')}
          onRetry={() => void refetchTemplates()}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('promptStudio.recoveryTitle'),
            steps: [t('promptStudio.recoveryConnection'), t('promptStudio.recoveryPermission')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      </div>
    )
  }

  return (
    <div className="page">
      <PageHeader
        title={t('nav.promptStudio')}
        description={t('promptStudio.pageGuide')}
        actions={
          <RefreshButton onRefresh={() => { void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() }) }} />
        }
      />

      {isLoading ? (
        <TableSkeleton />
      ) : templates.length === 0 ? (
        <section className="prompt-studio-empty" aria-label={t('prompts.empty')}>
          <EmptyState
            message={t('prompts.empty')}
            description={t('prompts.emptyDescription')}
            actionLabel={t('prompts.createTemplate')}
            onAction={() => openTemplateForm()}
          />
          <details className="prompt-studio-empty__example">
            <summary>
              <ChevronRight aria-hidden="true" size={15} />
              <span>{t('prompts.exampleDisclosure')}</span>
            </summary>
            <div>{t('prompts.emptyExample')}</div>
          </details>
        </section>
      ) : (
        <div className={`studio-layout${selectedId ? '' : ' studio-layout--list-only'}`}>
          <div className="studio-left">
            <TemplateList
              templates={templates}
              selectedId={selectedId}
              onSelect={selectTemplate}
              onCreateNew={() => openTemplateForm()}
              activeVersions={activeVersions}
            />
          </div>
          {selectedId && <div className="studio-right">
          {loadingDetail ? (
            <TableSkeleton />
          ) : detailError ? (
            <WorkspaceUnavailable
              title={t('promptStudio.detailLoadErrorTitle')}
              description={t('promptStudio.detailLoadErrorDescription')}
              retryLabel={t('common.retry')}
              retryingLabel={t('common.loading')}
              onRetry={() => void refetchDetail()}
              isRetrying={detailFetching}
              guide={{
                title: t('promptStudio.recoveryTitle'),
                technicalLabel: t('common.technicalDetails'),
                technicalDetail: getErrorMessage(detailError),
              }}
            />
          ) : selected ? (
            <>
              {/* Template header — name, status, version */}
              <div className="detail-header">
                <h2>{selected.name}</h2>
                <span className="prompt-current-version">
                  {selected.activeVersion
                    ? t('promptStudio.currentVersion', { version: selected.activeVersion.version })
                    : t('promptStudio.noCurrentVersion')}
                </span>
              </div>
              {selected.description && <p className="detail-description">{selected.description}</p>}
              <Tabs
                ariaLabel={t('promptStudio.workspaceNavLabel')}
                value={activeSection}
                onChange={selectSection}
                tabs={[
                  {
                    value: 'info',
                    label: t('promptStudioPage.sections.info'),
                    panel: <SettingsTab template={selected} onUpdate={handleSettingsUpdate} onDelete={handleSettingsDelete} saving={updateTemplateMutation.isPending} />,
                  },
                  {
                    value: 'content',
                    label: t('promptStudioPage.sections.body'),
                    panel: <VersionsTab template={selected} onCreateVersion={handleCreateVersion} onActivate={handleActivateVersion} onArchive={handleArchiveVersion} saving={createVersionMutation.isPending} />,
                  },
                  {
                    value: 'compare',
                    label: t('promptStudioPage.sections.experiments'),
                    panel: <ExperimentsTab templateId={selected.id} templateName={selected.name} versions={selected.versions} />,
                  },
                  {
                    value: 'history',
                    label: t('promptStudioPage.sections.activity'),
                    panel: activityEntries.length === 0 ? (
                      <EmptyState message={t('promptStudioPage.sections.activityEmpty')} />
                    ) : (
                      <ul className="activity-log" data-testid="prompt-studio-activity-log">
                        {activityEntries.map((v) => (
                          <li key={v.id} className="activity-log__item">
                            <span className="activity-log__when">{formatDateTime(v.createdAt)}</span>
                            <span className="activity-log__what">{t('promptStudio.versionLabel', { version: v.version })}</span>
                            {v.changeLog && <span className="activity-log__why">{v.changeLog}</span>}
                          </li>
                        ))}
                      </ul>
                    ),
                  },
                ]}
              />
            </>
          ) : null}
          </div>}
        </div>
      )}

      {/* Template create/edit modal */}
      {showTemplateForm && (
        <div className="modal-overlay" onClick={() => setShowTemplateForm(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="studio-template-modal-title"
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => { if (e.key === 'Escape') setShowTemplateForm(false) }}
          >
            <h3 id="studio-template-modal-title" className="modal-title">
              {editingTemplate ? t('prompts.editTemplate') : t('prompts.createTemplate')}
            </h3>
            <DraftRecoveryBanner
              open={!!recoveredDraft}
              savedAt={recoveredAt ?? undefined}
              onAccept={() => {
                if (recoveredDraft) {
                  setTemplateForm({
                    name: recoveredDraft.name ?? '',
                    description: recoveredDraft.description ?? '',
                  })
                }
                acceptRecovery()
              }}
              onDismiss={dismissRecovery}
            />
            {formError && <div className="alert alert-error">{formError}</div>}
            <form onSubmit={(e) => { e.preventDefault(); handleSaveTemplate() }} noValidate>
              <div className="form-group">
                <label htmlFor="template-name">{t('common.name')}</label>
                <input
                  id="template-name"
                  name="name"
                  placeholder={t('common.name')}
                  value={templateForm.name}
                  onChange={(e) => setTemplateForm((f) => ({ ...f, name: e.target.value }))}
                  autoFocus
                />
              </div>
              <div className="form-group">
                <label htmlFor="template-description">{t('common.description')}</label>
                <input
                  id="template-description"
                  name="description"
                  placeholder={t('prompts.descriptionPlaceholder')}
                  value={templateForm.description}
                  onChange={(e) => setTemplateForm((f) => ({ ...f, description: e.target.value }))}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowTemplateForm(false)}>{t('common.cancel')}</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>
                  {saving ? <LoadingSpinner size="sm" /> : t('common.save')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <ConfirmDialog
          title={t('prompts.deleteTitle')}
          message={t('prompts.deleteConfirm', { name: deleteTarget.name })}
          onConfirm={handleDeleteTemplate}
          onCancel={() => setDeleteTarget(null)}
          danger
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
    </div>
  )
}
