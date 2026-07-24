import { describe, it, expect } from 'vitest'
import { i18n, render, screen } from '../../../test/utils'
import { TokenCostBadge } from '../ui/TokenCostBadge'
import type { MessageCost } from '../types'

const mockCost: MessageCost = {
  runId: 'run-1',
  model: 'claude-sonnet-4-20250514',
  provider: 'anthropic',
  stepType: 'llm_call',
  promptTokens: 800,
  completionTokens: 1200,
  totalTokens: 2000,
  estimatedCostUsd: 0.003,
  time: Date.now(),
}

describe('TokenCostBadge', () => {
  beforeAll(() => {
    i18n.addResourceBundle('en', 'translation', {
      'tokenCost.badgeTooltip': 'In: {{input}} · Out: {{output}} · Model: {{model}}',
      'tokenCost.badgeLabel': '{{tokens}} tokens · {{cost}}',
    }, true, true)
  })

  it('renders token count and cost when visible', () => {
    render(<TokenCostBadge cost={mockCost} visible={true} />)

    expect(screen.getByText('2.0k')).toBeInTheDocument()
    expect(screen.getByText('$0.0030')).toBeInTheDocument()
  })

  it('returns null when not visible', () => {
    const { container } = render(<TokenCostBadge cost={mockCost} visible={false} />)

    expect(container.firstChild).toBeNull()
  })

  it('returns null when cost is undefined', () => {
    const { container } = render(<TokenCostBadge cost={undefined} visible={true} />)

    expect(container.firstChild).toBeNull()
  })

  it('formats small token counts without abbreviation', () => {
    const smallCost: MessageCost = { ...mockCost, totalTokens: 500, estimatedCostUsd: 0.0005 }
    render(<TokenCostBadge cost={smallCost} visible={true} />)

    expect(screen.getByText('500')).toBeInTheDocument()
    expect(screen.getByText('$0.000500')).toBeInTheDocument()
  })

  it('has correct aria-label with full details', () => {
    render(<TokenCostBadge cost={mockCost} visible={true} />)

    const badge = screen.getByLabelText(/2,000 tokens/)
    expect(badge).toBeInTheDocument()
  })
})
