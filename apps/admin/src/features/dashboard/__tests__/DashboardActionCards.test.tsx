import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { i18n, render, screen, within } from '../../../test/utils'
import type { IssueCenterSnapshot } from '../../issues'
import { DashboardActionCards } from '../ui/DashboardActionCards'

const issueSnapshot = {
  criticalCount: 2,
  items: [
    {
      id: 'approval-1',
      severity: 'critical',
      title: { key: 'issuesPage.titles.approvalRequest', values: { tool: 'deploy' } },
    },
  ],
} as unknown as IssueCenterSnapshot

describe('DashboardActionCards', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'dashboard.actions.priorityTitle': 'Work requiring attention',
      'dashboard.actions.prioritySummary': '{{count}} operator signals are waiting for review.',
      'dashboard.actions.criticalIssues': 'Critical issues',
      'dashboard.actions.pendingApprovals': 'Pending approvals',
      'dashboard.actions.outputGuard': 'Response filter',
      'dashboard.actions.viewAll': 'View all',
      'dashboard.actions.guardRejected': '{{count}} rejected',
      'dashboard.actions.guardModified': '{{count}} modified',
      'issuesPage.titles.approvalRequest': 'Approval request: {{tool}}',
    }, true, true)
  })

  it('presents outstanding signals as one action-first section', () => {
    render(
      <MemoryRouter>
        <DashboardActionCards
          issueSnapshot={issueSnapshot}
          pendingApprovals={3}
          guardRejected={1}
          guardModified={2}
        />
      </MemoryRouter>,
    )

    const section = screen.getByRole('region', { name: 'Work requiring attention' })
    expect(within(section).getByText('8 operator signals are waiting for review.')).toBeInTheDocument()
    expect(within(section).getByText('1 rejected')).toBeInTheDocument()
    expect(within(section).getByText('2 modified')).toBeInTheDocument()
    const links = within(section).getAllByRole('link')
    expect(links).toHaveLength(3)
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/issues',
      '/approvals',
      '/safety-rules',
    ])
    expect(section.querySelectorAll('.action-card')).toHaveLength(0)
  })

  it('omits clear categories from the active work queue', () => {
    render(
      <MemoryRouter>
        <DashboardActionCards
          issueSnapshot={issueSnapshot}
          pendingApprovals={0}
          guardRejected={0}
          guardModified={0}
        />
      </MemoryRouter>,
    )

    const section = screen.getByRole('region', { name: 'Work requiring attention' })
    expect(within(section).getAllByRole('link')).toHaveLength(1)
    expect(within(section).queryByText('Pending approvals')).not.toBeInTheDocument()
    expect(within(section).queryByText('Response filter')).not.toBeInTheDocument()
  })
})
