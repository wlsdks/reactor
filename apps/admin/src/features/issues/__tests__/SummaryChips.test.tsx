import { beforeEach, describe, it, expect, vi } from 'vitest'
import type { ComponentProps } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { i18n, render, screen } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { SummaryChips } from '../ui/SummaryChips'
import type { IssueCenterSnapshot } from '../types'

function buildSnapshot(overrides?: Partial<IssueCenterSnapshot>): IssueCenterSnapshot {
  return {
    generatedAt: Date.now(),
    total: 3,
    criticalCount: 1,
    warningCount: 2,
    sources: [
      { source: 'mcpServers', total: 1, criticalCount: 1, warningCount: 0 },
      { source: 'scheduler', total: 2, criticalCount: 0, warningCount: 2 },
    ],
    items: [
      { id: 'i-1', severity: 'critical', source: 'mcpServers', title: { key: 'test.c' }, summary: { key: 'test.s' }, detectedAt: null, routePath: '/mcp-servers', routeLabelKey: 'nav.mcpServers', evidence: [] },
      { id: 'i-2', severity: 'warning', source: 'scheduler', title: { key: 'test.w1' }, summary: { key: 'test.s' }, detectedAt: null, routePath: '/scheduler', routeLabelKey: 'nav.scheduler', evidence: [] },
      { id: 'i-3', severity: 'warning', source: 'scheduler', title: { key: 'test.w2' }, summary: { key: 'test.s' }, detectedAt: null, routePath: '/scheduler', routeLabelKey: 'nav.scheduler', evidence: [] },
    ],
    ...overrides,
  }
}

function renderSummary(props: Partial<ComponentProps<typeof SummaryChips>> = {}) {
  return render(
    <MemoryRouter>
      <SummaryChips
        snapshot={buildSnapshot()}
        sourceFilter={null}
        activeSeverity={null}
        onSeverityChange={vi.fn()}
        {...props}
      />
    </MemoryRouter>,
  )
}

describe('SummaryChips', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'issuesPage.healthySystems': '{{count}} healthy services',
      'issuesPage.openHealth': 'Open status',
    }, true, true)
  })

  it('renders Total, Critical, Warning, Healthy chips with correct counts', () => {
    renderSummary()
    expect(screen.getByText('3')).toBeInTheDocument()  // total count
    expect(screen.getByText('1')).toBeInTheDocument()  // critical count
    expect(screen.getByText('2')).toBeInTheDocument()  // warning count
    expect(screen.getByRole('button', { name: /total/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /critical/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /warning/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /healthy/i })).toHaveAttribute('href', '/health')
  })

  it('calculates healthyCount correctly (8 sources minus those with issues)', () => {
    renderSummary()
    // Healthy systems open the platform status detail instead of looking inert.
    const healthyChip = screen.getByRole('link', { name: /healthy/i })
    expect(healthyChip).toHaveTextContent('6')
  })

  it('calls onSeverityChange with "critical" when Critical chip is clicked', async () => {
    const user = userEvent.setup()
    const onSeverityChange = vi.fn()
    renderSummary({ onSeverityChange })
    await user.click(screen.getByRole('button', { name: /critical/i }))
    expect(onSeverityChange).toHaveBeenCalledWith('critical')
  })

  it('calls onSeverityChange with null when clicking the already-active chip (deselect)', async () => {
    const user = userEvent.setup()
    const onSeverityChange = vi.fn()
    renderSummary({ activeSeverity: 'critical', onSeverityChange })
    await user.click(screen.getByRole('button', { name: /critical/i }))
    expect(onSeverityChange).toHaveBeenCalledWith(null)
  })

  it('calls onSeverityChange with null when Total chip is clicked', async () => {
    const user = userEvent.setup()
    const onSeverityChange = vi.fn()
    renderSummary({ activeSeverity: 'warning', onSeverityChange })
    await user.click(screen.getByRole('button', { name: /total/i }))
    expect(onSeverityChange).toHaveBeenCalledWith(null)
  })

  it('marks the active chip with aria-pressed="true"', () => {
    renderSummary({ activeSeverity: 'warning' })
    expect(screen.getByRole('button', { name: /warning/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /critical/i })).toHaveAttribute('aria-pressed', 'false')
  })
})
