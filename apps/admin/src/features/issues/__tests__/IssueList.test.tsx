import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, i18n } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { IssueList } from '../ui/IssueList'
import type { OperatorIssue } from '../types'

function makeIssue(overrides: Partial<OperatorIssue>): OperatorIssue {
  return {
    id: 'issue-1',
    severity: 'critical',
    source: 'scheduler',
    title: { key: 'test.title', values: {} },
    summary: { key: 'test.summary' },
    detectedAt: 1710000000000,
    routePath: '/scheduler',
    routeLabelKey: 'nav.scheduler',
    evidence: [],
    ...overrides,
  }
}

const criticalIssue = makeIssue({ id: 'c-1', severity: 'critical', source: 'scheduler', title: { key: 'critical issue' } })
const warningIssue = makeIssue({ id: 'w-1', severity: 'warning', source: 'toolPolicy', title: { key: 'warning issue' } })

describe('IssueList', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'critical issue': 'Critical Issue',
      'warning issue': 'Warning Issue',
      'issuesPage.severityLabels.critical': 'Critical',
      'issuesPage.severityLabels.warning': 'Warning',
      'issuesPage.groupExpand': '+ {{count}} more',
      'issuesPage.empty': 'No issues match the current filters',
      'issuesPage.emptyDescription': 'Clear filters.',
      'nav.scheduler': 'Scheduled Jobs',
      'nav.toolPolicy': 'Tool Policy',
    }, true, true)
  })

  it('renders a Critical group and a Warning group', () => {
    render(
      <IssueList
        items={[criticalIssue, warningIssue]}
        sourceFilter={null}
        severityFilter={null}
      />
    )
    expect(screen.getByText('Critical')).toBeInTheDocument()
    expect(screen.getByText('Warning')).toBeInTheDocument()
  })

  it('shows correct item counts per group', () => {
    render(
      <IssueList
        items={[criticalIssue, warningIssue]}
        sourceFilter={null}
        severityFilter={null}
      />
    )
    expect(screen.getByText('Critical Issue')).toBeInTheDocument()
    expect(screen.getByText('Warning Issue')).toBeInTheDocument()
  })

  it('expands inline detail when item is clicked', async () => {
    const user = userEvent.setup()
    i18n.addResourceBundle('en', 'translation', {
      'test.summary': 'Test summary text',
      'issuesPage.nextSteps.openConsole': 'Open Console',
      'issuesPage.summary': 'Current situation',
      'issuesPage.resolutionPage': 'Resolution page',
      'issuesPage.openRelated': 'Resolve in {{name}}',
    }, true, true)
    render(
      <MemoryRouter>
        <IssueList
          items={[criticalIssue]}
          sourceFilter={null}
          severityFilter={null}
        />
      </MemoryRouter>,
    )
    await user.click(screen.getByText('Critical Issue'))
    // Clicking an issue toggles inline expansion showing summary
    expect(screen.getByText('Test summary text')).toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(1)
  })

  it('keeps one primary resolution link in an expanded issue', async () => {
    const user = userEvent.setup()
    i18n.addResourceBundle('en', 'translation', {
      'test.summary': 'Test summary text',
      'issuesPage.summary': 'Current situation',
      'issuesPage.resolutionPage': 'Resolve in',
      'issuesPage.openRelated': 'Open {{name}}',
      'nav.scheduler': 'Scheduled Jobs',
    }, true, true)
    render(
      <MemoryRouter>
        <IssueList
          items={[criticalIssue]}
          sourceFilter={null}
          severityFilter={null}
        />
      </MemoryRouter>,
    )

    await user.click(screen.getByText('Critical Issue'))
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.getByRole('link', { name: 'Open Scheduled Jobs' })).toHaveAttribute('href', '/scheduler')
  })

  it('shows "+ N more" button when group has more than 5 items', () => {
    const manyWarnings = Array.from({ length: 7 }, (_, i) =>
      makeIssue({ id: `w-${i}`, severity: 'warning', title: { key: `warning ${i}` } })
    )
    i18n.addResourceBundle('en', 'translation', Object.fromEntries(
      manyWarnings.map((_, i) => [`warning ${i}`, `Warning ${i}`])
    ), true, true)

    render(
      <IssueList
        items={manyWarnings}
        sourceFilter={null}
        severityFilter={null}
      />
    )
    expect(screen.getByText('+ 2 more')).toBeInTheDocument()
  })

  it('expands "N more" items when the expand button is clicked', async () => {
    const user = userEvent.setup()
    const manyWarnings = Array.from({ length: 7 }, (_, i) =>
      makeIssue({ id: `w-${i}`, severity: 'warning', title: { key: `warning ${i}` } })
    )
    i18n.addResourceBundle('en', 'translation', Object.fromEntries(
      manyWarnings.map((_, i) => [`warning ${i}`, `Warning ${i}`])
    ), true, true)

    render(
      <IssueList
        items={manyWarnings}
        sourceFilter={null}
        severityFilter={null}
      />
    )
    await user.click(screen.getByText('+ 2 more'))
    expect(screen.getByText('Warning 5')).toBeInTheDocument()
    expect(screen.getByText('Warning 6')).toBeInTheDocument()
  })

  it('hides Critical group when severityFilter is "warning"', () => {
    render(
      <IssueList
        items={[criticalIssue, warningIssue]}
        sourceFilter={null}
        severityFilter="warning"
      />
    )
    expect(screen.queryByText('Critical Issue')).not.toBeInTheDocument()
    expect(screen.getByText('Warning Issue')).toBeInTheDocument()
  })

  it('filters by source when sourceFilter is set', () => {
    render(
      <IssueList
        items={[criticalIssue, warningIssue]}
        sourceFilter="scheduler"
        severityFilter={null}
      />
    )
    expect(screen.getByText('Critical Issue')).toBeInTheDocument()
    expect(screen.queryByText('Warning Issue')).not.toBeInTheDocument()
  })

  it('shows healthy state when source filter has no issues', () => {
    i18n.addResourceBundle('en', 'translation', {
      'issuesPage.healthy': 'All systems healthy',
      'issuesPage.healthyDescription': 'No issues found for this source.',
    }, true, true)
    render(
      <IssueList
        items={[criticalIssue]}
        sourceFilter="audit"
        severityFilter={null}
      />
    )
    // Source filter with no matching items shows healthy state
    expect(screen.getByText('All systems healthy')).toBeInTheDocument()
  })

  it('shows empty state when severity filter has no matches', () => {
    render(
      <IssueList
        items={[criticalIssue]}
        sourceFilter={null}
        severityFilter="warning"
      />
    )
    expect(screen.getByText('No issues match the current filters')).toBeInTheDocument()
  })
})
