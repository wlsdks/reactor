import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import { ControlPlaneRecoveryPanel } from '../ui/ControlPlaneRecoveryPanel'
import type { ControlPlaneRecoverySummary } from '../controlPlaneRecovery'

const summary: ControlPlaneRecoverySummary = {
  status: 'WARN',
  attentionCount: 1,
  failCount: 0,
  transportFailureCount: 0,
  missingContractCount: 1,
  declaredBrokenCount: 0,
  manifestDriftCount: 0,
  items: [{
    status: 'WARN',
    kind: 'missingContract',
    route: { path: '/safety-rules?tab=tool-policy', labelKey: 'nav.safetyRules' },
    stepIds: ['checkManifest', 'reopenConsole'],
    probe: {
      id: 'toolPolicy',
      path: '/api/tool-policy',
      routePath: '/safety-rules?tab=tool-policy',
      status: 'WARN',
      reason: 'notAdvertised',
      manifestDeclared: false,
      httpStatus: 404,
      durationMs: 12,
      detail: 'HTTP 404',
    },
  }],
}

describe('ControlPlaneRecoveryPanel', () => {
  it('uses one recovery row and keeps diagnostic detail collapsed', () => {
    const { container } = render(
      <MemoryRouter>
        <ControlPlaneRecoveryPanel loading={false} recoverySummary={summary} />
      </MemoryRouter>,
    )

    expect(container.querySelector('.control-plane-recovery__summary')).not.toBeInTheDocument()
    expect(container.querySelectorAll('.control-plane-recovery__item')).toHaveLength(1)
    expect(container.querySelector('.stat-card')).not.toBeInTheDocument()
    expect(container.querySelector('.info-card')).not.toBeInTheDocument()
    expect(container.querySelector('.badge')).not.toBeInTheDocument()
    expect(screen.getByText('integrationsPage.recoveryRunbookTitle').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByText('common.technicalDetails').closest('details')).not.toHaveAttribute('open')
  })

  it('shows the highest-priority connection problems first and expands the remainder on demand', async () => {
    const user = userEvent.setup()
    const manyItems = Array.from({ length: 4 }, (_, index) => ({
      ...summary.items[0],
      probe: {
        ...summary.items[0].probe,
        id: ['toolPolicy', 'mcpSecurity', 'providerModels', 'schedulerJobs'][index] as typeof summary.items[0]['probe']['id'],
      },
    }))
    const manyItemsSummary: ControlPlaneRecoverySummary = {
      ...summary,
      attentionCount: manyItems.length,
      missingContractCount: manyItems.length,
      items: manyItems,
    }

    const { container } = render(
      <MemoryRouter>
        <ControlPlaneRecoveryPanel loading={false} recoverySummary={manyItemsSummary} />
      </MemoryRouter>,
    )

    expect(container.querySelectorAll('.control-plane-recovery__item')).toHaveLength(3)
    const showAll = screen.getByRole('button', { name: 'integrationsPage.recoveryShowAll' })
    await user.click(showAll)
    expect(container.querySelectorAll('.control-plane-recovery__item')).toHaveLength(4)
  })

  it('uses a compact passing status when no connection issue needs attention', () => {
    const { container } = render(
      <MemoryRouter>
        <ControlPlaneRecoveryPanel
          loading={false}
          recoverySummary={{
            ...summary,
            status: 'PASS',
            attentionCount: 0,
            missingContractCount: 0,
            items: [],
          }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('status')).toHaveTextContent('integrationsPage.recoveryEmpty')
    expect(container.querySelector('.empty-state')).not.toBeInTheDocument()
  })
})
