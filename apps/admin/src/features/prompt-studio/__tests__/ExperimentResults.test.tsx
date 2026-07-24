import { render, screen, fireEvent, within } from '../../../test/utils'
import { describe, it, expect, vi } from 'vitest'
import { ExperimentResults } from '../ui/ExperimentResults'
import type { PromptExperimentReport, PromptTrial } from '../types'
import { i18n } from '../../../test/utils'

i18n.addResourceBundle('en', 'translation', {
  'promptStudio.versionLabel': 'Version {{version}}',
  'promptStudio.versionComparison': 'Version comparison',
  'promptStudio.winner': 'Recommended',
  'promptStudio.confidence.high': 'High confidence',
  'promptStudio.confidence.medium': 'Medium confidence',
  'promptStudio.confidence.low': 'Needs more review',
  'promptStudio.confidence.unknown': 'Review confidence',
  'promptStudio.baseline': 'Current baseline',
  'promptStudio.candidate': 'Proposed version',
  'promptStudio.trialPassed': 'Meets criteria',
  'promptStudio.trialNeedsReview': 'Needs review',
  'promptStudio.score': 'Score',
  'promptStudio.duration': 'Duration',
}, true, true)

const mockReport: PromptExperimentReport = {
  experimentId: 'exp-1',
  experimentName: 'Support Bot Optimization',
  generatedAt: 1710002000000,
  totalTrials: 20,
  versionSummaries: [
    {
      versionId: 'ver-1',
      versionNumber: 1,
      isBaseline: true,
      totalTrials: 10,
      passCount: 7,
      passRate: 70,
      avgScore: 0.72,
      avgDurationMs: 2400,
      totalTokens: 5000,
      errorRate: 0.1,
      tierBreakdown: {},
      toolUsageFrequency: {},
    },
    {
      versionId: 'ver-2',
      versionNumber: 2,
      isBaseline: false,
      totalTrials: 10,
      passCount: 9,
      passRate: 90,
      avgScore: 0.88,
      avgDurationMs: 1800,
      totalTokens: 4500,
      errorRate: 0.02,
      tierBreakdown: {},
      toolUsageFrequency: {},
    },
  ],
  recommendation: {
    bestVersionId: 'ver-2',
    bestVersionNumber: 2,
    confidence: 'HIGH',
    reasoning: 'Version 2 significantly outperforms the baseline across all metrics with higher pass rates and lower error rates.',
    improvements: ['Better pass rate', 'Lower latency'],
    warnings: [],
  },
}

function buildTrial(index: number, overrides: Partial<PromptTrial> = {}): PromptTrial {
  return {
    id: `trial-${index}`,
    promptVersionId: index % 2 === 0 ? 'ver-1' : 'ver-2',
    promptVersionNumber: index % 2 === 0 ? 1 : 2,
    query: `Test query ${index}`,
    response: `Response ${index}`,
    success: true,
    score: 0.5 + (index * 0.03),
    durationMs: 1000 + index * 100,
    toolsUsed: [],
    passed: index % 3 !== 0,
    executedAt: 1710001000000 + index * 1000,
    ...overrides,
  }
}

const mockTrials: PromptTrial[] = Array.from({ length: 15 }, (_, i) => buildTrial(i))

describe('ExperimentResults', () => {
  it('renders winner banner with recommendation', () => {
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={vi.fn()}
      />,
    )

    const banner = document.querySelector('.winner-banner')!
    expect(banner).toBeInTheDocument()

    expect(banner.querySelector('svg')).toBeInTheDocument()

    // Winner title shows version and confidence
    const title = document.querySelector('.winner-title')!
    expect(title).toHaveTextContent('Version 2')
    expect(title).toHaveTextContent('High confidence')
    expect(title).not.toHaveTextContent('HIGH')

    // Reasoning text
    const reason = document.querySelector('.winner-reason')!
    expect(reason).toHaveTextContent('Version 2 significantly outperforms')
  })

  it('shows flat comparison rows with metrics', () => {
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={vi.fn()}
      />,
    )

    const cards = document.querySelectorAll('.comparison-row')
    expect(cards).toHaveLength(2)

    // Baseline card (first)
    const baselineCard = cards[0]
    expect(baselineCard).toHaveTextContent('70%')
    expect(baselineCard).toHaveTextContent('0.72')
    expect(baselineCard).toHaveTextContent('2.4s')
    expect(baselineCard).toHaveTextContent('10%')

    // Candidate card (second) - should have winner class
    const candidateCard = cards[1]
    expect(candidateCard).toHaveClass('winner')
    expect(candidateCard).toHaveTextContent('90%')
    expect(candidateCard).toHaveTextContent('0.88')
    expect(candidateCard).toHaveTextContent('1.8s')
    expect(candidateCard).toHaveTextContent('2%')

    // Delta indicators on candidate card
    const facts = candidateCard.querySelectorAll('.comparison-fact')
    expect(facts).toHaveLength(4)
    const deltas = candidateCard.querySelectorAll('.comparison-fact__delta')
    expect(deltas.length).toBeGreaterThan(0)
    // Pass rate delta should be positive
    const positiveDeltas = candidateCard.querySelectorAll('.comparison-fact__delta.positive')
    expect(positiveDeltas.length).toBeGreaterThan(0)
  })

  it('shows trial samples table', () => {
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={vi.fn()}
      />,
    )

    // First 10 trials shown by default
    expect(screen.getByText('Test query 0')).toBeInTheDocument()
    expect(screen.getByText('Test query 9')).toBeInTheDocument()

    // Trial 10+ should not be visible
    expect(screen.queryByText('Test query 10')).not.toBeInTheDocument()

    // Check pass/fail indicators in table
    const table = document.querySelector('.data-table')!
    expect(within(table as HTMLElement).getAllByText('Meets criteria').length).toBeGreaterThan(0)
    expect(within(table as HTMLElement).getAllByText('Needs review').length).toBeGreaterThan(0)
  })

  it('calls onActivateWinner when button clicked', () => {
    const onActivateWinner = vi.fn()
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={onActivateWinner}
      />,
    )

    // The activate button is in the winner banner
    const banner = document.querySelector('.winner-banner')!
    const activateButton = within(banner as HTMLElement).getByRole('button')
    fireEvent.click(activateButton)

    expect(onActivateWinner).toHaveBeenCalledTimes(1)
  })

  it('"Show all" expands trial list', () => {
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={vi.fn()}
      />,
    )

    // Trial 10 not visible initially
    expect(screen.queryByText('Test query 10')).not.toBeInTheDocument()

    // Click "Show all" button in the trial-samples section
    const trialSection = document.querySelector('.trial-samples')!
    const showAllButton = within(trialSection as HTMLElement).getByRole('button', { name: /15/ })
    fireEvent.click(showAllButton)

    // Now all trials visible
    expect(screen.getByText('Test query 10')).toBeInTheDocument()
    expect(screen.getByText('Test query 14')).toBeInTheDocument()
  })

  it('sorting by score works', () => {
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={vi.fn()}
      />,
    )

    // Click score header to sort descending (default first click)
    const table = document.querySelector('.data-table')!
    const scoreHeader = within(table as HTMLElement).getByRole('button', { name: 'Score' })
    fireEvent.click(scoreHeader)

    // Get table body rows only
    const tbody = table.querySelector('tbody')!
    let rows = tbody.querySelectorAll('tr')

    // First data row should have highest score among first 10 displayed
    // Trial 9 has score 0.5 + 9*0.03 = 0.77 (highest in top 10 of sorted by desc)
    // Actually with 15 trials sorted desc, top 10 are trials 14..5
    // Trial 14: score = 0.5 + 14*0.03 = 0.92
    expect(rows[0]).toHaveTextContent('0.92')

    // Click again to sort ascending
    fireEvent.click(scoreHeader)
    rows = tbody.querySelectorAll('tr')
    // Trial 0 has score 0.50
    expect(rows[0]).toHaveTextContent('0.50')
  })

  it('sorting by duration works', () => {
    render(
      <ExperimentResults
        report={mockReport}
        trials={mockTrials}
        onActivateWinner={vi.fn()}
      />,
    )

    // Click duration header
    const table = document.querySelector('.data-table')!
    const durationHeader = within(table as HTMLElement).getByRole('button', { name: 'Duration' })
    fireEvent.click(durationHeader)

    const tbody = table.querySelector('tbody')!
    let rows = tbody.querySelectorAll('tr')

    // Descending sort: trial 14 has durationMs = 1000 + 14*100 = 2400ms
    expect(rows[0]).toHaveTextContent('Test query 14')

    // Click again for ascending
    fireEvent.click(durationHeader)
    rows = tbody.querySelectorAll('tr')
    // Trial 0 has durationMs = 1000ms
    expect(rows[0]).toHaveTextContent('Test query 0')
  })
})
