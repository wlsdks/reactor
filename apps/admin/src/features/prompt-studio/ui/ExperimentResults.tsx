import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, ArrowUp, Award } from 'lucide-react'
import { LoadingSpinner } from '../../../shared/ui'
import type { PromptExperimentReport, PromptTrial, PromptVersionSummary } from '../types'

interface ExperimentResultsProps {
  report: PromptExperimentReport
  trials: PromptTrial[]
  onActivateWinner: () => void
  activating?: boolean
}

type SortField = 'score' | 'durationMs'
type SortDirection = 'asc' | 'desc'

const INITIAL_TRIAL_COUNT = 10

function getConfidenceLabel(confidence: string, t: (key: string) => string) {
  const normalizedConfidence = confidence.trim().toLowerCase()
  const translationKey = `promptStudio.confidence.${normalizedConfidence}`
  const translated = t(translationKey)

  return translated === translationKey ? t('promptStudio.confidence.unknown') : translated
}

export function ExperimentResults({ report, trials, onActivateWinner, activating }: ExperimentResultsProps) {
  const { t } = useTranslation()
  const [showAllTrials, setShowAllTrials] = useState(false)
  const [sortField, setSortField] = useState<SortField | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

  const { recommendation, versionSummaries } = report
  const baselineSummary = versionSummaries.find(s => s.isBaseline)

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(prev => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection('desc')
    }
  }

  const sortedTrials = [...trials].sort((a, b) => {
    if (!sortField) return 0
    const multiplier = sortDirection === 'asc' ? 1 : -1
    return (a[sortField] - b[sortField]) * multiplier
  })

  const displayedTrials = showAllTrials ? sortedTrials : sortedTrials.slice(0, INITIAL_TRIAL_COUNT)

  const truncatedReasoning = recommendation.reasoning.length > 200
    ? recommendation.reasoning.slice(0, 200) + '...'
    : recommendation.reasoning

  return (
    <div className="experiment-results">
      {/* Winner Banner */}
      <div className="winner-banner">
        <Award className="winner-icon" size={22} aria-hidden="true" />
        <div className="winner-info">
          <div className="winner-title">
            {t('promptStudio.versionLabel', { version: recommendation.bestVersionNumber })} {t('promptStudio.winner')} · {getConfidenceLabel(recommendation.confidence, t)}
          </div>
          <div className="winner-reason">{truncatedReasoning}</div>
        </div>
        <button
          className="btn btn-primary"
          onClick={onActivateWinner}
          disabled={activating}
        >
          {activating ? <LoadingSpinner size="sm" /> : t('promptStudio.activateVersion', { version: `v${recommendation.bestVersionNumber}` })}
        </button>
      </div>

      {/* Version comparison */}
      <div className="comparison-list" aria-label={t('promptStudio.versionComparison')}>
        {versionSummaries.map(summary => {
          const isWinner = summary.versionId === recommendation.bestVersionId
          const label = summary.isBaseline ? t('promptStudio.baseline') : t('promptStudio.candidate')

          return (
            <section
              key={summary.versionId}
              className={`comparison-row${isWinner ? ' winner' : ''}`}
            >
              <div className="comparison-row-header">
                <strong>{t('promptStudio.versionLabel', { version: summary.versionNumber })}</strong>
                <span>{label}</span>
                {isWinner ? <span className="comparison-recommendation">{t('promptStudio.winner')}</span> : null}
              </div>
              <dl className="comparison-facts">
                <ComparisonFact
                  label={t('promptStudio.passRate')}
                  value={`${summary.passRate}%`}
                  delta={computeDelta(summary, baselineSummary, 'passRate')}
                />
                <ComparisonFact
                  label={t('promptStudio.avgScore')}
                  value={summary.avgScore.toFixed(2)}
                  delta={computeDelta(summary, baselineSummary, 'avgScore')}
                />
                <ComparisonFact
                  label={t('promptStudio.avgDuration')}
                  value={`${(summary.avgDurationMs / 1000).toFixed(1)}s`}
                  delta={computeDurationDelta(summary, baselineSummary)}
                />
                <ComparisonFact
                  label={t('promptStudio.errorRate')}
                  value={`${(summary.errorRate * 100).toFixed(0)}%`}
                  delta={computeErrorDelta(summary, baselineSummary)}
                />
              </dl>
            </section>
          )
        })}
      </div>

      {/* Trial Samples Table */}
      <div className="trial-samples">
        <h4>{t('promptStudio.trialSamples')}</h4>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">{t('promptStudio.query')}</th>
              <th scope="col">{t('promptStudio.version')}</th>
              <th scope="col" aria-sort={sortField === 'score' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>
                <button className="table-sort-button" type="button" onClick={() => handleSort('score')}>
                  {t('promptStudio.score')}
                  {sortField === 'score' ? (sortDirection === 'asc' ? <ArrowUp size={14} aria-hidden="true" /> : <ArrowDown size={14} aria-hidden="true" />) : null}
                </button>
              </th>
              <th scope="col">{t('promptStudio.passed')}</th>
              <th scope="col" aria-sort={sortField === 'durationMs' ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}>
                <button className="table-sort-button" type="button" onClick={() => handleSort('durationMs')}>
                  {t('promptStudio.duration')}
                  {sortField === 'durationMs' ? (sortDirection === 'asc' ? <ArrowUp size={14} aria-hidden="true" /> : <ArrowDown size={14} aria-hidden="true" />) : null}
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {displayedTrials.map(trial => (
              <tr key={trial.id}>
                <td>{trial.query}</td>
                <td>v{trial.promptVersionNumber}</td>
                <td>{trial.score.toFixed(2)}</td>
                <td>{trial.passed ? t('promptStudio.trialPassed') : t('promptStudio.trialNeedsReview')}</td>
                <td>{(trial.durationMs / 1000).toFixed(1)}s</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!showAllTrials && trials.length > INITIAL_TRIAL_COUNT && (
          <button
            className="btn btn-secondary"
            onClick={() => setShowAllTrials(true)}
          >
            {t('promptStudio.showAll')} ({trials.length})
          </button>
        )}
      </div>
    </div>
  )
}

interface ComparisonFactProps {
  label: string
  value: string
  delta: { value: number; positive: boolean } | null
}

function ComparisonFact({ label, value, delta }: ComparisonFactProps) {
  return (
    <div className="comparison-fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {delta !== null && (
        <span className={`comparison-fact__delta ${delta.positive ? 'positive' : 'negative'}`}>
          {delta.positive ? '+' : ''}{delta.value.toFixed(1)}
        </span>
      )}
    </div>
  )
}

function computeDelta(
  summary: PromptVersionSummary,
  baseline: PromptVersionSummary | undefined,
  field: 'passRate' | 'avgScore',
): { value: number; positive: boolean } | null {
  if (!baseline || summary.isBaseline) return null
  const diff = summary[field] - baseline[field]
  return { value: diff, positive: diff >= 0 }
}

function computeDurationDelta(
  summary: PromptVersionSummary,
  baseline: PromptVersionSummary | undefined,
): { value: number; positive: boolean } | null {
  if (!baseline || summary.isBaseline) return null
  const diff = (summary.avgDurationMs - baseline.avgDurationMs) / 1000
  // Lower duration is better, so negative diff is positive
  return { value: diff, positive: diff <= 0 }
}

function computeErrorDelta(
  summary: PromptVersionSummary,
  baseline: PromptVersionSummary | undefined,
): { value: number; positive: boolean } | null {
  if (!baseline || summary.isBaseline) return null
  const diff = (summary.errorRate - baseline.errorRate) * 100
  // Lower error rate is better, so negative diff is positive
  return { value: diff, positive: diff <= 0 }
}
