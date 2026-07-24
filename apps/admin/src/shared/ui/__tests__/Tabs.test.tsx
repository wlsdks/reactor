import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { Tabs, type TabDefinition } from '../Tabs'

const tabs: TabDefinition[] = [
  { value: 'a', label: 'Alpha', panel: <div>Panel A</div> },
  { value: 'b', label: 'Beta', panel: <div>Panel B</div> },
  { value: 'c', label: 'Gamma', panel: <div>Panel C</div> },
]

describe('Tabs', () => {
  it('renders tablist with aria-label and 3 tabs', () => {
    render(<Tabs tabs={tabs} value="a" onChange={() => {}} ariaLabel="Test tabs" />)
    expect(screen.getByRole('tablist')).toHaveAttribute('aria-label', 'Test tabs')
    expect(screen.getAllByRole('tab')).toHaveLength(3)
  })

  it('marks the active tab with aria-selected and tabIndex 0', () => {
    render(<Tabs tabs={tabs} value="b" onChange={() => {}} ariaLabel="t" />)
    const beta = screen.getByRole('tab', { name: 'Beta' })
    expect(beta).toHaveAttribute('aria-selected', 'true')
    expect(beta).toHaveAttribute('tabindex', '0')

    const alpha = screen.getByRole('tab', { name: 'Alpha' })
    expect(alpha).toHaveAttribute('aria-selected', 'false')
    expect(alpha).toHaveAttribute('tabindex', '-1')
  })

  it('renders only the active tabpanel content', () => {
    render(<Tabs tabs={tabs} value="b" onChange={() => {}} ariaLabel="t" />)
    expect(screen.queryByText('Panel A')).not.toBeInTheDocument()
    expect(screen.getByText('Panel B')).toBeInTheDocument()
    expect(screen.queryByText('Panel C')).not.toBeInTheDocument()
  })

  it('connects tab to tabpanel via aria-controls and aria-labelledby', () => {
    render(<Tabs tabs={tabs} value="a" onChange={() => {}} ariaLabel="t" />)
    const alphaTab = screen.getByRole('tab', { name: 'Alpha' })
    expect(alphaTab).toHaveAttribute('aria-controls', 'tabpanel-a')
    expect(alphaTab).toHaveAttribute('id', 'tab-a')

    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('id', 'tabpanel-a')
    expect(panel).toHaveAttribute('aria-labelledby', 'tab-a')
  })

  it('calls onChange when a tab is clicked', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="a" onChange={onChange} ariaLabel="t" />)
    fireEvent.click(screen.getByRole('tab', { name: 'Beta' }))
    expect(onChange).toHaveBeenCalledWith('b')
  })

  it('ArrowRight moves to next tab', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="a" onChange={onChange} ariaLabel="t" />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Alpha' }), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith('b')
  })

  it('ArrowRight from last wraps to first', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="c" onChange={onChange} ariaLabel="t" />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Gamma' }), { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it('ArrowLeft from first wraps to last', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="a" onChange={onChange} ariaLabel="t" />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Alpha' }), { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenCalledWith('c')
  })

  it('Home key jumps to first tab', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="c" onChange={onChange} ariaLabel="t" />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Gamma' }), { key: 'Home' })
    expect(onChange).toHaveBeenCalledWith('a')
  })

  it('End key jumps to last tab', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="a" onChange={onChange} ariaLabel="t" />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Alpha' }), { key: 'End' })
    expect(onChange).toHaveBeenCalledWith('c')
  })

  it('ignores other keys', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} value="a" onChange={onChange} ariaLabel="t" />)
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Alpha' }), { key: 'Enter' })
    expect(onChange).not.toHaveBeenCalled()
  })
})
