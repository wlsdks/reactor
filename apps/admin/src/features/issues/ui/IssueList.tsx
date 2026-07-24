import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowUpRight, ChevronDown, ChevronRight } from 'lucide-react'
import { EmptyState } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import type { IssueSeverity, IssueSource, OperatorIssue } from '../types'

type SourceFilterValue = string | null

interface IssueListProps {
  items: OperatorIssue[]
  sourceFilter: SourceFilterValue
  severityFilter: IssueSeverity | null
}

const GROUP_PAGE_SIZE = 5

function sourceLabelKey(source: IssueSource): string {
  switch (source) {
    case 'integrations': return 'nav.integrations'
    case 'mcpServers': return 'nav.mcpServers'
    case 'scheduler': return 'nav.scheduler'
    case 'approvals': return 'nav.approvals'
    case 'toolPolicy': return 'nav.toolPolicy'
    case 'mcpSecurity': return 'nav.mcpSecurity'
    case 'outputGuard': return 'nav.outputGuard'
    case 'audit': return 'nav.audit'
  }
}

function applySourceFilter(items: OperatorIssue[], sourceFilter: SourceFilterValue): OperatorIssue[] {
  if (!sourceFilter) return items
  if (sourceFilter === 'atlassian' || sourceFilter === 'swagger') {
    return items.filter((item) => item.source === 'mcpServers' && item.id.includes(sourceFilter))
  }
  return items.filter((item) => item.source === sourceFilter)
}

function InlineDetail({ issue }: { issue: OperatorIssue }) {
  const { t } = useTranslation()

  return (
    <div className="issue-inline-detail">
      <div className="issue-inline-summary">
        <span>{t('issuesPage.summary')}</span>
        <p>{t(issue.summary.key, issue.summary.values)}</p>
      </div>
      {issue.evidence.length > 0 && (
        <details className="issue-evidence">
          <summary>{t('issuesPage.technicalDetails')}</summary>
          <code>
          {issue.evidence.map((line, i) => (
            <span key={i}>{line}{'\n'}</span>
          ))}
          </code>
        </details>
      )}
      <div className="issue-inline-actions">
        <span>{t('issuesPage.resolutionPage')}</span>
        <Link className="issue-action-link" to={issue.routePath}>
          {t('issuesPage.openRelated', { name: t(issue.routeLabelKey) })}
          <ArrowUpRight aria-hidden="true" size={15} />
        </Link>
      </div>
    </div>
  )
}

interface IssueGroupProps {
  severity: IssueSeverity
  items: OperatorIssue[]
  expandedId: string | null
  onToggle: (id: string) => void
}

function IssueGroup({ severity, items, expandedId, onToggle }: IssueGroupProps) {
  const { t } = useTranslation()
  const [showAll, setShowAll] = useState(false)
  const visibleItems = showAll ? items : items.slice(0, GROUP_PAGE_SIZE)
  const remaining = items.length - GROUP_PAGE_SIZE

  return (
    <section className={`issue-group issue-group--${severity}`}>
      <div className="issue-group-header">
        <div>
          <span className="issue-group-dot" aria-hidden="true" />
          <h3>{t(`issuesPage.severityLabels.${severity}`)}</h3>
        </div>
        <span className="issue-group-count">{items.length}</span>
      </div>
      {visibleItems.map((issue) => {
        const isExpanded = expandedId === issue.id
        return (
          <div key={issue.id}>
            <button
              type="button"
              className={`issue-item${isExpanded ? ' issue-item--expanded' : ''}`}
              onClick={() => onToggle(issue.id)}
              aria-expanded={isExpanded}
            >
              <span className="issue-item__status-dot" aria-hidden="true" />
              <div className="issue-item__copy">
                <div className="issue-item-title">{t(issue.title.key, issue.title.values)}</div>
                <div className="issue-item-meta">
                  {t(sourceLabelKey(issue.source))}
                  {issue.detectedAt ? ` · ${formatDateTime(issue.detectedAt)}` : ''}
                </div>
              </div>
              {isExpanded ? <ChevronDown className="issue-item-arrow" aria-hidden="true" size={18} /> : <ChevronRight className="issue-item-arrow" aria-hidden="true" size={18} />}
            </button>
            {isExpanded && <InlineDetail issue={issue} />}
          </div>
        )
      })}
      {!showAll && remaining > 0 && (
        <button type="button" className="issue-group-expand" onClick={() => setShowAll(true)}>
          {t('issuesPage.groupExpand', { count: remaining })}
        </button>
      )}
    </section>
  )
}

export function IssueList({ items, sourceFilter, severityFilter }: IssueListProps) {
  const { t } = useTranslation()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const filterKey = `${sourceFilter ?? 'all'}-${severityFilter ?? 'all'}`

  const filtered = applySourceFilter(items, sourceFilter).filter(
    (item) => !severityFilter || item.severity === severityFilter,
  )

  const criticalItems = filtered.filter((item) => item.severity === 'critical')
  const warningItems = filtered.filter((item) => item.severity === 'warning')

  function handleToggle(id: string) {
    setExpandedId(expandedId === id ? null : id)
  }

  if (filtered.length === 0) {
    if (sourceFilter && !severityFilter) {
      return (
        <EmptyState
          message={t('issuesPage.healthy')}
          description={t('issuesPage.healthyDescription')}
        />
      )
    }
    return (
      <EmptyState
        message={t('issuesPage.empty')}
        description={t('issuesPage.emptyDescription')}
      />
    )
  }

  return (
    <section className="issue-list" aria-label={t('issuesPage.issueListLabel')}>
      {criticalItems.length > 0 && (
        <IssueGroup
          key={`critical-${filterKey}`}
          severity="critical"
          items={criticalItems}
          expandedId={expandedId}
          onToggle={handleToggle}
        />
      )}
      {warningItems.length > 0 && (
        <IssueGroup
          key={`warning-${filterKey}`}
          severity="warning"
          items={warningItems}
          expandedId={expandedId}
          onToggle={handleToggle}
        />
      )}
    </section>
  )
}
