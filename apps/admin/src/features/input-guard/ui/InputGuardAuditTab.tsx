import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  SkeletonTable,
  EmptyState,
  Tooltip,
  WorkspaceUnavailable,
  type Column,
} from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { formatDateCompact } from '../../../shared/lib/formatters'
import * as inputGuardApi from '../api'
import type { InputGuardAudit } from '../api'
import {
  auditActionLabel,
  auditSummaryLabel,
  auditTargetLabel,
  INPUT_GUARD_AUDIT_ACTIONS,
} from '../inputGuardLabels'

/**
 * Input Guard audit log — admin actions + block/warn events.
 *
 * UX rationale:
 * - Localized action labels give non-developers a scannable incident history.
 * - Row limit (50/200/500) for incident vs long-form audits.
 * - Relative time + absolute tooltip (reduced cognitive load).
 */
export function InputGuardAuditTab() {
  const { t } = useTranslation()
  const [limit, setLimit] = useState(200)
  const [actionFilter, setActionFilter] = useState<string>('')

  const auditsQuery = useQuery({
    queryKey: queryKeys.inputGuard.audits({ limit, action: actionFilter || undefined }),
    queryFn: () => inputGuardApi.listInputGuardAudits(limit, actionFilter || undefined),
  })

  const audits = auditsQuery.data?.audits ?? []
  const listError = auditsQuery.error ? getErrorMessage(auditsQuery.error) : null

  const columns: Column<InputGuardAudit>[] = [
    {
      key: 'timestamp',
      header: t('inputGuard.audit.time'),
      width: '12%',
      render: (row) => (
        <Tooltip content={row.timestamp}>
          <span className="ig-num">
            {relativeTime(row.timestamp)}
          </span>
        </Tooltip>
      ),
    },
    {
      key: 'action',
      header: t('auditPage.action'),
      width: '16%',
      render: (row) => <span className="ig-action-summary">{auditActionLabel(t, row.action)}</span>,
    },
    {
      key: 'actor',
      header: t('inputGuard.audit.actor'),
      width: '18%',
      render: (row) => <span className="ig-audit-actor">{row.actor || t('inputGuard.audit.unknownActor')}</span>,
      responsivePriority: 3,
    },
    {
      key: 'resource',
      header: t('inputGuard.audit.resource'),
      width: '18%',
      render: (row) => auditTargetLabel(t, row.action),
      responsivePriority: 2,
    },
    {
      key: 'detail',
      header: t('inputGuard.audit.detail'),
      render: (row) => <span className="ig-rule-name__desc">{auditSummaryLabel(t, row.action)}</span>,
      responsivePriority: 3,
    },
  ]

  return (
    <div>
      {listError ? (
        <WorkspaceUnavailable
          title={t('inputGuard.audit.unavailableTitle')}
          description={t('inputGuard.audit.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={() => auditsQuery.refetch()}
          isRetrying={auditsQuery.isFetching}
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
            <label htmlFor="audit-action-filter" className="ig-toolbar__label">
              {t('inputGuard.audit.actionFilter')}
            </label>
            <select
              id="audit-action-filter"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            >
              <option value="">{t('inputGuard.audit.all')}</option>
              {INPUT_GUARD_AUDIT_ACTIONS.map((action) => (
                <option key={action} value={action}>{auditActionLabel(t, action)}</option>
              ))}
            </select>

            <label htmlFor="audit-limit" className="ig-toolbar__label">
              {t('inputGuard.audit.limit')}
            </label>
            <select
              id="audit-limit"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
            >
              <option value={50}>50</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
            </select>

            <div className="ig-toolbar__spacer" />
            <span className="ig-toolbar__meta">
              {t('inputGuard.audit.resultCount', { count: audits.length })}
            </span>
          </div>

          {auditsQuery.isLoading && <SkeletonTable rows={8} columns={5} />}

          {!auditsQuery.isLoading && audits.length === 0 && (
            <EmptyState
              message={t('inputGuard.audit.emptyTitle')}
              description={t('inputGuard.audit.emptyDesc')}
            />
          )}

          {audits.length > 0 && (
            <div className="ig-table-surface">
              <DataTable<InputGuardAudit>
                data={audits}
                columns={columns}
                keyFn={(row) => row.id}
                tableId="input-guard-audit"
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}

function relativeTime(iso: string): string {
  try {
    const then = new Date(iso).getTime()
    const now = Date.now()
    const diffSec = Math.floor((now - then) / 1000)
    if (diffSec < 60) return `${diffSec}초 전`
    const diffMin = Math.floor(diffSec / 60)
    if (diffMin < 60) return `${diffMin}분 전`
    const diffHr = Math.floor(diffMin / 60)
    if (diffHr < 24) return `${diffHr}시간 전`
    const diffDay = Math.floor(diffHr / 24)
    if (diffDay < 30) return `${diffDay}일 전`
    return formatDateCompact(iso)
  } catch {
    return iso
  }
}
