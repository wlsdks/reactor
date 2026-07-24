import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { ChevronRight, X } from 'lucide-react'
import './personas.css'
import { DataTable, ConfirmDialog, PageHeader, TableSkeleton, DetailSkeleton, WorkspaceUnavailable, useAnnouncer, type BulkAction, type Column } from '../../../shared/ui'
import { useToastStore } from '../../../shared/store/toast.store'
import { useEscapeKey } from '../../../shared/lib/useEscapeKey'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { showApiErrorToast } from '../../../shared/lib/showApiErrorToast'
import { scheduleUndoableDelete } from '../../../shared/lib/scheduleUndoableDelete'
import * as personasApi from '../api'
import type { PersonaResponse } from '../types'
import { PersonaInfoTab } from './PersonaInfoTab'
import { PersonaPlayground } from './PersonaPlayground'
import { PersonaFormModal } from './PersonaFormModal'
import { formatDateTime } from '../../../shared/lib/formatters'
import { queryKeys } from '../../../shared/lib/queryKeys'

type TabKey = 'info' | 'playground'

export function PersonaManager() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { announce } = useAnnouncer()

  const pageSize = 30
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('info')
  const [deleteTarget, setDeleteTarget] = useState<PersonaResponse | null>(null)
  const [playgroundSessionId, setPlaygroundSessionId] = useState('')
  const [formModalOpen, setFormModalOpen] = useState(false)
  const [formModalMode, setFormModalMode] = useState<'create' | 'edit'>('create')
  const detailRef = useRef<HTMLElement>(null)

  const { data: personas = [], isLoading, isFetching, error: listError, refetch } = useQuery({
    queryKey: queryKeys.personas.list(),
    queryFn: personasApi.listPersonas,
  })

  const {
    data: selected,
    isLoading: loadingDetail,
    error: detailError,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: queryKeys.personas.detail(selectedId ?? ''),
    queryFn: () => personasApi.getPersona(selectedId!),
    enabled: !!selectedId,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => personasApi.deletePersona(id),
    onSuccess: () => {
      // Authoritative refetch after the grace period commits the delete.
      // The optimistic UI mutation already happened; this just re-syncs in
      // case other clients changed the list during the 5s window.
      void queryClient.invalidateQueries({ queryKey: queryKeys.personas.all() })
    },
    onError: (err, id) => {
      // The optimistic delete already removed the row from the cached list.
      // Restore it so the user can retry, then surface a localized error
      // toast with a one-tap retry hook into the same delete flow.
      void queryClient.invalidateQueries({ queryKey: queryKeys.personas.all() })
      showApiErrorToast(err, {
        onRetry: () => deleteMutation.mutate(id),
      })
    },
  })

  // Inline-rename mutation wired to the DataTable's inline-edit primitive.
  // Validation runs sync inside the editor; the API call below only fires for
  // values that pass `validateName`, so we don't need to duplicate length
  // checks here.
  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      personasApi.updatePersona(id, { name }),
    onSuccess: (saved) => {
      queryClient.setQueryData(queryKeys.personas.detail(saved.id), saved)
      void queryClient.invalidateQueries({ queryKey: queryKeys.personas.list() })
      useToastStore.getState().addToast({ type: 'success', message: t('common.toast.updated') })
      announce(t('common.a11y.updated'))
    },
    onError: (err) => {
      showApiErrorToast(err)
    },
  })

  useEffect(() => {
    if (selected && detailRef.current) {
      const isNarrow = window.innerWidth <= 1280
      if (isNarrow && typeof detailRef.current.scrollIntoView === 'function') {
        detailRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }
    }
  }, [selected])

  const activePersonaCount = personas.filter((persona) => persona.isActive).length

  function openDetail(p: PersonaResponse) {
    if (selectedId === p.id) return
    setSelectedId(p.id)
    setActiveTab('info')
    setPlaygroundSessionId(`playground-${p.id}-${Date.now()}`)
  }

  function handleSaved(saved: PersonaResponse) {
    queryClient.setQueryData(queryKeys.personas.detail(saved.id), saved)
    void queryClient.invalidateQueries({ queryKey: queryKeys.personas.list() })
    setSelectedId(saved.id)
    setFormModalOpen(false)
    useToastStore.getState().addToast({ type: 'success', message: formModalMode === 'create' ? t('common.toast.created') : t('common.toast.updated') })
    announce(formModalMode === 'create' ? t('common.a11y.created') : t('common.a11y.updated'))
  }

  function handleDelete() {
    if (!deleteTarget) return
    const target = deleteTarget
    const listKey = queryKeys.personas.list()

    setDeleteTarget(null)

    // Snapshot the current list so we can both perform the optimistic
    // removal and restore it if the user clicks "실행 취소" within the
    // grace window.
    const snapshot = queryClient.getQueryData<PersonaResponse[]>(listKey)

    scheduleUndoableDelete({
      message: t('personas.deletedNamed', { name: target.name }),
      undoLabel: t('common.undo'),
      undoneMessage: t('common.toast.undone'),
      optimistic: () => {
        if (snapshot) {
          queryClient.setQueryData<PersonaResponse[]>(
            listKey,
            snapshot.filter((p) => p.id !== target.id),
          )
        }
        if (selectedId === target.id) setSelectedId(null)
        // Schedule the live-region announcement on the next macrotask so it
        // wins over the DataTable's row-count announce that fires
        // synchronously when the list shrinks.
        setTimeout(() => announce(t('common.a11y.deleted')), 0)
      },
      restore: () => {
        if (snapshot) {
          queryClient.setQueryData<PersonaResponse[]>(listKey, snapshot)
        } else {
          void queryClient.invalidateQueries({ queryKey: queryKeys.personas.all() })
        }
      },
      commit: () => deleteMutation.mutateAsync(target.id),
    })
  }

  function handleCloseDetail() {
    setSelectedId(null)
  }

  useEscapeKey(!!selectedId && !deleteTarget && !formModalOpen, () => handleCloseDetail())

  // Inline-rename validator. Mirrors the persona schema's name rules so the
  // editor blocks empty / over-long values before the network call fires.
  const validateName = (next: unknown): string | null => {
    if (typeof next !== 'string') return t('common.validation.required')
    const trimmed = next.trim()
    if (trimmed.length === 0) return t('common.validation.required')
    if (trimmed.length > 255) return t('common.validation.maxLength', { max: 255 })
    return null
  }

  const columns: Column<PersonaResponse>[] = [
    {
      key: 'name', header: t('common.name'), width: '40%',
      render: (p: PersonaResponse) => p.name,
      inlineEdit: {
        type: 'text',
        getValue: (p) => p.name,
        ariaLabel: (p) => t('personas.renameName', { name: p.name }),
        validate: validateName,
        onCommit: async (p, next) => {
          const value = String(next).trim()
          if (value === p.name) return
          await renameMutation.mutateAsync({ id: p.id, name: value })
        },
      },
    },
    {
      key: 'updatedAt', header: t('common.updatedAt'), width: '60%',
      render: (p: PersonaResponse) => formatDateTime(p.updatedAt),
    },
  ]

  // Bulk activate/deactivate. The persona API has no batch endpoint, so we
  // fan out single-row updates and aggregate the results into a toast. The
  // default persona is excluded via `rowSelectable` below so it is never
  // touched in bulk.
  const bulkSetActiveMutation = useMutation({
    mutationFn: async ({
      ids,
      isActive,
    }: { ids: string[]; isActive: boolean }) => {
      const results = await Promise.allSettled(
        ids.map(id => personasApi.updatePersona(id, { isActive })),
      )
      const ok = results.filter(r => r.status === 'fulfilled').length
      const failed = results.length - ok
      return { ok, failed }
    },
    onSuccess: (result, variables) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.personas.all() })
      useToastStore.getState().addToast({
        type: result.failed === 0 ? 'success' : 'warning',
        message: t(
          variables.isActive
            ? 'personas.bulk.activateResult'
            : 'personas.bulk.deactivateResult',
          { ok: result.ok, failed: result.failed },
        ),
      })
      announce(t('common.a11y.updated'))
    },
    onError: (err) => {
      showApiErrorToast(err)
    },
  })

  const personaBulkActions: BulkAction<PersonaResponse>[] = [
    {
      id: 'activate',
      label: t('personas.bulk.activate'),
      variant: 'primary',
      perform: async (rows) => {
        await bulkSetActiveMutation.mutateAsync({
          ids: rows.map(r => r.id),
          isActive: true,
        })
      },
    },
    {
      id: 'deactivate',
      label: t('personas.bulk.deactivate'),
      variant: 'secondary',
      perform: async (rows) => {
        await bulkSetActiveMutation.mutateAsync({
          ids: rows.map(r => r.id),
          isActive: false,
        })
      },
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title={t('nav.personas')}
        description={t('nav.help.personas')}
        actions={!isLoading && !listError && personas.length > 0 ? (
          <button
            className="btn btn-primary"
            onClick={() => { setFormModalMode('create'); setFormModalOpen(true) }}
          >
            {t('personas.create')}
          </button>
        ) : undefined}
      />

      {personas.length > 0 && (
        <dl className="personas-summary" aria-label={t('personas.summaryLabel')}>
          <div><dt>{t('personas.totalPersonas')}</dt><dd>{personas.length}</dd></div>
          <div><dt>{t('personas.active')}</dt><dd>{activePersonaCount}</dd></div>
        </dl>
      )}

      {listError ? (
        <WorkspaceUnavailable
          title={t('personas.unavailableTitle')}
          description={t('personas.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('personas.recoveryGuideTitle'),
            steps: [
              t('personas.recoveryCheckAccount'),
              t('personas.recoveryCheckConnection'),
              t('personas.recoveryRetry'),
            ],
            technicalLabel: t('personas.technicalError'),
            technicalDetail: getErrorMessage(listError),
          }}
        />
      ) : (
        <div className={`split-layout ${selectedId ? '' : 'split-layout--collapsed'}`}>
          <div className="split-left">
            {isLoading ? (
              <TableSkeleton />
            ) : personas.length === 0 ? (
              <section className="personas-empty" aria-label={t('personas.empty')}>
                <div className="personas-empty__intro">
                  <h2>{t('personas.empty')}</h2>
                  <p>{t('personas.emptyDescription')}</p>
                  <button className="btn btn-primary" type="button" onClick={() => { setFormModalMode('create'); setFormModalOpen(true) }}>
                    {t('personas.create')}
                  </button>
                </div>
                <div className="personas-empty__guide">
                  <strong>{t('personas.emptyGuideTitle')}</strong>
                  <dl>
                    <div><dt>{t('personas.emptyGuideRoleLabel')}</dt><dd>{t('personas.emptyGuideRole')}</dd></div>
                    <div><dt>{t('personas.emptyGuideToneLabel')}</dt><dd>{t('personas.emptyGuideTone')}</dd></div>
                    <div><dt>{t('personas.emptyGuideSafetyLabel')}</dt><dd>{t('personas.emptyGuideSafety')}</dd></div>
                  </dl>
                </div>
                <details className="personas-empty__example">
                  <summary><ChevronRight className="personas-empty__example-icon" aria-hidden="true" /><span>{t('personas.exampleDisclosure')}</span></summary>
                  <p>{t('personas.emptyExample')}</p>
                </details>
              </section>
            ) : (
              <section className="personas-list" aria-label={t('personas.listLabel')}>
                <p className="personas-list__guidance">
                  {t('personas.listGuidance')}
                </p>
                <div className="detail-note personas-list__count">
                  {t('common.showingCount', { shown: personas.slice((page - 1) * pageSize, page * pageSize).length, total: personas.length })}
                </div>
                <DataTable
                  columns={columns}
                  data={personas.slice((page - 1) * pageSize, page * pageSize)}
                  keyFn={p => p.id}
                  onRowClick={openDetail}
                  selectedKey={selectedId}
                  page={page}
                  pageSize={pageSize}
                  totalCount={personas.length}
                  onPageChange={setPage}
                  selectable
                  bulkActions={personaBulkActions}
                  rowSelectable={(p) => !p.isDefault}
                />
              </section>
            )}
          </div>

          {selectedId ? (
            <div className="split-right">
              {loadingDetail ? (
                <section className="persona-detail" ref={detailRef}><DetailSkeleton /></section>
              ) : null}
              {!loadingDetail && detailError ? (
                <section className="persona-detail persona-detail--unavailable" ref={detailRef} aria-labelledby="persona-detail-unavailable-title">
                  <h2 id="persona-detail-unavailable-title">{t('personas.detailUnavailableTitle')}</h2>
                  <p>{t('personas.detailUnavailableDescription')}</p>
                  <div className="detail-actions">
                    <button className="btn btn-secondary" onClick={() => void refetchDetail()}>{t('common.retry')}</button>
                    <button className="btn btn-secondary" onClick={handleCloseDetail}>{t('personas.chooseAnother')}</button>
                  </div>
                  <details className="persona-technical-details">
                    <summary>{t('personas.technicalError')}</summary>
                    <code>{getErrorMessage(detailError)}</code>
                  </details>
                </section>
              ) : null}
              {!loadingDetail && !detailError && selected ? (
                <section className="persona-detail" ref={detailRef} aria-labelledby="persona-detail-title">
                  <div className="persona-detail__heading">
                    <div>
                      <h2 id="persona-detail-title">{selected.name}</h2>
                      <span className={`persona-state persona-state--${selected.isActive ? 'active' : 'inactive'}`}>
                        <span aria-hidden="true" />{selected.isActive ? t('personas.active') : t('personas.inactive')}
                      </span>
                    </div>
                    <button className="detail-close-btn" onClick={handleCloseDetail} aria-label={t('common.close')}>
                      <X className="persona-detail__close-icon" aria-hidden="true" />
                    </button>
                  </div>
                  <div className="persona-detail__tabs" role="tablist" aria-label={t('personas.tablistLabel')}>
                  <button
                    id="persona-tab-info"
                    className={`tab-btn ${activeTab === 'info' ? 'active' : ''}`}
                    role="tab"
                    type="button"
                    aria-selected={activeTab === 'info'}
                    aria-controls="persona-tabpanel-info"
                    onClick={() => setActiveTab('info')}
                  >
                    {t('personas.tabInfo')}
                  </button>
                  <button
                    id="persona-tab-playground"
                    className={`tab-btn ${activeTab === 'playground' ? 'active' : ''}`}
                    role="tab"
                    type="button"
                    aria-selected={activeTab === 'playground'}
                    aria-controls="persona-tabpanel-playground"
                    onClick={() => setActiveTab('playground')}
                  >
                    {t('personas.tabPlayground')}
                  </button>
                  </div>

                  {activeTab === 'info' ? (
                    <div id="persona-tabpanel-info" role="tabpanel" aria-labelledby="persona-tab-info">
                      <PersonaInfoTab
                        persona={selected}
                        onEdit={() => { setFormModalMode('edit'); setFormModalOpen(true) }}
                        onDelete={() => setDeleteTarget(selected)}
                      />
                    </div>
                  ) : null}
                  {activeTab === 'playground' ? (
                    <div id="persona-tabpanel-playground" role="tabpanel" aria-labelledby="persona-tab-playground">
                      <PersonaPlayground persona={selected} sessionId={playgroundSessionId} />
                    </div>
                  ) : null}
                </section>
              ) : null}
            </div>
          ) : null}
        </div>
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={t('personas.deleteTitle')}
          message={t('personas.deleteConfirm', { name: deleteTarget.name })}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
          danger
        />
      )}

      <PersonaFormModal
        open={formModalOpen}
        onClose={() => setFormModalOpen(false)}
        onSaved={handleSaved}
        persona={formModalMode === 'edit' ? selected : null}
      />
    </div>
  )
}
