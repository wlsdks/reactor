import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { ReadinessStrip, type ReadinessCheck } from '../ReadinessStrip'

function makeChecks(): ReadinessCheck[] {
  return [
    { id: 'contract', label: 'Contract', status: 'PASS', description: 'Contract is healthy.' },
    { id: 'queue', label: 'Pending Queue', status: 'PASS', description: 'No backlog.' },
    { id: 'timeout', label: 'Timeout Debt', status: 'PASS', description: 'Nothing timed out.' },
    { id: 'coverage', label: 'Request Coverage', status: 'PASS', description: 'All metadata present.' },
  ]
}

describe('ReadinessStrip', () => {
  it('renders every readiness check row with label and description', () => {
    render(<ReadinessStrip checks={makeChecks()} />)
    expect(screen.getByText('Contract')).toBeInTheDocument()
    expect(screen.getByText('Pending Queue')).toBeInTheDocument()
    expect(screen.getByText('Timeout Debt')).toBeInTheDocument()
    expect(screen.getByText('Request Coverage')).toBeInTheDocument()
    expect(screen.getByText('Contract is healthy.')).toBeInTheDocument()
    expect(screen.getByText('No backlog.')).toBeInTheDocument()
    expect(screen.getByText('Nothing timed out.')).toBeInTheDocument()
    expect(screen.getByText('All metadata present.')).toBeInTheDocument()
  })

  it('collapses by default when every check passes', () => {
    const { container } = render(<ReadinessStrip checks={makeChecks()} />)
    const details = container.querySelector('details') as HTMLDetailsElement
    expect(details).not.toBeNull()
    expect(details.open).toBe(false)
  })

  it('expands automatically when any check reports WARN', () => {
    const checks = makeChecks()
    checks[1] = { ...checks[1], status: 'WARN', description: 'Queue is growing.' }
    const { container } = render(<ReadinessStrip checks={checks} />)
    const details = container.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(true)
  })

  it('expands automatically when any check reports FAIL', () => {
    const checks = makeChecks()
    checks[0] = { ...checks[0], status: 'FAIL', description: 'Contract down.' }
    const { container } = render(<ReadinessStrip checks={checks} />)
    const details = container.querySelector('details') as HTMLDetailsElement
    expect(details.open).toBe(true)
  })

  it('shows overall PASS badge when every check passes', () => {
    const { container } = render(<ReadinessStrip checks={makeChecks()} />)
    const summary = container.querySelector('summary') as HTMLElement
    expect(summary.querySelector('.badge-green')).toBeInTheDocument()
  })

  it('shows FAIL badge when any check fails, even if others warn', () => {
    const checks = makeChecks()
    checks[0] = { ...checks[0], status: 'WARN', description: 'Warn row.' }
    checks[1] = { ...checks[1], status: 'FAIL', description: 'Fail row.' }
    const { container } = render(<ReadinessStrip checks={checks} />)
    const summary = container.querySelector('summary') as HTMLElement
    expect(summary.querySelector('.badge-red')).toBeInTheDocument()
  })

  it('renders a passing-count indicator', () => {
    const checks = makeChecks()
    checks[0] = { ...checks[0], status: 'WARN', description: 'Warn row.' }
    render(<ReadinessStrip checks={checks} />)
    expect(screen.getByText('3/4 passing')).toBeInTheDocument()
  })

  it('accepts a custom summary label override', () => {
    render(<ReadinessStrip checks={makeChecks()} summaryLabel="Custom Readiness Title" />)
    expect(screen.getByText('Custom Readiness Title')).toBeInTheDocument()
  })
})
