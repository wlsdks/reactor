import { useTranslation } from 'react-i18next'
import { formatDateTime } from '../../../shared/lib/formatters'
import type { ScheduledJobResponse } from '../types'
import type { SchedulerAttentionItem, SchedulerOpsSummary, SchedulerSignal } from '../schedulerOps'

// ── Helpers ────────────────────────────────────────────────────────────────

function formatLastRun(value: number | null): string {
  return value == null ? '-' : formatDateTime(value)
}

// ── Props ──────────────────────────────────────────────────────────────────

interface SchedulerOpsPanelProps {
  opsSummary: SchedulerOpsSummary
  onOpenDetail: (job: ScheduledJobResponse) => void
}

// ── Component ──────────────────────────────────────────────────────────────

export function SchedulerOpsPanel({ opsSummary, onOpenDetail }: SchedulerOpsPanelProps) {
  const { t } = useTranslation()

  function describeSignal(signal: SchedulerSignal): string {
    return t(`scheduler.signalDetails.${signal.detailId}`, {
      count: signal.meta?.count ?? 0,
      total: signal.meta?.total ?? 0,
    })
  }

  function describeAttention(item: SchedulerAttentionItem): string {
    return t(`scheduler.attentionDetails.${item.detailId}`)
  }

  return (
    <>
      <section className="scheduler-ops" aria-labelledby="scheduler-ops-title">
        <div className="detail-section-header">
          <h2 id="scheduler-ops-title" className="section-title">{t('scheduler.opsTitle')}</h2>
          <span className={`scheduler-state scheduler-state--${opsSummary.status.toLowerCase()}`}>
            <span aria-hidden="true" />
            {t(`common.statuses.${opsSummary.status}`)}
          </span>
        </div>
        <p className="detail-note">{t('scheduler.opsDescription')}</p>
        <dl className="scheduler-ops__facts">
          <div><dt>{t('scheduler.totalJobsCard')}</dt><dd>{opsSummary.totalJobs}</dd></div>
          <div><dt>{t('scheduler.enabledJobsCard')}</dt><dd>{opsSummary.enabledJobs}</dd></div>
          <div><dt>{t('scheduler.attentionJobsCard')}</dt><dd>{opsSummary.attentionJobs}</dd></div>
          <div><dt>{t('scheduler.failedJobsCard')}</dt><dd>{opsSummary.failedJobs}</dd></div>
        </dl>
        <details className="scheduler-checks">
          <summary>
            <span>{t('scheduler.checksSummary')}</span>
            <span>{t('scheduler.checksCount', { count: opsSummary.signals.length })}</span>
          </summary>
          <ul>
            {opsSummary.signals.map((signal) => (
              <li key={signal.id}>
                <span className={`scheduler-state scheduler-state--${signal.status.toLowerCase()}`}>
                  <span aria-hidden="true" />
                  {t(`common.statuses.${signal.status}`)}
                </span>
                <strong>{t(`scheduler.signals.${signal.id}`)}</strong>
                <p>{describeSignal(signal)}</p>
              </li>
            ))}
          </ul>
        </details>
      </section>

      <section className="scheduler-attention" aria-labelledby="scheduler-attention-title">
        <div className="detail-section-header">
          <h2 id="scheduler-attention-title" className="section-title">{t('scheduler.attentionTitle')}</h2>
          {opsSummary.attentionItems.length > 0 && (
            <span className="scheduler-attention-count">
              {t('scheduler.attentionCount', { count: opsSummary.attentionItems.length })}
            </span>
          )}
        </div>
        <p className="detail-note">{t('scheduler.attentionDescription')}</p>
        {opsSummary.attentionItems.length === 0 ? (
          <div className="scheduler-attention__empty">
            <strong>{t('scheduler.attentionEmpty')}</strong>
            <span>{t('scheduler.attentionHealthy')}</span>
          </div>
        ) : (
          <ul className="scheduler-attention__list">
            {opsSummary.attentionItems.map((item) => (
              <li key={item.id}>
                <div className="scheduler-attention__heading">
                  <strong>{item.job.name}</strong>
                  <span className={`scheduler-state scheduler-state--${item.status.toLowerCase()}`}>
                    <span aria-hidden="true" />
                    {t(`common.statuses.${item.status}`)}
                  </span>
                  <button className="btn btn-secondary btn-sm" onClick={() => { onOpenDetail(item.job) }}>
                    {t('scheduler.openJobDetail')}
                  </button>
                </div>
                <p>{describeAttention(item)}</p>
                <div className="scheduler-attention__meta">
                  <span>{t('scheduler.jobType')}: {t(`scheduler.jobTypes.${item.job.jobType}`)}</span>
                  <span>{t('common.status')}: {item.job.lastStatus ? t(`common.statuses.${item.job.lastStatus}`, { defaultValue: t('common.statuses.WARN') }) : t('scheduler.noExecutionYet')}</span>
                  <span>{t('scheduler.lastRun')}: {formatLastRun(item.job.lastRunAt)}</span>
                  <span>{t('scheduler.retryOnFailure')}: {item.job.retryOnFailure ? t('common.yes') : t('common.no')}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

    </>
  )
}
