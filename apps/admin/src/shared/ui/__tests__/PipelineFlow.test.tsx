import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { PipelineFlow } from '../PipelineFlow'
import type { PipelineStage } from '../PipelineFlow'

const stages: PipelineStage[] = [
  { id: '1', name: 'Toxicity Filter', enabled: true, order: 1, ruleCount: 5, status: 'active' },
  { id: '2', name: 'PII Redactor', enabled: true, order: 2, ruleCount: 3, status: 'active' },
  { id: '3', name: 'Rate Limiter', enabled: false, order: 3, ruleCount: 1, status: 'disabled' },
]

describe('PipelineFlow', () => {
  it('renders all stage names', () => {
    render(<PipelineFlow stages={stages} />)
    expect(screen.getByText('Toxicity Filter')).toBeInTheDocument()
    expect(screen.getByText('PII Redactor')).toBeInTheDocument()
    expect(screen.getByText('Rate Limiter')).toBeInTheDocument()
  })

  it('renders as a list', () => {
    render(<PipelineFlow stages={stages} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })

  it('sorts stages by order', () => {
    const reversed: PipelineStage[] = [...stages].reverse()
    render(<PipelineFlow stages={reversed} />)
    const items = screen.getAllByRole('listitem')
    expect(items[0]).toHaveTextContent('Toxicity Filter')
    expect(items[1]).toHaveTextContent('PII Redactor')
    expect(items[2]).toHaveTextContent('Rate Limiter')
  })

  it('renders localized rule counts', () => {
    render(<PipelineFlow stages={stages} />)
    expect(screen.getAllByText('common.rulesCount')).toHaveLength(3)
  })

  it('applies selected class to selected stage', () => {
    const { container } = render(
      <PipelineFlow stages={stages} selectedStageId="2" />,
    )
    const cards = container.querySelectorAll('.pipeline-card')
    expect(cards[0].classList.contains('pipeline-card--selected')).toBe(false)
    expect(cards[1].classList.contains('pipeline-card--selected')).toBe(true)
    expect(cards[2].classList.contains('pipeline-card--selected')).toBe(false)
  })

  it('applies disabled class to disabled stages', () => {
    const { container } = render(<PipelineFlow stages={stages} />)
    const cards = container.querySelectorAll('.pipeline-card')
    expect(cards[0].classList.contains('pipeline-card--disabled')).toBe(false)
    expect(cards[2].classList.contains('pipeline-card--disabled')).toBe(true)
  })

  it('calls onStageClick when a stage is clicked', () => {
    const onClick = vi.fn()
    render(<PipelineFlow stages={stages} onStageClick={onClick} />)
    fireEvent.click(screen.getByText('PII Redactor'))
    expect(onClick).toHaveBeenCalledWith(stages[1])
  })

  it('calls onStageClick on Enter key', () => {
    const onClick = vi.fn()
    render(<PipelineFlow stages={stages} onStageClick={onClick} />)
    const card = screen.getByText('Toxicity Filter').closest('.pipeline-card') as HTMLElement
    fireEvent.keyDown(card, { key: 'Enter' })
    expect(onClick).toHaveBeenCalledWith(stages[0])
  })

  it('calls onStageClick on Space key', () => {
    const onClick = vi.fn()
    render(<PipelineFlow stages={stages} onStageClick={onClick} />)
    const card = screen.getByText('Toxicity Filter').closest('.pipeline-card') as HTMLElement
    fireEvent.keyDown(card, { key: ' ' })
    expect(onClick).toHaveBeenCalledWith(stages[0])
  })

  it('renders toggle switches when onToggle is provided', () => {
    const onToggle = vi.fn()
    render(<PipelineFlow stages={stages} onToggle={onToggle} />)
    const switches = screen.getAllByRole('switch')
    expect(switches).toHaveLength(3)
  })

  it('does not render toggle switches without onToggle', () => {
    render(<PipelineFlow stages={stages} />)
    expect(screen.queryAllByRole('switch')).toHaveLength(0)
  })

  it('calls onToggle when toggle is clicked', () => {
    const onToggle = vi.fn()
    render(<PipelineFlow stages={stages} onToggle={onToggle} />)
    const switches = screen.getAllByRole('switch')
    fireEvent.click(switches[0])
    expect(onToggle).toHaveBeenCalledWith('1', false)
  })

  it('toggle click does not propagate to onStageClick', () => {
    const onStageClick = vi.fn()
    const onToggle = vi.fn()
    render(<PipelineFlow stages={stages} onStageClick={onStageClick} onToggle={onToggle} />)
    const switches = screen.getAllByRole('switch')
    fireEvent.click(switches[0])
    expect(onToggle).toHaveBeenCalled()
    expect(onStageClick).not.toHaveBeenCalled()
  })

  it('renders ordered rows without connector ornament', () => {
    const { container } = render(<PipelineFlow stages={stages} />)
    const order = Array.from(container.querySelectorAll('.pipeline-card-order'))
      .map((element) => element.textContent)
    expect(order).toEqual(['01', '02', '03'])
    expect(container.querySelector('.pipeline-connector')).not.toBeInTheDocument()
  })

  it('renders empty list when no stages provided', () => {
    render(<PipelineFlow stages={[]} />)
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('renders stage description when provided', () => {
    const stagesWithDesc: PipelineStage[] = [
      { id: '1', name: 'Toxicity Filter', description: 'Filters toxic content', enabled: true, order: 1 },
      { id: '2', name: 'PII Redactor', enabled: true, order: 2 },
    ]
    render(<PipelineFlow stages={stagesWithDesc} />)
    expect(screen.getByText('Filters toxic content')).toBeInTheDocument()
    // Stage without description should not render a description element
    const items = screen.getAllByRole('listitem')
    expect(items[1].querySelector('.pipeline-card-description')).toBeNull()
  })

  it('applies error class for error stages', () => {
    const errorStages: PipelineStage[] = [
      { id: '1', name: 'Error Stage', enabled: true, order: 1, status: 'error' },
    ]
    const { container } = render(<PipelineFlow stages={errorStages} />)
    const card = container.querySelector('.pipeline-card')
    expect(card?.classList.contains('pipeline-card--error')).toBe(true)
  })
})
