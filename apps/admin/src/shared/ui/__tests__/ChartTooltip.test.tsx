import { describe, it, expect } from 'vitest'
import { render, screen } from '../../../test/utils'
import { ChartTooltip } from '../ChartTooltip'

describe('ChartTooltip', () => {
  it('renders nothing when not active', () => {
    const { container } = render(
      <ChartTooltip active={false} payload={[]} label="Test" />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when active but payload is empty', () => {
    const { container } = render(
      <ChartTooltip active={true} payload={[]} label="Test" />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when active but payload is undefined', () => {
    const { container } = render(
      <ChartTooltip active={true} payload={undefined} label="Test" />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders tooltip content with label and payload', () => {
    const payload = [
      { name: 'Users', value: 1500, color: '#34D399' },
      { name: 'Sessions', value: 3200, color: '#60A5FA' },
    ]
    render(
      <ChartTooltip active={true} payload={payload} label="Jan 2026" />,
    )
    expect(screen.getByText('Jan 2026')).toBeInTheDocument()
    expect(screen.getByText('Users')).toBeInTheDocument()
    expect(screen.getByText('Sessions')).toBeInTheDocument()
    // 1500 -> 1.5K, 3200 -> 3.2K (formatNumber)
    expect(screen.getByText('1.5K')).toBeInTheDocument()
    expect(screen.getByText('3.2K')).toBeInTheDocument()
  })

  it('renders without label when label is not provided', () => {
    const payload = [
      { name: 'Revenue', value: 500, color: '#E0B85A' },
    ]
    const { container } = render(
      <ChartTooltip active={true} payload={payload} />,
    )
    expect(container.querySelector('.chart-tooltip-label')).not.toBeInTheDocument()
    expect(screen.getByText('Revenue')).toBeInTheDocument()
  })

  it('uses custom formatValue function when provided', () => {
    const payload = [
      { name: 'CPU', value: 0.85, color: '#F87171' },
    ]
    const customFormat = (v: number) => `${(v * 100).toFixed(0)}%`
    render(
      <ChartTooltip
        active={true}
        payload={payload}
        label="Server A"
        formatValue={customFormat}
      />,
    )
    expect(screen.getByText('85%')).toBeInTheDocument()
  })

  it('uses default formatNumber when no formatValue is provided', () => {
    const payload = [
      { name: 'Requests', value: 2500000, color: '#60A5FA' },
    ]
    render(
      <ChartTooltip active={true} payload={payload} label="Feb" />,
    )
    // 2500000 -> 2.5M
    expect(screen.getByText('2.5M')).toBeInTheDocument()
  })

  it('renders small numbers without K/M suffix', () => {
    const payload = [
      { name: 'Errors', value: 42, color: '#F87171' },
    ]
    render(
      <ChartTooltip active={true} payload={payload} label="Today" />,
    )
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders color dots matching entry colors', () => {
    const payload = [
      { name: 'Alpha', value: 100, color: '#FF0000' },
      { name: 'Beta', value: 200, color: '#00FF00' },
    ]
    const { container } = render(
      <ChartTooltip active={true} payload={payload} label="Test" />,
    )
    const dots = container.querySelectorAll('.chart-tooltip-dot')
    expect(dots).toHaveLength(2)
    expect((dots[0] as HTMLElement).style.background).toBe('rgb(255, 0, 0)')
    expect((dots[1] as HTMLElement).style.background).toBe('rgb(0, 255, 0)')
  })

  it('renders multiple rows for multi-series data', () => {
    const payload = [
      { name: 'Series A', value: 10, color: '#AAA' },
      { name: 'Series B', value: 20, color: '#BBB' },
      { name: 'Series C', value: 30, color: '#CCC' },
    ]
    const { container } = render(
      <ChartTooltip active={true} payload={payload} label="Multi" />,
    )
    const rows = container.querySelectorAll('.chart-tooltip-row')
    expect(rows).toHaveLength(3)
  })
})
