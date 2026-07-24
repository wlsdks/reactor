import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { CopyButton, OverlayCloseButton } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { deriveAuditEntryInsight } from '../auditOps'
import type { AuditLogEntry } from '../types'
import { useAuditLabelLocalizers } from './auditLabels'

interface AuditDetailPanelProps {
  effectiveSelected: AuditLogEntry
  onClose: () => void
  onRollbackTarget: (row: AuditLogEntry) => void
}

export function AuditDetailPanel({ effectiveSelected, onClose, onRollbackTarget }: AuditDetailPanelProps) {
  const { t } = useTranslation()
  const { localizeCategory, localizeAction, localizeRollbackReadiness, localizeResource } = useAuditLabelLocalizers()
  const insight = deriveAuditEntryInsight(effectiveSelected)

  return (
    <aside className="audit-detail" aria-labelledby="audit-detail-title">
      <div className="audit-detail-header">
        <div>
          <p>{localizeAction(effectiveSelected.action)}</p>
          <h2 id="audit-detail-title">{localizeCategory(effectiveSelected.category)}</h2>
        </div>
        <OverlayCloseButton onClick={onClose} label={t('common.close')} />
      </div>

      <div className="audit-detail-status" data-ready={insight.rollbackReady}>
        <span>{t('auditPage.recoveryStatus')}</span>
        <strong>{localizeRollbackReadiness(insight.rollbackReady ? 'READY' : 'WARN')}</strong>
      </div>

      <dl className="audit-detail-facts">
        <div>
          <dt>{t('auditPage.recordId')}</dt>
          <dd><CopyButton value={effectiveSelected.id} label={t('auditPage.recordId')} variant="icon-text" /></dd>
        </div>
        <div><dt>{t('auditPage.actor')}</dt><dd>{effectiveSelected.actorEmail ?? effectiveSelected.actor}</dd></div>
        <div><dt>{t('auditPage.created')}</dt><dd>{formatDateTime(effectiveSelected.createdAt)}</dd></div>
        <div>
          <dt>{t('auditPage.resource')}</dt>
          <dd className="audit-detail-resource">
            <span>{localizeResource(effectiveSelected)}</span>
            {effectiveSelected.resourceId && <CopyButton value={effectiveSelected.resourceId} label={t('auditPage.resource')} />}
          </dd>
        </div>
        <div><dt>{t('auditPage.detailCoverage')}</dt><dd>{insight.hasDetail ? t('auditPage.detailAvailable') : t('auditPage.detailUnavailable')}</dd></div>
      </dl>

      <div className="audit-detail-guidance">
        {insight.rollbackReady ? t('auditPage.rollbackReadyHelp') : insight.highRisk ? t('auditPage.rollbackManualHelp') : t('auditPage.reviewHelp')}
      </div>

      <div className="audit-detail-actions">
        <Link className="btn btn-secondary" to={insight.recoveryRoute.path}>{t('auditPage.openRecoveryConsole')}</Link>
        {insight.rollbackReady && <button type="button" className="btn btn-danger" onClick={() => onRollbackTarget(effectiveSelected)}>{t('auditPage.rollback.buttonLabel')}</button>}
      </div>

      {insight.detail.changeKeys.length > 0 && (
        <div className="audit-changed-fields">
          <h3>{t('auditPage.changedFields')}</h3>
          <p>{t('auditPage.changedFieldCount', { count: insight.detail.changeKeys.length })}</p>
        </div>
      )}

      <details className="audit-technical-detail">
        <summary>{t('auditPage.detail')}</summary>
        <pre>{insight.detail.formatted || t('auditPage.noDetail')}</pre>
      </details>
    </aside>
  )
}
