import { i18n, render, screen } from '../../../test/utils'
import { describe, it, expect } from 'vitest'
import { ActivityFeed } from '../ui/ActivityFeed'

describe('ActivityFeed', () => {
  it('returns null when no events', () => {
    const { container } = render(
      <ActivityFeed metrics={[]} trustEvents={[]} generatedAt={Date.now()} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders non-zero metrics', () => {
    i18n.addResourceBundle('en', 'translation', {
      'dashboard.metricLabel.agentExecutions': 'Agent executions',
      'dashboard.metricLabel.agentErrors': 'Agent errors',
    }, true, true)
    const metrics = [
      { name: 'reactor.agent.executions', meterCount: 3, measurements: { count: 3 } },
      { name: 'reactor.agent.errors', meterCount: 0, measurements: {} },
    ]
    render(<ActivityFeed metrics={metrics} trustEvents={[]} generatedAt={Date.now()} />)
    expect(screen.getByText('Agent executions')).toBeInTheDocument()
    expect(screen.queryByText('Agent errors')).not.toBeInTheDocument()
  })

  it('renders trust events', () => {
    const trustEvents = [{
      occurredAt: Date.now(),
      type: 'OUTPUT_GUARD',
      severity: 'WARNING',
    }]
    render(<ActivityFeed metrics={[]} trustEvents={trustEvents} generatedAt={Date.now()} />)
    expect(screen.getByText(/OUTPUT_GUARD/)).toBeInTheDocument()
  })

  it('shows max 5 items', () => {
    const metrics = Array.from({ length: 8 }, (_, i) => ({
      name: `reactor.metric.${i}`,
      meterCount: i + 1,
      measurements: { count: i + 1 },
    }))
    render(<ActivityFeed metrics={metrics} trustEvents={[]} generatedAt={Date.now()} />)
    const items = document.querySelectorAll('.feed-item')
    expect(items.length).toBeLessThanOrEqual(5)
  })

  it('sorts items by timestamp descending', () => {
    const now = Date.now()
    const trustEvents = [
      { occurredAt: now - 10000, type: 'OLDER_EVENT', severity: 'INFO' },
      { occurredAt: now, type: 'NEWEST_EVENT', severity: 'WARNING' },
    ]
    render(<ActivityFeed metrics={[]} trustEvents={trustEvents} generatedAt={now - 5000} />)
    const labels = document.querySelectorAll('.feed-item__label')
    expect(labels[0].textContent).toBe('NEWEST_EVENT')
    expect(labels[1].textContent).toBe('OLDER_EVENT')
  })
})
