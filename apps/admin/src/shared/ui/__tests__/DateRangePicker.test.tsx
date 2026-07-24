import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { DateRangePicker } from '../DateRangePicker'
import type { DateRange } from '../DateRangePicker'

describe('DateRangePicker', () => {
  const NOW = 1700000000000
  let dateSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    dateSpy = vi.spyOn(Date, 'now').mockReturnValue(NOW)
  })

  afterEach(() => {
    dateSpy.mockRestore()
  })

  const defaultRange: DateRange = {
    from: NOW - 24 * 60 * 60 * 1000,
    to: NOW,
  }

  it('renders preset buttons', () => {
    render(<DateRangePicker value={defaultRange} onChange={vi.fn()} />)
    expect(screen.getByText('24h')).toBeInTheDocument()
    expect(screen.getByText('7d')).toBeInTheDocument()
    expect(screen.getByText('30d')).toBeInTheDocument()
    expect(screen.getByText('90d')).toBeInTheDocument()
  })

  it('renders only specified presets', () => {
    render(
      <DateRangePicker value={defaultRange} onChange={vi.fn()} presets={['24h', '7d']} />,
    )
    expect(screen.getByText('24h')).toBeInTheDocument()
    expect(screen.getByText('7d')).toBeInTheDocument()
    expect(screen.queryByText('30d')).not.toBeInTheDocument()
    expect(screen.queryByText('90d')).not.toBeInTheDocument()
  })

  it('applies active-filter class to matching preset', () => {
    render(<DateRangePicker value={defaultRange} onChange={vi.fn()} />)
    expect(screen.getByText('24h').classList.contains('active-filter')).toBe(true)
    expect(screen.getByText('7d').classList.contains('active-filter')).toBe(false)
  })

  it('calls onChange with correct range for 7d preset', () => {
    const onChange = vi.fn()
    render(<DateRangePicker value={defaultRange} onChange={onChange} />)
    fireEvent.click(screen.getByText('7d'))
    expect(onChange).toHaveBeenCalledWith({
      from: NOW - 7 * 24 * 60 * 60 * 1000,
      to: NOW,
    })
  })

  it('calls onChange with correct range for 30d preset', () => {
    const onChange = vi.fn()
    render(<DateRangePicker value={defaultRange} onChange={onChange} />)
    fireEvent.click(screen.getByText('30d'))
    expect(onChange).toHaveBeenCalledWith({
      from: NOW - 30 * 24 * 60 * 60 * 1000,
      to: NOW,
    })
  })

  it('shows custom date inputs when no preset matches', () => {
    const customRange: DateRange = {
      from: NOW - 5 * 24 * 60 * 60 * 1000,
      to: NOW - 2 * 24 * 60 * 60 * 1000,
    }
    render(<DateRangePicker value={customRange} onChange={vi.fn()} />)
    const fromInput = screen.getByLabelText('dateRange.from')
    const toInput = screen.getByLabelText('dateRange.to')
    expect(fromInput).toBeInTheDocument()
    expect(toInput).toBeInTheDocument()
  })

  it('hides custom inputs when a preset matches', () => {
    render(<DateRangePicker value={defaultRange} onChange={vi.fn()} />)
    expect(screen.queryByLabelText('dateRange.from')).not.toBeInTheDocument()
  })

  it('has accessible group role', () => {
    render(<DateRangePicker value={defaultRange} onChange={vi.fn()} />)
    expect(screen.getByRole('group')).toBeInTheDocument()
  })

  it('hides custom inputs when custom is not in presets', () => {
    const customRange: DateRange = {
      from: NOW - 5 * 24 * 60 * 60 * 1000,
      to: NOW - 2 * 24 * 60 * 60 * 1000,
    }
    render(
      <DateRangePicker
        value={customRange}
        onChange={vi.fn()}
        presets={['24h', '7d']}
      />,
    )
    expect(screen.queryByLabelText('dateRange.from')).not.toBeInTheDocument()
  })
})
