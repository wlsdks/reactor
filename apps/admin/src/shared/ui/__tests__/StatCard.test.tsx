import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { StatCard } from '../StatCard'

describe('StatCard', () => {
  it('renders label text in the stat-card-label element', () => {
    const { container } = render(<StatCard label="users" value={42} />)
    expect(container.querySelector('.stat-card-label')?.textContent).toBe('users')
  })

  it('renders numeric value', () => {
    render(<StatCard label="Count" value={99} />)
    expect(screen.getByText('99')).toBeInTheDocument()
  })

  it('renders string value', () => {
    render(<StatCard label="Status" value="Online" />)
    expect(screen.getByText('Online')).toBeInTheDocument()
  })

  it('renders sub text when provided', () => {
    render(<StatCard label="Memory" value="512MB" sub="of 2GB" />)
    expect(screen.getByText('of 2GB')).toBeInTheDocument()
  })

  it('does not render sub element when not provided', () => {
    const { container } = render(<StatCard label="Count" value={5} />)
    expect(container.querySelector('.stat-card-sub')).not.toBeInTheDocument()
  })

  it('renders icon element when icon prop is provided', () => {
    const { container } = render(<StatCard label="Sessions" value={10} icon={<span>SL</span>} />)
    expect(container.querySelector('.stat-card-icon')).toBeInTheDocument()
    expect(container.querySelector('.stat-card-icon')?.textContent).toBe('SL')
  })

  it('does not render icon element when not provided', () => {
    const { container } = render(<StatCard label="Count" value={5} />)
    expect(container.querySelector('.stat-card-icon')).not.toBeInTheDocument()
  })

  it('renders as div when no onClick', () => {
    render(<StatCard label="Issues" value={18} />)
    const card = screen.getByText('Issues').closest('.stat-card')
    expect(card?.tagName).toBe('DIV')
  })

  it('renders as button when onClick provided', () => {
    render(<StatCard label="Issues" value={18} onClick={vi.fn()} />)
    const card = screen.getByRole('button', { name: 'Issues' })
    expect(card).toBeInTheDocument()
  })

  it('calls onClick when clicked', () => {
    const onClick = vi.fn()
    render(<StatCard label="Issues" value={18} onClick={onClick} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('renders the change chip with the supplied baseline tooltip', () => {
    const { container } = render(
      <StatCard label="Sessions" value={120} change={12} changeBaselineLabel="어제 대비" />,
    )
    const chip = container.querySelector('.stat-card-change')
    expect(chip).not.toBeNull()
    expect(chip?.getAttribute('title')).toBe('어제 대비')
    expect(chip?.getAttribute('aria-label')).toBe('+12% 어제 대비')
  })

  it('omits the baseline caption by default', () => {
    render(<StatCard label="Sessions" value={120} change={12} changeBaselineLabel="어제 대비" />)
    expect(screen.queryByTestId('stat-card-baseline')).not.toBeInTheDocument()
  })

  it('renders the baseline caption when showBaselineCaption is true', () => {
    render(
      <StatCard
        label="Sessions"
        value={120}
        change={12}
        changeBaselineLabel="어제 대비"
        showBaselineCaption
      />,
    )
    const caption = screen.getByTestId('stat-card-baseline')
    expect(caption.textContent).toBe('어제 대비')
  })

  it('renders the value without the hero modifier class by default', () => {
    const { container } = render(<StatCard label="Sessions" value={120} />)
    const valueEl = container.querySelector('.stat-card-value')
    expect(valueEl).not.toBeNull()
    expect(valueEl?.classList.contains('stat-card-value--hero')).toBe(false)
  })

  it('adds the stat-card-value--hero class when tone="hero"', () => {
    const { container } = render(<StatCard label="Sessions" value={120} tone="hero" />)
    const valueEl = container.querySelector('.stat-card-value')
    expect(valueEl).not.toBeNull()
    expect(valueEl?.classList.contains('stat-card-value--hero')).toBe(true)
  })
})
