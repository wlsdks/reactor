import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '../../../test/utils'
import * as integrationsApi from '../api'
import { ExternalSmokeOperations } from '../ui/ExternalSmokeOperations'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'

vi.mock('../api', () => ({
  runSlackLiveSmoke: vi.fn(),
  runA2aLiveSmoke: vi.fn(),
}))

const runSlackLiveSmokeMock = vi.mocked(integrationsApi.runSlackLiveSmoke)
const runA2aLiveSmokeMock = vi.mocked(integrationsApi.runA2aLiveSmoke)

const readiness: DashboardReleaseReadinessSummary = {
  status: 'blocked',
  syncedAt: '2026-07-10T00:00:00Z',
  slackGatewaySmoke: {
    status: 'verified',
    gateway: 'native_slack_gateway',
    workspaceId: 'T_OLD',
    channelId: 'C_OLD',
  },
}

describe('ExternalSmokeOperations', () => {
  it('requires typed Slack confirmation and keeps fresh readiness pending', async () => {
    const user = userEvent.setup()
    const refreshReadiness = vi.fn().mockResolvedValue(undefined)
    runSlackLiveSmokeMock.mockResolvedValue({
      ok: true,
      status: 'passed',
      scope: 'live',
      liveTarget: {
        workspaceId: 'T123',
        channelId: 'C123',
        botUserId: 'U123',
      },
      evidence: {
        slackGatewaySmoke: {
          status: 'verified',
          gateway: 'native_slack_gateway',
        },
      },
      checks: {
        auth_test: { status: 'passed' },
        thread_message: { status: 'passed' },
      },
    })

    render(
      <ExternalSmokeOperations
        releaseReadiness={readiness}
        onRefreshReadiness={refreshReadiness}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'integrationsPage.releaseSmoke.operations.runSlack' }))
    expect(runSlackLiveSmokeMock).not.toHaveBeenCalled()
    const confirmInput = screen.getByRole('textbox')
    await user.type(confirmInput, 'SLACK')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    await waitFor(() => expect(runSlackLiveSmokeMock).toHaveBeenCalledTimes(1))
    expect(refreshReadiness).toHaveBeenCalledTimes(1)
    const result = screen.getByRole('region', {
      name: 'integrationsPage.releaseSmoke.operations.slackResult',
    })
    expect(result).toHaveTextContent('T123')
    expect(result).toHaveTextContent('C123')
    expect(result).toHaveTextContent('U123')
    expect(result).toHaveTextContent('integrationsPage.releaseSmoke.operations.readinessPending')
  })

  it('requires typed A2A confirmation and shows the created task evidence', async () => {
    const user = userEvent.setup()
    runA2aLiveSmokeMock.mockResolvedValue({
      ok: true,
      status: 'passed',
      scope: 'live',
      base_url: 'https://reactor.example',
      evidence: {
        a2aProtocol: {
          status: 'verified',
          agentCard: { name: 'Reactor', interfaceCount: 1 },
          taskApi: { status: 'passed', taskStatus: 'completed', path: '/v1/a2a/tasks' },
          secretFree: true,
          tlsRequired: true,
        },
      },
      checks: {
        task_api: { status: 'passed', task_id: 'task_123', task_status: 'completed' },
      },
    })

    render(
      <ExternalSmokeOperations
        releaseReadiness={readiness}
        onRefreshReadiness={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'integrationsPage.releaseSmoke.operations.runA2a' }))
    await user.type(screen.getByRole('textbox'), 'A2A')
    await user.click(screen.getByRole('button', { name: 'Confirm' }))

    const result = await screen.findByRole('region', {
      name: 'integrationsPage.releaseSmoke.operations.a2aResult',
    })
    expect(result).toHaveTextContent('https://reactor.example')
    expect(result).toHaveTextContent('task_123')
    expect(result).toHaveTextContent('Reactor')
  })
})
