import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { NumberInputStepper } from '../NumberInputStepper'

function getInput(): HTMLInputElement {
  return screen.getByRole('spinbutton') as HTMLInputElement
}

function getDecrement(): HTMLButtonElement {
  return screen.getByLabelText('common.numberStepper.decrementAria') as HTMLButtonElement
}

function getIncrement(): HTMLButtonElement {
  return screen.getByLabelText('common.numberStepper.incrementAria') as HTMLButtonElement
}

describe('NumberInputStepper', () => {
  it('increments and decrements by step on button click', () => {
    const onChange = vi.fn()
    render(<NumberInputStepper value={5} onChange={onChange} step={1} />)

    fireEvent.click(getIncrement())
    expect(onChange).toHaveBeenLastCalledWith(6)

    fireEvent.click(getDecrement())
    expect(onChange).toHaveBeenLastCalledWith(4)
  })

  it('uses shared line icons instead of text symbols for adjustments', () => {
    render(<NumberInputStepper value={5} onChange={() => {}} />)

    expect(getDecrement().querySelector('svg.lucide-minus')).toBeInTheDocument()
    expect(getIncrement().querySelector('svg.lucide-plus')).toBeInTheDocument()
    expect(getDecrement()).not.toHaveTextContent('−')
    expect(getIncrement()).not.toHaveTextContent('+')
    expect(getDecrement()).toHaveStyle({
      width: 'var(--control-height-default)',
      height: 'var(--control-height-default)',
    })
    expect(getDecrement().querySelector('svg.lucide-minus')).toHaveAttribute('width', 'var(--icon-size-sm)')
    expect(getIncrement().querySelector('svg.lucide-plus')).toHaveAttribute('height', 'var(--icon-size-sm)')
  })

  it('clamps value to min and max boundaries', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <NumberInputStepper value={1} onChange={onChange} min={0} max={10} step={5} />,
    )

    // Clicking + with value=1 step=5 max=10 produces 6 (within range).
    fireEvent.click(getIncrement())
    expect(onChange).toHaveBeenLastCalledWith(6)

    // From value=8 with step=5 → 13, clamped to 10.
    rerender(<NumberInputStepper value={8} onChange={onChange} min={0} max={10} step={5} />)
    fireEvent.click(getIncrement())
    expect(onChange).toHaveBeenLastCalledWith(10)

    // From value=2 step=5 going down → -3, clamped to 0.
    rerender(<NumberInputStepper value={2} onChange={onChange} min={0} max={10} step={5} />)
    fireEvent.click(getDecrement())
    expect(onChange).toHaveBeenLastCalledWith(0)
  })

  it('disables decrement at min and increment at max', () => {
    const onChange = vi.fn()
    const { rerender } = render(
      <NumberInputStepper value={0} onChange={onChange} min={0} max={10} />,
    )
    expect(getDecrement()).toBeDisabled()
    expect(getIncrement()).not.toBeDisabled()

    rerender(<NumberInputStepper value={10} onChange={onChange} min={0} max={10} />)
    expect(getIncrement()).toBeDisabled()
    expect(getDecrement()).not.toBeDisabled()
  })

  it('adjusts value via ArrowUp / ArrowDown keys', () => {
    const onChange = vi.fn()
    render(<NumberInputStepper value={10} onChange={onChange} step={2} />)

    fireEvent.keyDown(getInput(), { key: 'ArrowUp' })
    expect(onChange).toHaveBeenLastCalledWith(12)

    fireEvent.keyDown(getInput(), { key: 'ArrowDown' })
    expect(onChange).toHaveBeenLastCalledWith(8)
  })

  it('multiplies adjustment by 10 when Shift is held', () => {
    const onChange = vi.fn()
    render(<NumberInputStepper value={100} onChange={onChange} step={5} />)

    fireEvent.keyDown(getInput(), { key: 'ArrowUp', shiftKey: true })
    expect(onChange).toHaveBeenLastCalledWith(150)

    fireEvent.keyDown(getInput(), { key: 'ArrowDown', shiftKey: true })
    expect(onChange).toHaveBeenLastCalledWith(50)
  })

  it('renders the suffix when provided', () => {
    render(<NumberInputStepper value={30} onChange={() => {}} suffix="초" />)
    expect(screen.getByText('초')).toBeInTheDocument()
  })

  it('emits parsed numeric value on input change', () => {
    const onChange = vi.fn()
    const { rerender } = render(<NumberInputStepper value={null} onChange={onChange} />)

    fireEvent.change(getInput(), { target: { value: '42' } })
    expect(onChange).toHaveBeenLastCalledWith(42)

    // Mirror parent state update so the controlled input reflects 42.
    rerender(<NumberInputStepper value={42} onChange={onChange} />)
    fireEvent.change(getInput(), { target: { value: '' } })
    expect(onChange).toHaveBeenLastCalledWith(null)
  })

  it('rounds to derived precision when step has decimals', () => {
    const onChange = vi.fn()
    render(<NumberInputStepper value={1} onChange={onChange} step={0.1} />)

    fireEvent.click(getIncrement())
    // 1 + 0.1 floats to 1.1, which we expect rounded clean.
    expect(onChange).toHaveBeenLastCalledWith(1.1)
  })

  it('does not adjust when disabled', () => {
    const onChange = vi.fn()
    render(<NumberInputStepper value={5} onChange={onChange} disabled />)

    expect(getIncrement()).toBeDisabled()
    expect(getDecrement()).toBeDisabled()
    fireEvent.click(getIncrement())
    expect(onChange).not.toHaveBeenCalled()
  })
})
