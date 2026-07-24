import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { OperationButton } from '../../../shared/ui'
import { formatDateTime, formatDuration } from '../../../shared/lib/formatters'
import type {
  PromptExperiment,
  PromptExperimentReport,
  PromptExperimentStatus,
  PromptExperimentStatusResponse,
  PromptTrial,
} from '../types'

interface ExperimentDetailProps {
  experiment: PromptExperiment
  experimentStatus: PromptExperimentStatusResponse | null
  trials: PromptTrial[]
  report: PromptExperimentReport | null
  actioning: string | null
  onRun: (experiment: PromptExperiment) => void
  onCancel: (experiment: PromptExperiment) => void
  onActivate: (experiment: PromptExperiment) => void
  onDelete: (experiment: PromptExperiment) => void
  onClose: () => void
}

function statusTone(status: PromptExperimentStatus): 'pass' | 'warn' | 'fail' | 'muted' {
  if (status === 'COMPLETED') return 'pass'
  if (status === 'FAILED') return 'fail'
  if (status === 'RUNNING') return 'warn'
  return 'muted'
}

function trialOutcome(t: ReturnType<typeof useTranslation>['t'], trial: PromptTrial): string {
  return trial.passed ? t('promptLabPage.trialOutcomes.passed') : t('promptLabPage.trialOutcomes.review')
}

function statusLabel(t: ReturnType<typeof useTranslation>['t'], status: PromptExperimentStatus): string {
  switch (status) {
    case 'PENDING': return t('promptLabPage.statuses.waiting')
    case 'RUNNING': return t('promptLabPage.statuses.running')
    case 'COMPLETED': return t('promptLabPage.statuses.completed')
    case 'FAILED': return t('promptLabPage.statuses.needsReview')
    case 'CANCELLED': return t('promptLabPage.statuses.stopped')
  }
}

function queryPreview(query: string): string {
  return query.length > 72 ? `${query.slice(0, 72)}…` : query
}

export function ExperimentDetail({
  experiment,
  experimentStatus,
  trials,
  report,
  actioning,
  onRun,
  onCancel,
  onActivate,
  onDelete,
  onClose,
}: ExperimentDetailProps) {
  const { t } = useTranslation()
  const activeStatus = experimentStatus?.status ?? experiment.status
  const hasRuntimeFailure = activeStatus === 'FAILED' || Boolean(experimentStatus?.errorMessage)

  return (
    <section className="prompt-experiment-detail" aria-labelledby="prompt-experiment-detail-title">
      <div className="prompt-experiment-detail__heading">
        <div>
          <h2 id="prompt-experiment-detail-title">{experiment.name}</h2>
          <span className={`prompt-lab-state prompt-lab-state--${statusTone(activeStatus)}`}>
            <span aria-hidden="true" />{statusLabel(t, activeStatus)}
          </span>
        </div>
        <button className="detail-close-btn" onClick={onClose} aria-label={t('common.close')}>
          <X className="prompt-lab-close-icon" aria-hidden="true" />
        </button>
      </div>

      <p className="prompt-experiment-detail__description">{experiment.description || t('promptLabPage.noDescription')}</p>

      <dl className="prompt-lab-facts">
        <div><dt>{t('promptLabPage.versions')}</dt><dd>{1 + experiment.candidateVersionIds.length}</dd></div>
        <div><dt>{t('promptLabPage.trials')}</dt><dd>{trials.length}</dd></div>
        <div><dt>{t('common.createdAt')}</dt><dd>{formatDateTime(experiment.createdAt)}</dd></div>
        <div><dt>{t('promptLabPage.completed')}</dt><dd>{experiment.completedAt ? formatDateTime(experiment.completedAt) : t('promptLabPage.notCompleted')}</dd></div>
      </dl>

      {hasRuntimeFailure ? (
        <p className="prompt-experiment-detail__attention" role="status">{t('promptLabPage.runtimeAttention')}</p>
      ) : null}

      <div className="detail-actions prompt-experiment-detail__actions">
        <OperationButton
          variant="primary"
          isOperating={actioning === `run-${experiment.id}`}
          disabled={experiment.status !== 'PENDING'}
          onClick={() => onRun(experiment)}
        >
          {t('promptLabPage.run')}
        </OperationButton>
        <OperationButton
          variant="secondary"
          isOperating={actioning === `cancel-${experiment.id}`}
          disabled={experiment.status !== 'RUNNING'}
          onClick={() => onCancel(experiment)}
        >
          {t('common.cancel')}
        </OperationButton>
        <OperationButton
          variant="secondary"
          isOperating={actioning === `activate-${experiment.id}`}
          disabled={!report}
          onClick={() => onActivate(experiment)}
        >
          {t('promptLabPage.activateRecommendation')}
        </OperationButton>
        <OperationButton variant="danger" onClick={() => onDelete(experiment)}>{t('common.delete')}</OperationButton>
      </div>

      <section className="prompt-experiment-detail__section" aria-labelledby="prompt-experiment-trials-title">
        <h3 id="prompt-experiment-trials-title">{t('promptLabPage.trials')}</h3>
        {trials.length > 0 ? (
          <div className="prompt-experiment-trials" role="list">
            {trials.slice(0, 10).map((trial) => (
              <div key={trial.id} className="prompt-experiment-trials__row" role="listitem">
                <p>{queryPreview(trial.query)}</p>
                <span className={`prompt-lab-state prompt-lab-state--${trial.passed ? 'pass' : 'warn'}`}>
                  <span aria-hidden="true" />{trialOutcome(t, trial)}
                </span>
                <span>{trial.score.toFixed(2)}</span>
                <span>{formatDuration(trial.durationMs)}</span>
              </div>
            ))}
          </div>
        ) : <p className="prompt-experiment-detail__empty">{t('promptLabPage.noTrials')}</p>}
      </section>

      <section className="prompt-experiment-detail__section" aria-labelledby="prompt-experiment-report-title">
        <h3 id="prompt-experiment-report-title">{t('promptLabPage.report')}</h3>
        {report ? (
          <>
            <div className="prompt-experiment-comparison" role="list">
              {report.versionSummaries.map((summary) => (
                <div key={summary.versionId} className="prompt-experiment-comparison__row" role="listitem">
                  <div>
                    <strong>{t('promptLabPage.version')} {summary.versionNumber}</strong>
                    <span>{summary.isBaseline ? t('promptLabPage.baselineVersion') : t('promptLabPage.candidateVersion')}</span>
                  </div>
                  <span>{t('promptLabPage.passRate')} {(summary.passRate * 100).toFixed(1)}%</span>
                  <span>{t('promptLabPage.avgScore')} {summary.avgScore.toFixed(2)}</span>
                  <span>{t('promptLabPage.avgDuration')} {formatDuration(summary.avgDurationMs)}</span>
                </div>
              ))}
            </div>
            <div className="prompt-experiment-recommendation">
              <strong>{t('promptLabPage.recommendation')}</strong>
              <p>{report.recommendation.reasoning}</p>
            </div>
          </>
        ) : <p className="prompt-experiment-detail__empty">{t('promptLabPage.noReport')}</p>}
      </section>

      <details className="prompt-lab-technical-details prompt-experiment-detail__technical">
        <summary>{t('promptLabPage.technicalExperiment')}</summary>
        <dl>
          <div><dt>{t('promptLabPage.experimentIdentifier')}</dt><dd><code>{experiment.id}</code></dd></div>
          <div><dt>{t('promptLabPage.templateIdentifier')}</dt><dd><code>{experiment.templateId}</code></dd></div>
          <div><dt>{t('promptLabPage.baselineVersionId')}</dt><dd><code>{experiment.baselineVersionId}</code></dd></div>
          <div><dt>{t('promptLabPage.candidateVersionIds')}</dt><dd><code>{experiment.candidateVersionIds.join(', ')}</code></dd></div>
          <div><dt>{t('promptLabPage.createdBy')}</dt><dd><code>{experiment.createdBy}</code></dd></div>
          {experimentStatus?.errorMessage ? <div><dt>{t('promptLabPage.runtimeError')}</dt><dd><code>{experimentStatus.errorMessage}</code></dd></div> : null}
          <div><dt>{t('promptLabPage.trialRecords')}</dt><dd><pre className="code-block">{JSON.stringify(trials, null, 2)}</pre></dd></div>
          {report ? <div><dt>{t('promptLabPage.reportRecord')}</dt><dd><pre className="code-block">{JSON.stringify(report, null, 2)}</pre></dd></div> : null}
        </dl>
      </details>
    </section>
  )
}
