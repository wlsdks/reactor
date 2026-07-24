import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { InfoCard } from '../InfoCard'

describe('InfoCard', () => {
  it('renders title text', () => {
    render(<InfoCard title="Connection probe">body</InfoCard>)
    expect(screen.getByText('Connection probe')).toBeInTheDocument()
  })

  it('renders title inside a <strong> element for semantic emphasis', () => {
    const { container } = render(<InfoCard title="Connection probe">body</InfoCard>)
    const strong = container.querySelector('strong.info-card-title')
    expect(strong).not.toBeNull()
    expect(strong?.textContent).toBe('Connection probe')
  })

  it('renders body content (children)', () => {
    render(
      <InfoCard title="Probe">
        <p>Inner body content</p>
      </InfoCard>,
    )
    expect(screen.getByText('Inner body content')).toBeInTheDocument()
  })

  it('renders header extra slot when provided', () => {
    render(
      <InfoCard title="Probe" headerExtra={<span data-testid="badge">OK</span>}>
        body
      </InfoCard>,
    )
    expect(screen.getByTestId('badge')).toBeInTheDocument()
  })

  it('renders subtitle when provided', () => {
    render(
      <InfoCard title="Probe" subtitle="last run 10m ago">
        body
      </InfoCard>,
    )
    expect(screen.getByText('last run 10m ago')).toBeInTheDocument()
  })

  it('renders actions slot when provided', () => {
    render(
      <InfoCard title="Probe" actions={<button>Open</button>}>
        body
      </InfoCard>,
    )
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument()
  })

  it('renders as <article> by default', () => {
    const { container } = render(<InfoCard title="Probe">body</InfoCard>)
    const card = container.querySelector('.info-card')
    expect(card?.tagName).toBe('ARTICLE')
  })

  it('does not render header-extra/subtitle/body/actions when not provided', () => {
    const { container } = render(<InfoCard title="Probe" />)
    expect(container.querySelector('.info-card-header-extra')).not.toBeInTheDocument()
    expect(container.querySelector('.info-card-subtitle')).not.toBeInTheDocument()
    expect(container.querySelector('.info-card-body')).not.toBeInTheDocument()
    expect(container.querySelector('.info-card-actions')).not.toBeInTheDocument()
  })

  it('does not add a variant class for default variant', () => {
    const { container } = render(<InfoCard title="Probe">body</InfoCard>)
    const card = container.querySelector('.info-card')
    expect(card?.classList.contains('info-card--success')).toBe(false)
    expect(card?.classList.contains('info-card--warning')).toBe(false)
    expect(card?.classList.contains('info-card--error')).toBe(false)
  })

  it('adds info-card--success class when variant="success"', () => {
    const { container } = render(
      <InfoCard title="Probe" variant="success">
        body
      </InfoCard>,
    )
    expect(container.querySelector('.info-card--success')).toBeInTheDocument()
  })

  it('adds info-card--warning class when variant="warning"', () => {
    const { container } = render(
      <InfoCard title="Probe" variant="warning">
        body
      </InfoCard>,
    )
    expect(container.querySelector('.info-card--warning')).toBeInTheDocument()
  })

  it('adds info-card--error class when variant="error"', () => {
    const { container } = render(
      <InfoCard title="Probe" variant="error">
        body
      </InfoCard>,
    )
    expect(container.querySelector('.info-card--error')).toBeInTheDocument()
  })

  it('renders as <button> with info-card--clickable when onClick provided', () => {
    render(
      <InfoCard title="Probe" onClick={vi.fn()}>
        body
      </InfoCard>,
    )
    const card = screen.getByRole('button', { name: 'Probe' })
    expect(card.tagName).toBe('BUTTON')
    expect(card.classList.contains('info-card--clickable')).toBe(true)
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(
      <InfoCard title="Probe" onClick={onClick}>
        body
      </InfoCard>,
    )
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('uses ariaLabel prop verbatim when provided', () => {
    render(
      <InfoCard title={<span>complex</span>} ariaLabel="Custom label" onClick={vi.fn()}>
        body
      </InfoCard>,
    )
    expect(screen.getByRole('button', { name: 'Custom label' })).toBeInTheDocument()
  })

  it('derives aria-label from string title when ariaLabel not provided', () => {
    const { container } = render(<InfoCard title="Direct title">body</InfoCard>)
    const card = container.querySelector('.info-card')
    expect(card?.getAttribute('aria-label')).toBe('Direct title')
  })

  it('omits aria-label when title is non-string and ariaLabel not provided', () => {
    const { container } = render(
      <InfoCard title={<span>complex</span>}>body</InfoCard>,
    )
    const card = container.querySelector('.info-card')
    expect(card?.getAttribute('aria-label')).toBeNull()
  })

  it('passes testId through to the rendered root', () => {
    render(
      <InfoCard title="Probe" testId="probe-card">
        body
      </InfoCard>,
    )
    expect(screen.getByTestId('probe-card')).toBeInTheDocument()
  })
})
