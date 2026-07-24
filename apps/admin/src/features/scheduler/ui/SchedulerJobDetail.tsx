import { useState } from 'react'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  OperationButton,
  TableSkeleton,
} from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import type { SchedulerAttentionItem } from '../schedulerOps'
import { formatSchedulerDuration, formatSchedulerTimezone } from '../presenters'
import type { ScheduledJobExecutionResponse, ScheduledJobResponse } from '../types'
import { SchedulerExecutionDetail } from './SchedulerExecutionDetail'

interface SchedulerJobDetailProps {
  selected: ScheduledJobResponse
  selectedAttention: SchedulerAttentionItem | null
  executions: ScheduledJobExecutionResponse[]
  selectedExecution: ScheduledJobExecutionResponse | null
  loadingExec: boolean
  executionError: string | null
  actionResult: string | null
  running: string | null
  loadingEdit: boolean
  onClose: () => void
  onTrigger: (id: string) => void
  onDryRun: (id: string) => void
  onEdit: (job: ScheduledJobResponse) => void
  onRequestDelete: (job: ScheduledJobResponse) => void
  onSelectExecution: (execution: ScheduledJobExecutionResponse | null) => void
}

function formatTimeout(value: number | null): string {
  return formatSchedulerDuration(value)
}

function formatLastRun(value: number | null): string {
  return value == null ? '-' : formatDateTime(value)
}

function statusTone(status: string): 'fail' | 'warn' | 'pass' {
  if (status === 'FAILED' || status === 'FAIL') return 'fail'
  if (status === 'RUNNING' || status === 'WARN') return 'warn'
  return 'pass'
}

export function SchedulerJobDetail({
  selected,
  selectedAttention,
  executions,
  selectedExecution,
  loadingExec,
  executionError,
  actionResult,
  running,
  loadingEdit,
  onClose,
  onTrigger,
  onDryRun,
  onEdit,
  onRequestDelete,
  onSelectExecution,
}: SchedulerJobDetailProps) {
  const { t } = useTranslation()
  const [execPage, setExecPage] = useState(1)
  const pageSize = 20
  const statusText = (status: string) => t(`common.statuses.${status}`, { defaultValue: t('common.statuses.WARN') })
  const executionOutcome = (status: string) => {
    switch (status) {
      case 'SUCCESS': return t('scheduler.executionOutcomes.success')
      case 'FAILED': return t('scheduler.executionOutcomes.failed')
      case 'RUNNING': return t('scheduler.executionOutcomes.running')
      case 'SKIPPED': return t('scheduler.executionOutcomes.skipped')
      default: return t('scheduler.executionOutcomes.review')
    }
  }

  const executionColumns = [
    {
      key: 'status',
      header: t('common.status'),
      width: '20%',
      render: (execution: ScheduledJobExecutionResponse) => (
        <span className={`scheduler-state scheduler-state--${statusTone(execution.status)}`}>
          <span aria-hidden="true" />{statusText(execution.status)}
        </span>
      ),
    },
    {
      key: 'dryRun',
      header: t('scheduler.runType'),
      width: '18%',
      render: (execution: ScheduledJobExecutionResponse) => execution.dryRun
        ? t('scheduler.dryRun')
        : t('scheduler.liveRun'),
    },
    {
      key: 'duration',
      header: t('scheduler.duration'),
      width: '20%',
      render: (execution: ScheduledJobExecutionResponse) => formatSchedulerDuration(execution.durationMs),
    },
    {
      key: 'startedAt',
      header: t('scheduler.startedAt'),
      width: '24%',
      render: (execution: ScheduledJobExecutionResponse) => formatDateTime(execution.completedAt ?? execution.startedAt),
    },
    {
      key: 'outcome',
      header: t('scheduler.executionResult'),
      width: '18%',
      render: (execution: ScheduledJobExecutionResponse) => executionOutcome(execution.status),
    },
  ]

  return (
    <section className="scheduler-job-detail" aria-labelledby="scheduler-job-detail-title">
      <div className="scheduler-job-detail__heading">
        <div>
          <h2 id="scheduler-job-detail-title">{selected.name}</h2>
          <span className={`scheduler-state scheduler-state--${selected.enabled ? 'pass' : 'muted'}`}>
            <span aria-hidden="true" />
            {selected.enabled ? t('scheduler.jobState.enabled') : t('scheduler.jobState.paused')}
          </span>
        </div>
        <button className="detail-close-btn" onClick={onClose} aria-label={t('common.close')}>
          <X className="scheduler-detail-close-icon" aria-hidden="true" />
        </button>
      </div>

      {selected.description ? <p className="detail-description">{selected.description}</p> : null}

      <dl className="scheduler-detail-facts">
        <div><dt>{t('scheduler.jobType')}</dt><dd>{t(`scheduler.jobTypes.${selected.jobType}`)}</dd></div>
        <div><dt>{t('scheduler.timezone')}</dt><dd>{formatSchedulerTimezone(selected.timezone)}</dd></div>
        <div><dt>{t('scheduler.retryOnFailure')}</dt><dd>{selected.retryOnFailure ? t('common.yes') : t('common.no')}</dd></div>
        <div><dt>{t('scheduler.maxRetryCount')}</dt><dd>{selected.maxRetryCount}</dd></div>
        <div><dt>{t('scheduler.maximumExecutionTime')}</dt><dd>{formatTimeout(selected.executionTimeoutMs)}</dd></div>
      </dl>

      {selectedAttention ? (
        <section className="scheduler-job-detail__note">
          <h3>{t('scheduler.operatorNoteTitle')}</h3>
          <span className={`scheduler-state scheduler-state--${statusTone(selectedAttention.status)}`}>
            <span aria-hidden="true" />{statusText(selectedAttention.status)}
          </span>
          <p>{t(`scheduler.attentionDetails.${selectedAttention.detailId}`)}</p>
        </section>
      ) : null}

      {selected.lastStatus ? (
        <section className="scheduler-job-detail__recent-run">
          <h3>{t('scheduler.latestRunSummary')}</h3>
          <dl className="scheduler-detail-facts">
            <div><dt>{t('common.status')}</dt><dd>{statusText(selected.lastStatus)}</dd></div>
            <div><dt>{t('scheduler.lastRun')}</dt><dd>{formatLastRun(selected.lastRunAt)}</dd></div>
          </dl>
        </section>
      ) : null}

      <div className="detail-actions scheduler-job-detail__actions">
        <OperationButton
          variant="primary"
          isOperating={running === `trigger-${selected.id}`}
          disabled={running != null && running !== `trigger-${selected.id}`}
          onClick={() => onTrigger(selected.id)}
        >
          {t('scheduler.trigger')}
        </OperationButton>
        <OperationButton
          variant="secondary"
          isOperating={running === `dryrun-${selected.id}`}
          disabled={running != null && running !== `dryrun-${selected.id}`}
          onClick={() => onDryRun(selected.id)}
        >
          {t('scheduler.dryRun')}
        </OperationButton>
        <OperationButton
          variant="secondary"
          isOperating={loadingEdit}
          disabled={running != null}
          onClick={() => onEdit(selected)}
        >
          {t('common.edit')}
        </OperationButton>
        <OperationButton
          variant="danger"
          disabled={running != null || loadingEdit}
          onClick={() => onRequestDelete(selected)}
        >
          {t('common.delete')}
        </OperationButton>
      </div>

      <section className="scheduler-job-detail__executions" aria-labelledby="scheduler-job-executions-title">
        <h3 id="scheduler-job-executions-title">{t('scheduler.executions')}</h3>
        {executionError ? (
          <p className="scheduler-job-detail__connection-note" role="status">
            {executions.length > 0 ? t('scheduler.executionSnapshotWarningPlain') : t('scheduler.executionUnavailablePlain')}
          </p>
        ) : null}
        {loadingExec && executions.length === 0 ? (
          <TableSkeleton />
        ) : executions.length === 0 ? (
          <p className="scheduler-job-detail__empty">{t('scheduler.noExecutions')}</p>
        ) : (
          <DataTable
            columns={executionColumns}
            data={executions.slice((execPage - 1) * pageSize, execPage * pageSize)}
            keyFn={(execution) => execution.id}
            onRowClick={onSelectExecution}
            selectedKey={selectedExecution?.id ?? null}
            page={execPage}
            pageSize={pageSize}
            totalCount={executions.length}
            onPageChange={setExecPage}
          />
        )}
        {selectedExecution ? <SchedulerExecutionDetail execution={selectedExecution} onClose={() => onSelectExecution(null)} /> : null}
      </section>

      <details className="scheduler-technical-details scheduler-job-detail__technical">
        <summary>{t('scheduler.technicalJob')}</summary>
        <dl>
          <div><dt>{t('scheduler.jobId')}</dt><dd><code>{selected.id}</code></dd></div>
          <div><dt>{t('scheduler.cron')}</dt><dd><code>{selected.cronExpression}</code></dd></div>
          {selected.lastFailureReason ? <div><dt>{t('scheduler.failureReason')}</dt><dd>{selected.lastFailureReason}</dd></div> : null}
          {selected.lastResult ? <div><dt>{t('scheduler.result')}</dt><dd><pre className="code-block">{selected.lastResult}</pre></dd></div> : null}
          {selected.jobType === 'AGENT' ? (
            <>
              {selected.agentPrompt ? <div><dt>{t('scheduler.agentPrompt')}</dt><dd><pre className="code-block">{selected.agentPrompt}</pre></dd></div> : null}
              {selected.agentSystemPrompt ? <div><dt>{t('scheduler.agentSystemPrompt')}</dt><dd><pre className="code-block">{selected.agentSystemPrompt}</pre></dd></div> : null}
              <div><dt>{t('scheduler.personaId')}</dt><dd><code>{selected.personaId ?? '-'}</code></dd></div>
              <div><dt>{t('scheduler.agentModel')}</dt><dd><code>{selected.agentModel ?? '-'}</code></dd></div>
              <div><dt>{t('scheduler.maxToolCalls')}</dt><dd>{selected.agentMaxToolCalls ?? '-'}</dd></div>
            </>
          ) : null}
          {selected.jobType === 'MCP_TOOL' ? (
            <>
              <div><dt>{t('scheduler.mcpServer')}</dt><dd><code>{selected.mcpServerName ?? '-'}</code></dd></div>
              <div><dt>{t('scheduler.toolName')}</dt><dd><code>{selected.toolName ?? '-'}</code></dd></div>
              <div><dt>{t('scheduler.toolArguments')}</dt><dd><pre className="code-block">{JSON.stringify(selected.toolArguments, null, 2)}</pre></dd></div>
            </>
          ) : null}
          {actionResult ? <div><dt>{t('scheduler.result')}</dt><dd><pre className="code-block">{actionResult}</pre></dd></div> : null}
          {executionError ? <div><dt>{t('scheduler.executionConnectionDetail')}</dt><dd>{executionError}</dd></div> : null}
        </dl>
      </details>
    </section>
  )
}
