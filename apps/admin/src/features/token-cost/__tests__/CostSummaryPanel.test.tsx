import { describe, it, expect } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { render, screen } from '../../../test/utils'
import {
  RELEASE_WORKFLOW_ANCHOR_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import { CostSummaryPanel } from '../ui/CostSummaryPanel'
import type { MessageCost } from '../types'

const NOW = Date.now()

function buildCost(overrides: Partial<MessageCost> = {}): MessageCost {
  return {
    runId: 'run-1',
    model: 'claude-sonnet-4-20250514',
    provider: 'anthropic',
    stepType: 'llm_call',
    promptTokens: 200,
    completionTokens: 300,
    totalTokens: 500,
    estimatedCostUsd: 0.002,
    time: NOW,
    ...overrides,
  }
}

describe('CostSummaryPanel', () => {
  function renderPanel(costs: MessageCost[]) {
    return render(
      <MemoryRouter>
        <CostSummaryPanel costs={costs} />
      </MemoryRouter>,
    )
  }

  it('renders nothing when costs array is empty', () => {
    const { container } = renderPanel([])

    expect(container.firstChild).toBeNull()
  })

  it('renders total cost and token count', () => {
    const costs = [
      buildCost({ estimatedCostUsd: 0.002, totalTokens: 500 }),
      buildCost({ runId: 'run-2', estimatedCostUsd: 0.003, totalTokens: 700 }),
    ]

    renderPanel(costs)

    expect(screen.getByText('$0.0050')).toBeInTheDocument()
    expect(screen.getByText('1,200')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('renders model breakdown', () => {
    const costs = [
      buildCost({ model: 'claude-sonnet-4-20250514', estimatedCostUsd: 0.002 }),
      buildCost({ runId: 'run-2', model: 'claude-haiku-35-20241022', estimatedCostUsd: 0.001 }),
    ]

    renderPanel(costs)

    expect(screen.getByText('claude-sonnet-4-20250514')).toBeInTheDocument()
    expect(screen.getByText('claude-haiku-35-20241022')).toBeInTheDocument()
  })

  it('renders the summary panel container', () => {
    const costs = [buildCost()]

    renderPanel(costs)

    expect(screen.getByTestId('cost-summary-panel')).toBeInTheDocument()
  })

  it('links cost accounting back to provider smoke evidence', () => {
    renderPanel([buildCost()])

    const providerSmokeLink = screen.getByRole('link', {
      name: /tokenCost\.openProviderSmoke/,
    })
    expect(providerSmokeLink).toHaveAttribute('href', RELEASE_WORKFLOW_PATHS_BY_ID.provider)
    expect(providerSmokeLink)
      .toHaveTextContent(`${RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.provider}tokenCost.openProviderSmoke`)
  })

  it('links cost accounting back to the release workflow cockpit', () => {
    renderPanel([buildCost()])

    expect(screen.getByRole('link', { name: 'common.releaseWorkflowBacklinkStep' }))
      .toHaveAttribute('href', RELEASE_WORKFLOW_ANCHOR_PATH)
  })
})
