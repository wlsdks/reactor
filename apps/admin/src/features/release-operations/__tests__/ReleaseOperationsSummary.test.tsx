import { MemoryRouter } from 'react-router-dom'
import { i18n, render, screen } from '../../../test/utils'
import { RELEASE_WORKFLOW_PATHS_BY_ID } from '../../../shared/releaseWorkflow'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'
import { ReleaseOperationsSummary } from '../ui/ReleaseOperationsSummary'

describe('ReleaseOperationsSummary', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'releaseOperations.dashboardSummary.title': 'Release operations',
      'releaseOperations.dashboardSummary.description': 'Open the workspace for evidence.',
      'releaseOperations.dashboardSummary.gates': 'Passed reports',
      'releaseOperations.dashboardSummary.blockers': 'Blockers',
      'releaseOperations.dashboardSummary.warnings': 'Warnings',
      'releaseOperations.dashboardSummary.open': 'Open release operations',
      'dashboard.release.recommendedTag': 'Recommended tag',
      'dashboard.release.noTag': 'Undecided',
      'dashboard.release.status.eligible_with_warnings': 'Warning review required',
      'dashboard.release.status.missing': 'Not connected',
    }, true, true)
  })

  it('compresses readiness evidence into a dashboard handoff', () => {
    const readiness: DashboardReleaseReadinessSummary = {
      status: 'eligible_with_warnings',
      requiredReports: ['smoke_run', 'release_evidence', 'hardening_suite', 'langsmith_eval_sync'],
      blockingReports: [],
      warningReports: ['hardening_suite'],
      tagRecommendation: {
        recommendedTag: 'v1.2.0',
        passedReports: ['smoke_run', 'release_evidence', 'hardening_suite', 'langsmith_eval_sync'],
      },
    }

    const { container } = render(
      <MemoryRouter>
        <ReleaseOperationsSummary readiness={readiness} />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Release operations' })).toBeInTheDocument()
    expect(screen.getByText('4/4')).toBeInTheDocument()
    expect(screen.getByText('v1.2.0')).toBeInTheDocument()
    expect(screen.getByText('Warning review required')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Open release operations/ })).toHaveAttribute(
      'href',
      RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
    )
    expect(container.querySelectorAll('.status-badge')).toHaveLength(0)
    expect(container.querySelector('.release-operations-summary__status')).toBeInTheDocument()
  })

  it('renders an explicit missing state without inventing release evidence', () => {
    render(
      <MemoryRouter>
        <ReleaseOperationsSummary readiness={null} />
      </MemoryRouter>,
    )

    expect(screen.getByText('Not connected')).toBeInTheDocument()
    expect(screen.getByText('Undecided')).toBeInTheDocument()
    expect(screen.getByText('0/0')).toBeInTheDocument()
  })
})
