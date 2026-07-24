import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import {
  DashboardStatCards,
  DashboardStatCardsSkeleton,
} from '../ui/DashboardStatCards'
import type { DashboardResponse } from '../types'
import type { IssueCenterSnapshot } from '../../issues'

function makeData(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    generatedAt: new Date().toISOString(),
    mcp: { total: 0, statusCounts: {} },
    scheduler: { runningJobs: 0, failedJobs: 0, pendingJobs: 0 },
    approvals: { pendingCount: 0 },
    responseTrust: {
      outputGuardRejected: 0,
      outputGuardModified: 0,
      boundaryFailures: 0,
      unverifiedResponses: 0,
    },
    metrics: { tracked: 0, sources: 0 },
    employeeValue: undefined,
    recentTrustEvents: [],
    ...overrides,
  } as unknown as DashboardResponse
}

const emptySnapshot: IssueCenterSnapshot = {
  criticalCount: 0,
  warningCount: 0,
} as unknown as IssueCenterSnapshot

describe('DashboardStatCardsSkeleton', () => {
  it('renders one table-shaped loading placeholder', () => {
    const { container } = render(<DashboardStatCardsSkeleton />)
    expect(container.querySelector('.skeleton-table-v2')).toBeInTheDocument()
    expect(container.querySelectorAll('.skeleton-card')).toHaveLength(0)
  })
})

describe('DashboardStatCards', () => {
  it('renders three operational rows without cards or fabricated trends', () => {
    const { container } = render(
      <DashboardStatCards
        data={makeData()}
        issueSnapshot={emptySnapshot}
        connectedCount={0}
      />,
    )
    expect(screen.getByRole('region', { name: 'dashboard.statCards.title' })).toBeInTheDocument()
    expect(container.querySelectorAll('.dashboard-status-row')).toHaveLength(3)
    expect(container.querySelectorAll('.stat-group')).toHaveLength(0)
    expect(container.querySelectorAll('.stat-sparkline')).toHaveLength(0)
  })
})
