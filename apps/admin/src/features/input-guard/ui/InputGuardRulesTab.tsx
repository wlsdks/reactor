import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  DetailModal,
  SkeletonText,
  SkeletonTable,
  EmptyState,
  ConfirmDialog,
  WorkspaceUnavailable,
  useAnnouncer,
  type Column,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import * as inputGuardApi from '../api'
import type { InputGuardRule } from '../api'
import { ruleActionLabel } from '../inputGuardLabels'
import { InputGuardRuleModal } from './InputGuardRuleModal'

/**
 * Input Guard custom rules — list + CRUD with modal editor.
 *
 * UX rationale:
 * - DataTable for consistency with other admin feature tables.
 * - A single review action keeps table scanning focused; edits and deletion live
 *   in the selected rule detail rather than becoming a per-row action cluster.
 * - Rule behavior is described in Korean. Pattern, category, and identifier
 *   remain in the detail's technical disclosure for specialist review.
 */
export function InputGuardRulesTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const { announce } = useAnnouncer()

  const [editingRule, setEditingRule] = useState<InputGuardRule | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<InputGuardRule | null>(null)
  const [detailRuleId, setDetailRuleId] = useState<string | null>(null)

  const rulesQuery = useQuery({
    queryKey: queryKeys.inputGuard.rules(),
    queryFn: inputGuardApi.listInputGuardRules,
  })

  const detailQuery = useQuery({
    queryKey: queryKeys.inputGuard.rule(detailRuleId ?? ''),
    queryFn: () => inputGuardApi.getInputGuardRule(detailRuleId!),
    enabled: detailRuleId !== null,
  })

  const rules = rulesQuery.data?.rules ?? []
  const listError = rulesQuery.error ? getErrorMessage(rulesQuery.error) : null

  const deleteMutation = useMutation({
    mutationFn: (id: string) => inputGuardApi.deleteInputGuardRule(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.inputGuard.rules() })
      addToast({ type: 'success', message: t('inputGuard.rules.deleted') })
      announce(t('common.a11y.deleted'))
      setDeleteTarget(null)
    },
    onError: (err: Error) => {
      const msg = getErrorMessage(err)
      addToast({ type: 'error', message: msg })
      announce(msg, { priority: 'assertive' })
    },
  })

  function openCreate() {
    setEditingRule(null)
    setModalOpen(true)
  }

  function openDetail(rule: InputGuardRule) {
    setDetailRuleId(rule.id)
  }

  function closeDetail() {
    setDetailRuleId(null)
  }

  const columns: Column<InputGuardRule>[] = [
    {
      key: 'name',
      header: t('inputGuard.rules.colName'),
      width: '26%',
      render: (row) => (
        <div className="ig-rule-name">
          <span className="ig-rule-name__primary">{row.name}</span>
          {row.description && <span className="ig-rule-name__desc">{row.description}</span>}
        </div>
      ),
    },
    {
      key: 'action',
      header: t('inputGuard.rules.colAction'),
      width: '16%',
      render: (row) => <span className="ig-action-summary">{ruleActionLabel(t, row.action)}</span>,
    },
    {
      key: 'description',
      header: t('inputGuard.rules.colDescription'),
      render: (row) => (
        <span className={row.description ? 'ig-rule-name__desc' : 'ig-rule-name__empty'}>
          {row.description || t('inputGuard.rules.descriptionEmpty')}
        </span>
      ),
      responsivePriority: 3,
    },
    {
      key: 'priority',
      header: t('inputGuard.rules.colPriority'),
      width: '8%',
      render: (row) => <span className="ig-num">{row.priority}</span>,
      responsivePriority: 3,
    },
    {
      key: 'enabled',
      header: t('inputGuard.rules.colStatus'),
      width: '12%',
      render: (row) => (
        <span className={`ig-rule-state is-${row.enabled ? 'active' : 'paused'}`}>
          <span aria-hidden="true" />
          {row.enabled ? t('inputGuard.rules.statusEnabled') : t('inputGuard.rules.statusPaused')}
        </span>
      ),
      responsivePriority: 2,
    },
    {
      key: 'review',
      header: t('inputGuard.rules.colReview'),
      width: '12%',
      render: (row) => (
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          aria-label={t('inputGuard.rules.reviewAriaLabel', { name: row.name })}
          onClick={() => openDetail(row)}
        >
          {t('inputGuard.rules.review')}
        </button>
      ),
    },
  ]

  return (
    <div>
      {listError ? (
        <WorkspaceUnavailable
          title={t('inputGuard.rules.unavailableTitle')}
          description={t('inputGuard.rules.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={() => rulesQuery.refetch()}
          isRetrying={rulesQuery.isFetching}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('inputGuard.recoveryTitle'),
            steps: [t('inputGuard.recoveryAccount'), t('inputGuard.recoveryConnection')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: listError,
          }}
        />
      ) : (
        <>
          <div className="ig-toolbar">
            <span className="ig-rules-desc">{t('inputGuard.rules.description')}</span>
            <span className="ig-toolbar__meta">
              {t('inputGuard.rules.total', { count: rules.length })}
            </span>
            {rules.length > 0 ? (
              <button type="button" className="btn btn-primary" onClick={openCreate}>
                {t('inputGuard.rules.addNew')}
              </button>
            ) : null}
          </div>

          {rulesQuery.isLoading && <SkeletonTable rows={6} columns={5} />}

          {!rulesQuery.isLoading && rules.length === 0 && (
            <EmptyState
              message={t('inputGuard.rules.emptyTitle')}
              description={t('inputGuard.rules.emptyDesc')}
              actionLabel={t('inputGuard.rules.addNew')}
              onAction={openCreate}
            />
          )}

          {rules.length > 0 && (
            <div className="ig-table-surface">
              <DataTable<InputGuardRule>
                data={rules}
                columns={columns}
                keyFn={(row) => row.id}
                tableId="input-guard-rules"
                rowClassName={(row) => (row.enabled ? undefined : 'ig-rule-row--disabled')}
              />
            </div>
          )}
        </>
      )}

      {modalOpen && (
        <InputGuardRuleModal
          key={editingRule?.id ?? 'create'}
          open={modalOpen}
          rule={editingRule}
          onClose={() => {
            setModalOpen(false)
            setEditingRule(null)
          }}
        />
      )}

      {detailRuleId !== null && detailQuery.isPending && (
        <DetailModal
          open
          title={t('inputGuard.rules.detailLoading')}
          onClose={closeDetail}
        >
          <SkeletonText lines={6} />
        </DetailModal>
      )}

      {detailRuleId !== null && detailQuery.isError && (
        <DetailModal
          open
          title={t('inputGuard.rules.detailErrorTitle')}
          onClose={closeDetail}
        >
          <p>{t('inputGuard.rules.detailNotFound')}</p>
          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={closeDetail}>
              {t('common.close')}
            </button>
          </div>
        </DetailModal>
      )}

      {detailRuleId !== null && detailQuery.isSuccess && detailQuery.data && (
        <InputGuardRuleModal
          key={`detail-${detailQuery.data.id}`}
          open
          mode="read"
          rule={detailQuery.data}
          onClose={closeDetail}
          onDelete={() => {
            setDeleteTarget(detailQuery.data)
            closeDetail()
          }}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={t('inputGuard.rules.delete')}
          message={t('inputGuard.rules.confirmDelete', { name: deleteTarget.name })}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
          onCancel={() => setDeleteTarget(null)}
          danger
        />
      )}
    </div>
  )
}
