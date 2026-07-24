import { describe, it, expect } from 'vitest'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, within } from '../../../test/utils'
import { ModelDetailDrawer } from '../ui/ModelDetailDrawer'
import { estimateMonthlyCost } from '../pricing'
import type { ModelEntry } from '../types'

function buildModel(overrides: Partial<ModelEntry> = {}): ModelEntry {
  return {
    name: 'gpt-4o',
    inputPricePerMillionTokens: 2.5,
    outputPricePerMillionTokens: 10,
    isDefault: false,
    ...overrides,
  }
}

describe('estimateMonthlyCost', () => {
  it('computes (inputTokens / 1M) * inputPrice + (outputTokens / 1M) * outputPrice', () => {
    // 1M input @ $2.50 + 1M output @ $10.00 = $12.50
    expect(estimateMonthlyCost(1_000_000, 1_000_000, 2.5, 10)).toBeCloseTo(12.5, 5)
  })

  it('scales linearly with token volume', () => {
    // 2M input @ $3 + 500k output @ $6 = 6 + 3 = 9
    expect(estimateMonthlyCost(2_000_000, 500_000, 3, 6)).toBeCloseTo(9, 5)
  })

  it('returns 0 when tokens are 0', () => {
    expect(estimateMonthlyCost(0, 0, 2.5, 10)).toBe(0)
  })

  it('treats negative or NaN inputs as 0', () => {
    expect(estimateMonthlyCost(-100, Number.NaN, 2.5, 10)).toBe(0)
  })
})

describe('ModelDetailDrawer', () => {
  it('renders with minimal model data', () => {
    render(
      <ModelDetailDrawer
        model={buildModel()}
        alerts={[]}
        onClose={() => {}}
      />,
    )
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getAllByText('gpt-4o').length).toBeGreaterThan(0)
    expect(within(dialog).getByText('modelsPage.drawer.pricingSection')).toBeInTheDocument()
    expect(within(dialog).getByText('modelsPage.drawer.capabilitiesSection')).toBeInTheDocument()
    expect(within(dialog).getByText('modelsPage.drawer.contextSection')).toBeInTheDocument()
    expect(within(dialog).getByText('modelsPage.drawer.alertsSection')).toBeInTheDocument()
    expect(within(dialog).getByText('modelsPage.drawer.noAlerts')).toBeInTheDocument()
  })

  it('does not render when model is null', () => {
    render(
      <ModelDetailDrawer model={null} alerts={[]} onClose={() => {}} />,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows the default model as supporting text instead of a badge', () => {
    render(
      <ModelDetailDrawer
        model={buildModel({ isDefault: true })}
        alerts={[]}
        onClose={() => {}}
      />,
    )
    const defaultLabel = screen.getByText('modelsPage.default')
    expect(defaultLabel).toHaveClass('model-detail-drawer__default')
    expect(defaultLabel).not.toHaveClass('badge')
  })

  it('renders a readable provider label when present', () => {
    render(
      <MemoryRouter>
        <ModelDetailDrawer
          model={buildModel({ provider: 'openai' })}
          alerts={[]}
          onClose={() => {}}
        />
      </MemoryRouter>,
    )
    expect(screen.getByText('modelsPage.providerSmoke.providerLabels.openai')).toBeInTheDocument()
    expect(screen.queryByText('openai')).not.toBeInTheDocument()
  })

  it('shows provider context without duplicating release workflow navigation', () => {
    render(
      <MemoryRouter>
        <ModelDetailDrawer
          model={buildModel({ provider: 'ollama' })}
          alerts={[]}
          onClose={() => {}}
        />
      </MemoryRouter>,
    )
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('modelsPage.providerSmoke.providerLabels.local'))
      .toHaveClass('model-detail-drawer__provider')
    expect(within(dialog).queryByText('ollama')).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link')).not.toBeInTheDocument()
  })

  it('formats context length with thousands separators', () => {
    render(
      <ModelDetailDrawer
        model={buildModel({ contextLength: 128000, maxTokens: 16384 })}
        alerts={[]}
        onClose={() => {}}
      />,
    )
    expect(screen.getByText('128,000')).toBeInTheDocument()
    expect(screen.getByText('16,384')).toBeInTheDocument()
  })

  it('calculates the monthly estimate: 1M * inputPrice + 1M * outputPrice', () => {
    render(
      <ModelDetailDrawer
        model={buildModel({
          inputPricePerMillionTokens: 2.5,
          outputPricePerMillionTokens: 10,
        })}
        alerts={[]}
        onClose={() => {}}
      />,
    )
    // Default inputs: 1M input + 1M output → 2.5 + 10 = $12.50
    expect(screen.getByTestId('model-monthly-estimate')).toHaveTextContent('$12.50')
  })

  it('recomputes the estimate when the user edits token inputs', async () => {
    const user = userEvent.setup()
    render(
      <ModelDetailDrawer
        model={buildModel({
          inputPricePerMillionTokens: 3,
          outputPricePerMillionTokens: 6,
        })}
        alerts={[]}
        onClose={() => {}}
      />,
    )
    const input = screen.getByLabelText('modelsPage.drawer.expectedInputTokens')
    const output = screen.getByLabelText('modelsPage.drawer.expectedOutputTokens')
    await user.clear(input)
    await user.type(input, '2000000')
    await user.clear(output)
    await user.type(output, '500000')
    // 2M * 3 / 1M + 0.5M * 6 / 1M = 6 + 3 = 9
    expect(screen.getByTestId('model-monthly-estimate')).toHaveTextContent('$9.00')
  })

  it('renders capability labels instead of raw implementation values', () => {
    render(
      <ModelDetailDrawer
        model={buildModel({ capabilities: ['tools', 'vision'] })}
        alerts={[]}
        onClose={() => {}}
      />,
    )
    const chips = screen.getAllByTestId('model-capability-chip')
    expect(chips).toHaveLength(2)
    expect(chips[0]).toHaveTextContent('modelsPage.drawer.capabilityLabels.tools')
    expect(chips[1]).toHaveTextContent('modelsPage.drawer.capabilityLabels.vision')
    expect(chips[0]).not.toHaveClass('badge')
  })

  it('lists alerts whose metric/description references the model name', () => {
    render(
      <ModelDetailDrawer
        model={buildModel({ name: 'gpt-4o' })}
        alerts={[
          {
            id: 'a1',
            name: 'High gpt-4o latency',
            type: 'STATIC_THRESHOLD',
            metric: 'llm.latency_p99{model=gpt-4o}',
            threshold: 2000,
            severity: 'WARNING',
          },
          {
            id: 'a2',
            name: 'Unrelated budget alert',
            type: 'STATIC_THRESHOLD',
            metric: 'cost.monthly',
            threshold: 1000,
          },
        ]}
        onClose={() => {}}
      />,
    )
    expect(screen.getByText('High gpt-4o latency')).toBeInTheDocument()
    expect(screen.queryByText('Unrelated budget alert')).not.toBeInTheDocument()
    expect(screen.getByText('modelsPage.drawer.severityLabels.warning')).toBeInTheDocument()
    expect(screen.queryByText('WARNING')).not.toBeInTheDocument()
    expect(document.querySelector('.model-detail-drawer__alert-technical')).not.toHaveAttribute('open')
  })

  it('keeps the alert metric in a closed technical disclosure', async () => {
    const user = userEvent.setup()
    render(
      <ModelDetailDrawer
        model={buildModel({ name: 'gpt-4o' })}
        alerts={[{
          id: 'a1',
          name: 'High gpt-4o latency',
          type: 'STATIC_THRESHOLD',
          metric: 'llm.latency_p99{model=gpt-4o}',
          threshold: 2000,
          severity: 'WARNING',
        }]}
        onClose={() => {}}
      />,
    )

    const details = document.querySelector('.model-detail-drawer__alert-technical')
    expect(details).not.toHaveAttribute('open')
    await user.click(screen.getByText('modelsPage.drawer.technicalDetails'))
    expect(details).toHaveAttribute('open')
    expect(screen.getByText('llm.latency_p99{model=gpt-4o}')).toBeInTheDocument()
  })
})
