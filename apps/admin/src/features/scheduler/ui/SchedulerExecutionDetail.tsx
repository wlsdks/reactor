import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDateTime } from '../../../shared/lib/formatters'
import { formatSchedulerDuration } from '../presenters'
import type { ScheduledJobExecutionResponse } from '../types'

interface SchedulerExecutionDetailProps {
  execution: ScheduledJobExecutionResponse
  onClose: () => void
}

function statusTone(status: string): 'fail' | 'warn' | 'pass' {
  if (status === 'FAILED') return 'fail'
  if (status === 'RUNNING') return 'warn'
  return 'pass'
}

export function SchedulerExecutionDetail({ execution, onClose }: SchedulerExecutionDetailProps) {
  const { t } = useTranslation()
  const statusText = t(`common.statuses.${execution.status}`, { defaultValue: t('common.statuses.WARN') })

  return (
    <section className="scheduler-execution-detail" aria-labelledby="scheduler-execution-detail-title">
      <div className="scheduler-execution-detail__heading">
        <div>
          <h2 id="scheduler-execution-detail-title">{t('scheduler.executionDetail')}</h2>
          <span className={`scheduler-state scheduler-state--${statusTone(execution.status)}`}>
            <span aria-hidden="true" />{statusText}
          </span>
        </div>
        <button className="detail-close-btn" onClick={onClose} aria-label={t('common.close')}>
          <X className="scheduler-detail-close-icon" aria-hidden="true" />
        </button>
      </div>

      <dl className="scheduler-detail-facts">
        <div><dt>{t('scheduler.startedAt')}</dt><dd>{formatDateTime(execution.startedAt)}</dd></div>
        <div><dt>{t('scheduler.completedAt')}</dt><dd>{execution.completedAt ? formatDateTime(execution.completedAt) : '-'}</dd></div>
        <div><dt>{t('scheduler.duration')}</dt><dd>{formatSchedulerDuration(execution.durationMs)}</dd></div>
        <div><dt>{t('scheduler.dryRun')}</dt><dd>{execution.dryRun ? t('common.yes') : t('common.no')}</dd></div>
      </dl>

      <details className="scheduler-technical-details scheduler-execution-detail__technical">
        <summary>{t('scheduler.technicalExecution')}</summary>
        <dl>
          <div><dt>{t('scheduler.executionId')}</dt><dd><code>{execution.id}</code></dd></div>
          {execution.failureReason ? <div><dt>{t('scheduler.failureReason')}</dt><dd>{execution.failureReason}</dd></div> : null}
          <div><dt>{t('scheduler.result')}</dt><dd><pre className="code-block">{execution.result ?? '-'}</pre></dd></div>
        </dl>
      </details>
    </section>
  )
}
