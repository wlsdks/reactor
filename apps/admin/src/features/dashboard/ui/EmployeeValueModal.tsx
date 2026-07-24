import { useTranslation } from 'react-i18next'
import { DetailModal } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import { buildMissingQueryInspectorHref } from '../../chat-inspector/prefill'
import {
  coverageColor,
  deriveEmployeeValueFocus,
  humanizeAnswerMode,
  humanizeChannel,
  laneCoverageLabel,
  topBucketLabel,
} from '../presenters'
import type { DashboardEmployeeValueSummary } from '../types'

interface EmployeeValueModalProps {
  open: boolean
  onClose: () => void
  employeeValue: DashboardEmployeeValueSummary | undefined
}

export function EmployeeValueModal({ open, onClose, employeeValue }: EmployeeValueModalProps) {
  const { t } = useTranslation()

  if (!employeeValue) return null

  const answerModeEntries = Object.entries(employeeValue.answerModes).sort((a, b) => b[1] - a[1])
  const laneSummaries = employeeValue.lanes
  const topChannels = employeeValue.channels.slice(0, 4)
  const topToolFamilies = employeeValue.toolFamilies.slice(0, 5)
  const topMissingQueries = employeeValue.topMissingQueries
  const focusHints = deriveEmployeeValueFocus(employeeValue)

  return (
    <DetailModal open={open} title={t('dashboard.employeeValueModal.title')} onClose={onClose}>
      {/* Value snapshot */}
      <div className="detail-panel detail-panel--compact">
        <h3 className="detail-section-title">{t('dashboard.employeeValueSnapshot')}</h3>
        <div className="meta-grid" style={{ marginTop: 'var(--space-3)' }}>
          <span>{t('dashboard.observedResponses')}: <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{employeeValue.observedResponses}</span></span>
          <span>{t('dashboard.groundedResponses')}: <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{employeeValue.groundedResponses}</span></span>
          <span>{t('dashboard.groundedCoverage')}: <span style={{ color: coverageColor(employeeValue.groundedRatePercent), fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{employeeValue.groundedRatePercent}%</span></span>
          <span>{t('dashboard.blockedResponses')}: <span style={{ color: employeeValue.blockedResponses > 0 ? 'var(--red)' : 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{employeeValue.blockedResponses}</span></span>
          <span>{t('dashboard.interactiveResponses')}: <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{employeeValue.interactiveResponses}</span></span>
          <span>{t('dashboard.scheduledResponses')}: <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{employeeValue.scheduledResponses}</span></span>
        </div>
        <div className="tag-list" style={{ marginTop: 'var(--space-3)' }}>
          {answerModeEntries.length === 0 ? (
            <span className="tag">{t('dashboard.noValueSignals')}</span>
          ) : (
            answerModeEntries.map(([mode, count]) => (
              <span key={mode} className={`tag tag--${mode.toLowerCase()}`}>
                {humanizeAnswerMode(mode)}: {count}
              </span>
            ))
          )}
        </div>
      </div>

      {/* Recommended focus areas */}
      <div className="detail-panel detail-panel--compact">
        <h3 className="detail-section-title">{t('dashboard.recommendedFocusTitle')}</h3>
        <div className="panel-stack" style={{ marginTop: 'var(--space-3)' }}>
          {focusHints.length === 0 ? (
            <p className="detail-note">{t('dashboard.noRecommendedFocus')}</p>
          ) : (
            focusHints.map((hint, index) => (
              <div key={`${hint.title}-${index}`} className="focus-hint">
                <strong>{hint.title}</strong>
                <p className="detail-note" style={{ marginTop: 'var(--space-2)' }}>{hint.detail}</p>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Lane health table */}
      <div className="detail-panel detail-panel--compact">
        <h3 className="detail-section-title">{t('dashboard.laneHealthTitle')}</h3>
        <div className="table-wrapper" style={{ marginTop: 'var(--space-3)' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">{t('dashboard.lane')}</th>
                <th scope="col">{t('dashboard.observedResponses')}</th>
                <th scope="col">{t('dashboard.groundedResponses')}</th>
                <th scope="col">{t('dashboard.blockedResponses')}</th>
                <th scope="col">{t('dashboard.groundedCoverage')}</th>
              </tr>
            </thead>
            <tbody>
              {laneSummaries.length === 0 ? (
                <tr>
                  <td colSpan={5} className="section-muted-message">{t('dashboard.noValueSignals')}</td>
                </tr>
              ) : (
                laneSummaries.map(lane => (
                  <tr key={lane.answerMode}>
                    <td>{humanizeAnswerMode(lane.answerMode)}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{lane.observedResponses}</td>
                    <td style={{ fontFamily: 'var(--font-mono)' }}>{lane.groundedResponses}</td>
                    <td style={{ color: lane.blockedResponses > 0 ? 'var(--red)' : undefined, fontFamily: 'var(--font-mono)' }}>{lane.blockedResponses}</td>
                    <td style={{ color: coverageColor(lane.groundedRatePercent), fontFamily: 'var(--font-mono)', fontWeight: 'var(--font-weight-strong)' }}>{laneCoverageLabel(lane.groundedRatePercent)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Top channels */}
      <div className="detail-panel detail-panel--compact">
        <h3 className="detail-section-title">{t('dashboard.topChannels')}</h3>
        <div className="tag-list" style={{ marginTop: 'var(--space-3)' }}>
          {topChannels.length === 0 ? (
            <span className="tag">{t('dashboard.noValueSignals')}</span>
          ) : (
            topChannels.map(bucket => (
              <span key={bucket.key} className="tag">{humanizeChannel(bucket.key)}: {bucket.count}</span>
            ))
          )}
        </div>
      </div>

      {/* Top tool families */}
      <div className="detail-panel detail-panel--compact">
        <h3 className="detail-section-title">{t('dashboard.topToolFamilies')}</h3>
        <div className="tag-list" style={{ marginTop: 'var(--space-3)' }}>
          {topToolFamilies.length === 0 ? (
            <span className="tag">{t('dashboard.noValueSignals')}</span>
          ) : (
            topToolFamilies.map(bucket => (
              <span key={bucket.key} className="tag">{topBucketLabel(bucket)}</span>
            ))
          )}
        </div>
      </div>

      {/* Missing queries table */}
      <div className="table-wrapper" style={{ marginTop: 'var(--space-4)' }}>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">{t('dashboard.query')}</th>
              <th scope="col">{t('dashboard.mcpCount')}</th>
              <th scope="col">{t('dashboard.lastSeen')}</th>
              <th scope="col">{t('dashboard.detail')}</th>
              <th scope="col">{t('dashboard.action')}</th>
            </tr>
          </thead>
          <tbody>
            {topMissingQueries.length === 0 ? (
              <tr>
                <td colSpan={5} className="section-muted-message">{t('dashboard.noMissingQueries')}</td>
              </tr>
            ) : (
              topMissingQueries.map(query => (
                <tr key={`${query.queryCluster}-${query.lastOccurredAt}`}>
                  <td>{query.queryLabel}</td>
                  <td style={{ color: query.count > 3 ? 'var(--red)' : undefined, fontFamily: 'var(--font-mono)' }}>{query.count}</td>
                  <td>{formatDateTime(query.lastOccurredAt)}</td>
                  <td>{query.blockReason || query.queryCluster}</td>
                  <td>
                    <button className="btn btn-secondary" onClick={() => { window.location.href = buildMissingQueryInspectorHref(query) }}>
                      {t('dashboard.inspectInChatInspector')}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </DetailModal>
  )
}
