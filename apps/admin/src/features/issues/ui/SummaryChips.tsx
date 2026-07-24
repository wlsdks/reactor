import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import type { IssueCenterSnapshot, IssueSeverity, IssueSource, OperatorIssue } from '../types'

type SourceFilterValue = string | null

interface SummaryChipsProps {
  snapshot: IssueCenterSnapshot
  sourceFilter: SourceFilterValue
  activeSeverity: IssueSeverity | null
  onSeverityChange: (severity: IssueSeverity | null) => void
}

const ALL_SOURCES: IssueSource[] = [
  'integrations', 'mcpServers', 'scheduler', 'approvals',
  'toolPolicy', 'mcpSecurity', 'outputGuard', 'audit',
]

function filterBySource(items: OperatorIssue[], sourceFilter: SourceFilterValue): OperatorIssue[] {
  if (!sourceFilter) return items
  if (sourceFilter === 'atlassian' || sourceFilter === 'swagger') {
    return items.filter((item) => item.source === 'mcpServers' && item.id.includes(sourceFilter))
  }
  return items.filter((item) => item.source === sourceFilter)
}

export function SummaryChips({ snapshot, sourceFilter, activeSeverity, onSeverityChange }: SummaryChipsProps) {
  const { t } = useTranslation()

  const filtered = filterBySource(snapshot.items, sourceFilter)
  const totalCount = filtered.length
  const criticalCount = filtered.filter((i) => i.severity === 'critical').length
  const warningCount = filtered.filter((i) => i.severity === 'warning').length

  const sourcesWithIssues = new Set(snapshot.sources.map((s) => s.source))
  const healthyCount = ALL_SOURCES.filter((s) => !sourcesWithIssues.has(s)).length

  function handleClick(severity: IssueSeverity | null) {
    if (severity === activeSeverity) {
      onSeverityChange(null)
    } else {
      onSeverityChange(severity)
    }
  }

  return (
    <section className="issues-summary" aria-labelledby="issues-summary-title">
      <div className="issues-summary__heading">
        <div>
          <h2 id="issues-summary-title">{t('issuesPage.issueCountHeading')}</h2>
          <p>{t('issuesPage.issueCountDescription')}</p>
        </div>
        {sourceFilter && <span>{t('issuesPage.filteredSource')}</span>}
      </div>
      <div className="issues-summary__controls">
        <div className="summary-chips" role="group" aria-label={t('issuesPage.severityFilterLabel')}>
          <button
            type="button"
            className={`summary-chip${activeSeverity === null ? ' summary-chip--active' : ''}`}
            aria-pressed={activeSeverity === null}
            onClick={() => handleClick(null)}
          >
            <span className="summary-chip-count">{totalCount}</span>
            <span>{t('issuesPage.chips.total')}</span>
          </button>
          <button
            type="button"
            className={`summary-chip summary-chip--critical${activeSeverity === 'critical' ? ' summary-chip--active' : ''}${criticalCount === 0 ? ' summary-chip--disabled' : ''}`}
            aria-pressed={activeSeverity === 'critical'}
            disabled={criticalCount === 0}
            onClick={() => criticalCount > 0 && handleClick('critical')}
          >
            <span className="summary-chip-dot" aria-hidden="true" />
            <span className="summary-chip-count">{criticalCount}</span>
            <span>{t('issuesPage.chips.critical')}</span>
          </button>
          <button
            type="button"
            className={`summary-chip summary-chip--warning${activeSeverity === 'warning' ? ' summary-chip--active' : ''}${warningCount === 0 ? ' summary-chip--disabled' : ''}`}
            aria-pressed={activeSeverity === 'warning'}
            disabled={warningCount === 0}
            onClick={() => warningCount > 0 && handleClick('warning')}
          >
            <span className="summary-chip-dot" aria-hidden="true" />
            <span className="summary-chip-count">{warningCount}</span>
            <span>{t('issuesPage.chips.warning')}</span>
          </button>
        </div>
        {!sourceFilter && (
          <Link className="issues-health-link" to="/health">
            <span className="summary-chip-dot" aria-hidden="true" />
            <span>{t('issuesPage.healthySystems', { count: healthyCount })}</span>
            <span>{t('issuesPage.openHealth')}</span>
            <ArrowRight aria-hidden="true" size={16} />
          </Link>
        )}
      </div>
    </section>
  )
}
