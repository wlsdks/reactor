import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { StepProgress, type StepDefinition } from '../StepProgress'

const STEPS: StepDefinition[] = [
  { id: 'configure', label: 'Configure' },
  { id: 'execute', label: 'Execute' },
  { id: 'inspect', label: 'Inspect' },
]

describe('StepProgress', () => {
  it('renders all steps as a labelled ordered list', () => {
    render(<StepProgress steps={STEPS} currentId="configure" ariaLabel="Wizard steps" />)
    const list = screen.getByRole('list', { name: 'Wizard steps' })
    expect(list).toBeInTheDocument()
    expect(list.tagName).toBe('OL')
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
  })

  it('marks the current step with aria-current="step"', () => {
    render(<StepProgress steps={STEPS} currentId="execute" />)
    const items = screen.getAllByRole('listitem')
    expect(items[0]).not.toHaveAttribute('aria-current')
    expect(items[1]).toHaveAttribute('aria-current', 'step')
    expect(items[2]).not.toHaveAttribute('aria-current')
  })

  it('applies done class to previous steps and active class to current', () => {
    const { container } = render(<StepProgress steps={STEPS} currentId="inspect" />)
    const items = container.querySelectorAll('.step-progress__item')
    expect(items[0]).toHaveClass('step-progress__item--done')
    expect(items[1]).toHaveClass('step-progress__item--done')
    expect(items[2]).toHaveClass('step-progress__item--active')
  })

  it('applies pending class to future steps', () => {
    const { container } = render(<StepProgress steps={STEPS} currentId="configure" />)
    const items = container.querySelectorAll('.step-progress__item')
    expect(items[0]).toHaveClass('step-progress__item--active')
    expect(items[1]).toHaveClass('step-progress__item--pending')
    expect(items[2]).toHaveClass('step-progress__item--pending')
  })

  it('calls onStep with the step id when a previous step is clicked', () => {
    const onStep = vi.fn()
    render(<StepProgress steps={STEPS} currentId="inspect" onStep={onStep} />)
    fireEvent.click(screen.getByTestId('step-progress-configure'))
    expect(onStep).toHaveBeenCalledWith('configure')
  })

  it('disables future-step buttons when not visited', () => {
    const onStep = vi.fn()
    render(<StepProgress steps={STEPS} currentId="configure" onStep={onStep} />)
    const futureBtn = screen.getByTestId('step-progress-inspect')
    expect(futureBtn).toBeDisabled()
    fireEvent.click(futureBtn)
    expect(onStep).not.toHaveBeenCalled()
  })

  it('enables future-step buttons explicitly listed in `visited`', () => {
    const onStep = vi.fn()
    render(
      <StepProgress
        steps={STEPS}
        currentId="configure"
        onStep={onStep}
        visited={new Set(['execute'])}
      />,
    )
    const visitedBtn = screen.getByTestId('step-progress-execute')
    expect(visitedBtn).not.toBeDisabled()
    fireEvent.click(visitedBtn)
    expect(onStep).toHaveBeenCalledWith('execute')
  })

  it('renders all step buttons disabled when no onStep handler is provided', () => {
    render(<StepProgress steps={STEPS} currentId="execute" />)
    expect(screen.getByTestId('step-progress-configure')).toBeDisabled()
    expect(screen.getByTestId('step-progress-execute')).toBeDisabled()
    expect(screen.getByTestId('step-progress-inspect')).toBeDisabled()
  })

  it('renders 1-based numeric index per step', () => {
    render(<StepProgress steps={STEPS} currentId="configure" />)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders step labels', () => {
    render(<StepProgress steps={STEPS} currentId="configure" />)
    expect(screen.getByText('Configure')).toBeInTheDocument()
    expect(screen.getByText('Execute')).toBeInTheDocument()
    expect(screen.getByText('Inspect')).toBeInTheDocument()
  })
})
