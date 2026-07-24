import { render, screen, fireEvent } from '../../../test/utils'
import { describe, it, expect, vi } from 'vitest'
import { ToggleSwitch } from '../ToggleSwitch'

describe('ToggleSwitch', () => {
  it('renders as switch role', () => {
    render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    expect(screen.getByRole('switch')).toBeInTheDocument()
  })

  it('shows checked state', () => {
    render(<ToggleSwitch checked={true} onChange={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true')
  })

  it('shows unchecked state', () => {
    render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false')
  })

  it('calls onChange on click', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={false} onChange={onChange} />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('calls onChange on Space key', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={true} onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('switch'), { key: ' ' })
    expect(onChange).toHaveBeenCalledWith(false)
  })

  it('respects disabled state', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={false} onChange={onChange} disabled />)
    fireEvent.click(screen.getByRole('switch'))
    expect(onChange).not.toHaveBeenCalled()
    expect(screen.getByRole('switch')).toBeDisabled()
  })

  it('calls onChange on Enter key', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={false} onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('switch'), { key: 'Enter' })
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('does not call onChange on Enter key when disabled', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={false} onChange={onChange} disabled />)
    fireEvent.keyDown(screen.getByRole('switch'), { key: 'Enter' })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does not call onChange on Space key when disabled', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={true} onChange={onChange} disabled />)
    fireEvent.keyDown(screen.getByRole('switch'), { key: ' ' })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('does not call onChange on non-trigger keys', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={false} onChange={onChange} />)
    fireEvent.keyDown(screen.getByRole('switch'), { key: 'Tab' })
    expect(onChange).not.toHaveBeenCalled()
  })

  it('renders aria-label when label prop is provided', () => {
    render(<ToggleSwitch checked={false} onChange={vi.fn()} label="Enable feature" />)
    expect(screen.getByRole('switch')).toHaveAttribute('aria-label', 'Enable feature')
  })

  it('applies toggle-switch-on class when checked', () => {
    render(<ToggleSwitch checked={true} onChange={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveClass('toggle-switch-on')
  })

  it('applies toggle-switch-off class when unchecked', () => {
    render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    expect(screen.getByRole('switch')).toHaveClass('toggle-switch-off')
  })

  it('renders toggle-switch-thumb span', () => {
    const { container } = render(<ToggleSwitch checked={false} onChange={vi.fn()} />)
    expect(container.querySelector('.toggle-switch-thumb')).toBeInTheDocument()
  })
})
