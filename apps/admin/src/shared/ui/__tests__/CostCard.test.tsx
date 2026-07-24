import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '../../../test/utils'
import { CostCard } from '../CostCard'
import { budgetSeverity } from '../CostCard.utils'

describe('CostCard', () => {
  it('renders label and formatted USD value', () => {
    render(<CostCard label="오늘 비용" value={42.5} />)
    expect(screen.getByText('오늘 비용')).toBeInTheDocument()
    expect(screen.getByTestId('cost-card-value').textContent).toBe('$42.50')
  })

  it('renders sub-dollar values with 4 decimal precision', () => {
    render(<CostCard label="비용" value={0.0123} />)
    expect(screen.getByTestId('cost-card-value').textContent).toBe('$0.0123')
  })

  it('renders zero / non-finite as $0.00', () => {
    render(<CostCard label="비용" value={0} />)
    expect(screen.getByTestId('cost-card-value').textContent).toBe('$0.00')
  })

  it('renders trend chip with success class when delta < 0', () => {
    render(
      <CostCard
        label="비용"
        value={10}
        trend={{ delta: -5.2, period: '어제 대비' }}
      />,
    )
    const chip = screen.getByTestId('cost-card-trend')
    expect(chip.className).toContain('cost-card__trend--success')
    expect(chip.textContent).toContain('-5.2%')
    expect(chip.textContent).toContain('어제 대비')
  })

  it('renders trend chip with error class when delta > 0', () => {
    render(
      <CostCard
        label="비용"
        value={10}
        trend={{ delta: 12.3, period: '어제 대비' }}
      />,
    )
    const chip = screen.getByTestId('cost-card-trend')
    expect(chip.className).toContain('cost-card__trend--error')
    expect(chip.textContent).toContain('+12.3%')
  })

  it('renders trend chip with neutral class when delta === 0', () => {
    render(
      <CostCard
        label="비용"
        value={10}
        trend={{ delta: 0, period: '어제 대비' }}
      />,
    )
    const chip = screen.getByTestId('cost-card-trend')
    expect(chip.className).toContain('cost-card__trend--neutral')
  })

  it('does not render trend chip when no trend prop', () => {
    render(<CostCard label="비용" value={10} />)
    expect(screen.queryByTestId('cost-card-trend')).not.toBeInTheDocument()
  })

  it('shows token tooltip on hover when tokens prop provided', () => {
    render(
      <CostCard
        label="비용"
        value={10}
        tokens={{ input: 1234, output: 5678 }}
      />,
    )
    const value = screen.getByTestId('cost-card-value')
    fireEvent.mouseEnter(value.parentElement!)
    // Tooltip element appears (text content depends on i18n resource bundle —
    // we only assert the tooltip is rendered and the role is correct).
    const tip = screen.getByTestId('cost-card-tooltip')
    expect(tip).toBeInTheDocument()
    expect(tip.getAttribute('role')).toBe('tooltip')
  })

  it('hides token tooltip when not hovered', () => {
    render(
      <CostCard
        label="비용"
        value={10}
        tokens={{ input: 1, output: 2 }}
      />,
    )
    expect(screen.queryByTestId('cost-card-tooltip')).not.toBeInTheDocument()
  })

  it('renders budget bar with success color when usage < 50%', () => {
    render(
      <CostCard
        label="비용"
        value={20}
        budget={{ used: 20, limit: 100 }}
      />,
    )
    const fill = screen.getByTestId('cost-card-budget-fill')
    expect(fill.getAttribute('data-severity')).toBe('success')
    expect(fill.style.width).toBe('20%')
  })

  it('renders budget bar with warning color when usage >= 50% and < 80%', () => {
    render(
      <CostCard
        label="비용"
        value={60}
        budget={{ used: 60, limit: 100 }}
      />,
    )
    const fill = screen.getByTestId('cost-card-budget-fill')
    expect(fill.getAttribute('data-severity')).toBe('warning')
    expect(fill.style.width).toBe('60%')
  })

  it('renders budget bar with error color when usage >= 80%', () => {
    render(
      <CostCard
        label="비용"
        value={90}
        budget={{ used: 90, limit: 100 }}
      />,
    )
    const fill = screen.getByTestId('cost-card-budget-fill')
    expect(fill.getAttribute('data-severity')).toBe('error')
    expect(fill.style.width).toBe('90%')
  })

  it('clamps budget bar to 100% when usage exceeds limit', () => {
    render(
      <CostCard
        label="비용"
        value={150}
        budget={{ used: 150, limit: 100 }}
      />,
    )
    const fill = screen.getByTestId('cost-card-budget-fill')
    expect(fill.style.width).toBe('100%')
    expect(fill.getAttribute('data-severity')).toBe('error')
  })

  it('does not render budget bar when no budget prop', () => {
    render(<CostCard label="비용" value={10} />)
    expect(screen.queryByTestId('cost-card-budget')).not.toBeInTheDocument()
  })

  it('renders as button when onClick provided and fires onClick', () => {
    const onClick = vi.fn()
    render(<CostCard label="비용" value={10} onClick={onClick} />)
    const btn = screen.getByRole('button')
    fireEvent.click(btn)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('renders as div when no onClick', () => {
    const { container } = render(<CostCard label="비용" value={10} />)
    expect(container.querySelector('button')).toBeNull()
    expect(container.querySelector('.cost-card')?.tagName).toBe('DIV')
  })
})

describe('budgetSeverity', () => {
  it('returns success below 50%', () => {
    expect(budgetSeverity(0)).toBe('success')
    expect(budgetSeverity(0.49)).toBe('success')
  })

  it('returns warning between 50% and 80%', () => {
    expect(budgetSeverity(0.5)).toBe('warning')
    expect(budgetSeverity(0.79)).toBe('warning')
  })

  it('returns error at or above 80%', () => {
    expect(budgetSeverity(0.8)).toBe('error')
    expect(budgetSeverity(1)).toBe('error')
  })
})
