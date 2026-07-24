import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { ConfirmDialog, DataTable, DetailSkeleton, EmptyState, OperationButton, PageHeader, RefreshButton, TableSkeleton, WorkspaceUnavailable, useAnnouncer } from '../../../shared/ui'
import { useUnsavedChanges, useEscapeKey, getErrorMessage } from '../../../shared/lib'
import { useToastStore } from '../../../shared/store/toast.store'
import { queryKeys } from '../../../shared/lib/queryKeys'
import * as promptsApi from '../api'
import type { TemplateResponse, VersionResponse } from '../types'
import { formatDateTime } from '../../../shared/lib/formatters'
import './prompts.css'

function localizeVersionStatus(status: VersionResponse['status'], t: (key: string) => string) {
  if (status === 'ACTIVE') return t('prompts.versionStatus.active')
  if (status === 'DRAFT') return t('prompts.versionStatus.draft')
  if (status === 'ARCHIVED') return t('prompts.versionStatus.archived')
  return t('prompts.versionStatus.unknown')
}

export function PromptsManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()

  const pageSize = 30
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const [showTemplateForm, setShowTemplateForm] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<TemplateResponse | null>(null)
  const [templateForm, setTemplateForm] = useState({ name: '', description: '' })
  const [initialTemplateForm, setInitialTemplateForm] = useState({ name: '', description: '' })
  const [formError, setFormError] = useState<string | null>(null)
  const [formTechnicalError, setFormTechnicalError] = useState<string | null>(null)

  const [showVersionForm, setShowVersionForm] = useState(false)
  const [versionForm, setVersionForm] = useState({ content: '', changeLog: '' })
  const [initialVersionForm, setInitialVersionForm] = useState({ content: '', changeLog: '' })

  const [deleteTemplateTarget, setDeleteTemplateTarget] = useState<TemplateResponse | null>(null)

  const templateFormDirty = showTemplateForm && JSON.stringify(templateForm) !== JSON.stringify(initialTemplateForm)
  const versionFormDirty = showVersionForm && JSON.stringify(versionForm) !== JSON.stringify(initialVersionForm)
  const blocker = useUnsavedChanges(templateFormDirty || versionFormDirty)

  // Cap retries to 1 (default is 2) to avoid retry storms when the backend
  // `/api/prompt-templates` endpoint is unavailable. The error banner below
  // surfaces the failure to the operator immediately rather than after
  // multiple silent retry rounds.
  const { data: templates = [], isLoading, error } = useQuery({
    queryKey: queryKeys.prompts.list(),
    queryFn: promptsApi.listTemplates,
    retry: 1,
    retryDelay: 800,
  })

  const {
    data: selected = null,
    isLoading: loadingDetail,
    error: detailError,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: queryKeys.prompts.detail(selectedId ?? ''),
    queryFn: () => promptsApi.getTemplate(selectedId!),
    enabled: !!selectedId,
  })

  const createTemplateMutation = useMutation({
    mutationFn: promptsApi.createTemplate,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
      announce(t('common.a11y.created'))
      setShowTemplateForm(false)
      setEditingTemplate(null)
    },
    onError: (err: Error) => {
      setFormError(t('prompts.saveUnavailable'))
      setFormTechnicalError(getErrorMessage(err))
      announce(t('prompts.saveUnavailable'), { priority: 'assertive' })
    },
  })

  const updateTemplateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name: string; description: string } }) =>
      promptsApi.updateTemplate(id, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      announce(t('common.a11y.updated'))
      setShowTemplateForm(false)
      setEditingTemplate(null)
    },
    onError: (err: Error) => {
      setFormError(t('prompts.saveUnavailable'))
      setFormTechnicalError(getErrorMessage(err))
      announce(t('prompts.saveUnavailable'), { priority: 'assertive' })
    },
  })

  const deleteTemplateMutation = useMutation({
    mutationFn: (id: string) => promptsApi.deleteTemplate(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })
      if (selectedId === id) setSelectedId(null)
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.deleted') })
      announce(t('common.a11y.deleted'))
      setDeleteTemplateTarget(null)
    },
    onError: () => {
      setDeleteTemplateTarget(null)
      useToastStore.getState().addToast({ type: 'error', message: t('prompts.deleteUnavailable') })
      announce(t('prompts.deleteUnavailable'), { priority: 'assertive' })
    },
  })

  const createVersionMutation = useMutation({
    mutationFn: ({ templateId, data }: { templateId: string; data: { content: string; changeLog: string } }) =>
      promptsApi.createVersion(templateId, data),
    onSuccess: (_data, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.detail(templateId) })
      setShowVersionForm(false)
      setVersionForm({ content: '', changeLog: '' })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.created') })
      announce(t('common.a11y.created'))
    },
    onError: (err: Error) => {
      setFormError(t('prompts.saveUnavailable'))
      setFormTechnicalError(getErrorMessage(err))
      announce(t('prompts.saveUnavailable'), { priority: 'assertive' })
    },
  })

  const activateVersionMutation = useMutation({
    mutationFn: ({ templateId, versionId }: { templateId: string; versionId: string }) =>
      promptsApi.activateVersion(templateId, versionId),
    onSuccess: (_data, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.detail(templateId) })
      announce(t('common.a11y.updated'))
    },
    onError: () => {
      useToastStore.getState().addToast({ type: 'error', message: t('prompts.versionUpdateUnavailable') })
      announce(t('prompts.versionUpdateUnavailable'), { priority: 'assertive' })
    },
  })

  const archiveVersionMutation = useMutation({
    mutationFn: ({ templateId, versionId }: { templateId: string; versionId: string }) =>
      promptsApi.archiveVersion(templateId, versionId),
    onSuccess: (_data, { templateId }) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.detail(templateId) })
      announce(t('common.a11y.updated'))
    },
    onError: () => {
      useToastStore.getState().addToast({ type: 'error', message: t('prompts.versionUpdateUnavailable') })
      announce(t('prompts.versionUpdateUnavailable'), { priority: 'assertive' })
    },
  })

  const saving = createTemplateMutation.isPending || updateTemplateMutation.isPending || createVersionMutation.isPending

  useEscapeKey(!!selectedId && !showTemplateForm && !showVersionForm && !deleteTemplateTarget, () => setSelectedId(null))

  function handleSaveTemplate() {
    if (!templateForm.name.trim()) {
      setFormError(t('prompts.nameRequired'))
      setFormTechnicalError(null)
      return
    }
    setFormError(null)
    setFormTechnicalError(null)
    if (editingTemplate) {
      updateTemplateMutation.mutate({ id: editingTemplate.id, data: templateForm })
    } else {
      createTemplateMutation.mutate(templateForm)
    }
  }

  function handleSaveVersion() {
    if (!selectedId || !versionForm.content.trim()) {
      setFormError(t('prompts.contentRequired'))
      setFormTechnicalError(null)
      return
    }
    setFormError(null)
    setFormTechnicalError(null)
    createVersionMutation.mutate({ templateId: selectedId, data: versionForm })
  }

  function handleActivate(v: VersionResponse) {
    if (!selectedId) return
    activateVersionMutation.mutate({ templateId: selectedId, versionId: v.id })
  }

  function handleArchive(v: VersionResponse) {
    if (!selectedId) return
    archiveVersionMutation.mutate({ templateId: selectedId, versionId: v.id })
  }

  function handleDeleteTemplate() {
    if (!deleteTemplateTarget) return
    deleteTemplateMutation.mutate(deleteTemplateTarget.id)
  }

  function openCreateTemplate() {
    setEditingTemplate(null)
    const fresh = { name: '', description: '' }
    setTemplateForm(fresh)
    setInitialTemplateForm(fresh)
    setFormError(null)
    setFormTechnicalError(null)
    setShowTemplateForm(true)
  }

  const templateColumns = [
    {
      key: 'name', header: t('common.name'), width: '42%',
      render: (tpl: TemplateResponse) => tpl.name,
    },
    {
      key: 'description', header: t('common.description'), width: '38%',
      render: (tpl: TemplateResponse) => tpl.description || '-',
    },
    {
      key: 'updatedAt', header: t('common.updatedAt'), width: '20%',
      render: (tpl: TemplateResponse) => formatDateTime(tpl.updatedAt),
    },
  ]

  return (
    <div className="page prompts-workspace">
      <PageHeader
        title={t('nav.prompts')}
        description={t('nav.help.prompts')}
        actions={
          <>
            <RefreshButton onRefresh={() => queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })} />
            <OperationButton onClick={openCreateTemplate}>
              {t('prompts.createTemplate')}
            </OperationButton>
          </>
        }
      />

      {error ? (
        <WorkspaceUnavailable
          title={t('prompts.unavailableTitle')}
          description={t('prompts.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={() => void queryClient.invalidateQueries({ queryKey: queryKeys.prompts.all() })}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('prompts.recoveryGuideTitle'),
            steps: [t('prompts.recoveryCheckConnection'), t('prompts.recoveryCheckPermission')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(error),
          }}
        />
      ) : (
      <div className={`prompts-workspace__body${selectedId ? ' prompts-workspace__body--detail' : ''}`}>
        <section className="prompts-list" aria-labelledby="prompts-list-title">
          <header>
            <div>
              <h2 id="prompts-list-title">{t('prompts.listTitle')}</h2>
              <p>{t('prompts.pageGuide')}</p>
            </div>
            {!isLoading ? <span>{t('prompts.listCount', { count: templates.length })}</span> : null}
          </header>
          {isLoading ? (
            <TableSkeleton />
          ) : templates.length === 0 ? (
            <div className="prompts-empty">
              <EmptyState
                message={t('prompts.empty')}
                description={t('nav.help.prompts')}
                actionLabel={t('prompts.createTemplate')}
                onAction={openCreateTemplate}
              />
            </div>
          ) : (
            <>
              <div className="detail-note prompts-list__count-note">
                {t('common.showingCount', { shown: templates.slice((page - 1) * pageSize, page * pageSize).length, total: templates.length })}
              </div>
              <DataTable
                columns={templateColumns}
                data={templates.slice((page - 1) * pageSize, page * pageSize)}
                keyFn={tpl => tpl.id}
                onRowClick={(tpl) => setSelectedId(tpl.id)}
                selectedKey={selectedId}
                page={page}
                pageSize={pageSize}
                totalCount={templates.length}
                onPageChange={setPage}
              />
            </>
          )}
        </section>

        {selectedId ? (
          <aside className="prompt-detail" aria-labelledby="prompt-detail-title">
            {loadingDetail ? (
              <DetailSkeleton />
            ) : detailError ? (
              <section className="prompt-detail__unavailable" aria-labelledby="prompt-detail-unavailable-title">
                <h2 id="prompt-detail-unavailable-title">{t('prompts.detailUnavailableTitle')}</h2>
                <p>{t('prompts.detailUnavailableDescription')}</p>
                <div className="detail-actions">
                  <OperationButton variant="secondary" onClick={() => void refetchDetail()}>{t('common.retry')}</OperationButton>
                  <OperationButton variant="ghost" onClick={() => setSelectedId(null)}>{t('prompts.chooseAnother')}</OperationButton>
                </div>
                <details className="prompt-detail__technical">
                  <summary>{t('common.technicalDetails')}</summary>
                  <code>{getErrorMessage(detailError)}</code>
                </details>
              </section>
            ) : selected ? (
              <>
                <header className="prompt-detail__header">
                  <div>
                    <h2 id="prompt-detail-title">{selected.name}</h2>
                    {selected.description ? <p>{selected.description}</p> : null}
                  </div>
                  <button className="prompt-detail__close" onClick={() => setSelectedId(null)} aria-label={t('common.close')}>
                    <X aria-hidden="true" />
                  </button>
                </header>

                <dl className="prompt-detail__facts">
                  <div><dt>{t('common.createdAt')}</dt><dd>{formatDateTime(selected.createdAt)}</dd></div>
                  <div><dt>{t('common.updatedAt')}</dt><dd>{formatDateTime(selected.updatedAt)}</dd></div>
                  <div><dt>{t('prompts.versionCount')}</dt><dd>{selected.versions.length}</dd></div>
                  <div><dt>{t('prompts.activeVersion')}</dt><dd>{selected.activeVersion ? t('prompts.activeVersionValue', { version: selected.activeVersion.version }) : t('prompts.noActiveVersion')}</dd></div>
                </dl>

                <div className="detail-actions prompt-detail__actions">
                  <OperationButton variant="secondary" onClick={() => {
                    setEditingTemplate(selected)
                    const loaded = { name: selected.name, description: selected.description }
                    setTemplateForm(loaded)
                    setInitialTemplateForm(loaded)
                    setFormError(null)
                    setFormTechnicalError(null)
                    setShowTemplateForm(true)
                  }}>
                    {t('common.edit')}
                  </OperationButton>
                  <OperationButton variant="danger" onClick={() => setDeleteTemplateTarget(selected)}>{t('common.delete')}</OperationButton>
                </div>

                <section className="prompt-detail__versions" aria-labelledby="prompt-versions-title">
                  <header>
                    <div>
                      <h3 id="prompt-versions-title">{t('prompts.versions')}</h3>
                      <p>{t('prompts.versionGuide')}</p>
                    </div>
                    <OperationButton variant="secondary" onClick={() => {
                      const loaded = { content: selected.activeVersion?.content ?? '', changeLog: '' }
                      setVersionForm(loaded)
                      setInitialVersionForm(loaded)
                      setFormError(null)
                      setFormTechnicalError(null)
                      setShowVersionForm(true)
                    }}>
                      {t('prompts.newVersion')}
                    </OperationButton>
                  </header>
                  {selected.versions.length === 0 ? (
                    <p className="prompt-detail__empty">{t('prompts.noVersions')}</p>
                  ) : (
                    <div className="prompt-version-list">
                      {selected.versions.map((version) => (
                        <article key={version.id} className="prompt-version">
                          <header>
                            <div className="prompt-version__identity">
                              <strong>{t('prompts.versionLabel', { version: version.version })}</strong>
                              <span
                                className="prompt-version__state"
                                data-status={version.status}
                                aria-label={localizeVersionStatus(version.status, t)}
                                title={localizeVersionStatus(version.status, t)}
                              >
                                <span aria-hidden="true" />
                                {localizeVersionStatus(version.status, t)}
                              </span>
                            </div>
                            <time dateTime={new Date(version.createdAt).toISOString()}>{formatDateTime(version.createdAt)}</time>
                          </header>
                          {version.changeLog ? <p className="prompt-version__change">{version.changeLog}</p> : null}
                          <p className="prompt-version__content">{version.content}</p>
                          {version.status === 'DRAFT' ? (
                            <div className="prompt-version__actions">
                              <OperationButton onClick={() => handleActivate(version)}>{t('prompts.activate')}</OperationButton>
                            </div>
                          ) : version.status === 'ACTIVE' ? (
                            <div className="prompt-version__actions">
                              <OperationButton variant="secondary" onClick={() => handleArchive(version)}>{t('prompts.archive')}</OperationButton>
                            </div>
                          ) : null}
                        </article>
                      ))}
                    </div>
                  )}
                </section>

                <details className="prompt-detail__technical">
                  <summary>{t('prompts.technicalDetails')}</summary>
                  <dl>
                    <div><dt>{t('prompts.templateIdentifier')}</dt><dd><code>{selected.id}</code></dd></div>
                    <div><dt>{t('prompts.activeVersionIdentifier')}</dt><dd><code>{selected.activeVersion?.id ?? '-'}</code></dd></div>
                  </dl>
                </details>
              </>
            ) : null}
          </aside>
        ) : null}
      </div>
      )}

      {showTemplateForm && (
        <div className="modal-overlay" onClick={() => setShowTemplateForm(false)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="prompts-template-modal-title"
            tabIndex={-1}
            onClick={e => e.stopPropagation()}
            onKeyDown={e => { if (e.key === 'Escape') setShowTemplateForm(false) }}
          >
            <h3 id="prompts-template-modal-title" className="modal-title">
              {editingTemplate ? t('prompts.editTemplate') : t('prompts.createTemplate')}
            </h3>
            {formError ? (
              <div className="alert alert-error prompts-form-error" role="alert">
                <span>{formError}</span>
                {formTechnicalError ? (
                  <details>
                    <summary>{t('common.technicalDetails')}</summary>
                    <code>{formTechnicalError}</code>
                  </details>
                ) : null}
              </div>
            ) : null}
            <div className="form-group">
              <label htmlFor="template-name">{t('common.name')}</label>
              <input
                id="template-name"
                name="name"
                placeholder={t('common.name')}
                value={templateForm.name}
                onChange={e => setTemplateForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label htmlFor="template-description">{t('common.description')}</label>
              <input
                id="template-description"
                name="description"
                placeholder={t('prompts.descriptionPlaceholder')}
                value={templateForm.description}
                onChange={e => setTemplateForm(f => ({ ...f, description: e.target.value }))}
              />
            </div>
            <div className="modal-actions">
              <OperationButton variant="secondary" onClick={() => setShowTemplateForm(false)}>{t('common.cancel')}</OperationButton>
              <OperationButton onClick={handleSaveTemplate} isOperating={saving}>{t('common.save')}</OperationButton>
            </div>
          </div>
        </div>
      )}

      {showVersionForm && (
        <div className="modal-overlay" onClick={() => setShowVersionForm(false)}>
          <div
            className="modal modal-lg"
            role="dialog"
            aria-modal="true"
            aria-labelledby="prompts-version-modal-title"
            tabIndex={-1}
            onClick={e => e.stopPropagation()}
            onKeyDown={e => { if (e.key === 'Escape') setShowVersionForm(false) }}
          >
            <h3 id="prompts-version-modal-title" className="modal-title">{t('prompts.newVersion')}</h3>
            {formError ? (
              <div className="alert alert-error prompts-form-error" role="alert">
                <span>{formError}</span>
                {formTechnicalError ? (
                  <details>
                    <summary>{t('common.technicalDetails')}</summary>
                    <code>{formTechnicalError}</code>
                  </details>
                ) : null}
              </div>
            ) : null}
            <div className="form-group">
              <label htmlFor="version-content">{t('prompts.content')}</label>
              <textarea
                id="version-content"
                name="content"
                rows={12}
                value={versionForm.content}
                onChange={e => setVersionForm(f => ({ ...f, content: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label htmlFor="version-changelog">{t('prompts.changeLog')}</label>
              <input
                id="version-changelog"
                name="changeLog"
                placeholder={t('prompts.changeLog')}
                value={versionForm.changeLog}
                onChange={e => setVersionForm(f => ({ ...f, changeLog: e.target.value }))}
              />
            </div>
            <div className="modal-actions">
              <OperationButton variant="secondary" onClick={() => setShowVersionForm(false)}>{t('common.cancel')}</OperationButton>
              <OperationButton onClick={handleSaveVersion} isOperating={saving}>{t('common.save')}</OperationButton>
            </div>
          </div>
        </div>
      )}

      {deleteTemplateTarget && (
        <ConfirmDialog
          title={t('prompts.deleteTitle')}
          message={t('prompts.deleteConfirm', { name: deleteTemplateTarget.name })}
          onConfirm={handleDeleteTemplate}
          onCancel={() => setDeleteTemplateTarget(null)}
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
