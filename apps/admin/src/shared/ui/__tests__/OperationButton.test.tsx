import { createRef } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { OperationButton } from '../OperationButton'

describe('OperationButton', () => {
  it('renders children when not operating', () => {
    render(<OperationButton>Save</OperationButton>)
    const btn = screen.getByRole('button', { name: 'Save' })
    expect(btn).toBeInTheDocument()
    expect(btn).not.toBeDisabled()
    expect(btn).not.toHaveAttribute('aria-busy')
    expect(btn.querySelector('.spinner')).toBeNull()
  })

  it('sets aria-busy and disabled, renders spinner with translated label when operating', () => {
    render(<OperationButton isOperating>Save</OperationButton>)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).toHaveAttribute('aria-busy', 'true')
    expect(btn.querySelector('.spinner')).not.toBeNull()
    // Default loading label uses common.processing
    expect(btn).toHaveTextContent('Processing...')
    // Children are NOT shown while operating (spinner + loadingLabel replace them)
    expect(btn).not.toHaveTextContent('Save')
  })

  it('honours custom loadingLabel for screen-reader announcement', () => {
    render(
      <OperationButton isOperating loadingLabel="Saving job…">
        Save
      </OperationButton>,
    )
    const btn = screen.getByRole('button')
    expect(btn).toHaveTextContent('Saving job…')
    expect(btn.querySelector('.spinner')).not.toBeNull()
  })

  it('forwards ref to the underlying button element', () => {
    const ref = createRef<HTMLButtonElement>()
    render(<OperationButton ref={ref}>Save</OperationButton>)
    expect(ref.current).toBeInstanceOf(HTMLButtonElement)
    expect(ref.current?.textContent).toBe('Save')
  })

  it('applies the requested variant class', () => {
    const { rerender } = render(
      <OperationButton variant="primary">Primary</OperationButton>,
    )
    expect(screen.getByRole('button')).toHaveClass('btn', 'btn-primary')

    rerender(<OperationButton variant="secondary">Secondary</OperationButton>)
    expect(screen.getByRole('button')).toHaveClass('btn-secondary')

    rerender(<OperationButton variant="danger">Danger</OperationButton>)
    expect(screen.getByRole('button')).toHaveClass('btn-danger')

    rerender(<OperationButton variant="ghost">Ghost</OperationButton>)
    expect(screen.getByRole('button')).toHaveClass('btn-ghost')
  })

  it('defaults to primary variant', () => {
    render(<OperationButton>Default</OperationButton>)
    expect(screen.getByRole('button')).toHaveClass('btn-primary')
  })

  it('adds btn--operating class only while operating', () => {
    const { rerender } = render(<OperationButton>Idle</OperationButton>)
    expect(screen.getByRole('button')).not.toHaveClass('btn--operating')

    rerender(<OperationButton isOperating>Idle</OperationButton>)
    expect(screen.getByRole('button')).toHaveClass('btn--operating')
  })

  it('plain disabled state does not show spinner and is not aria-busy', () => {
    render(<OperationButton disabled>Save</OperationButton>)
    const btn = screen.getByRole('button')
    expect(btn).toBeDisabled()
    expect(btn).not.toHaveAttribute('aria-busy')
    expect(btn.querySelector('.spinner')).toBeNull()
    expect(btn).toHaveTextContent('Save')
  })

  it('disabled OR isOperating disables the button', () => {
    const { rerender } = render(
      <OperationButton disabled={false} isOperating={false}>
        Save
      </OperationButton>,
    )
    expect(screen.getByRole('button')).not.toBeDisabled()

    rerender(
      <OperationButton disabled isOperating={false}>
        Save
      </OperationButton>,
    )
    expect(screen.getByRole('button')).toBeDisabled()

    rerender(
      <OperationButton disabled={false} isOperating>
        Save
      </OperationButton>,
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('does not invoke onClick while operating (button is disabled)', () => {
    const onClick = vi.fn()
    render(
      <OperationButton isOperating onClick={onClick}>
        Save
      </OperationButton>,
    )
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('invokes onClick when idle', () => {
    const onClick = vi.fn()
    render(<OperationButton onClick={onClick}>Save</OperationButton>)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('defaults type to "button" but respects explicit type="submit"', () => {
    const { rerender } = render(<OperationButton>Default</OperationButton>)
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button')

    rerender(<OperationButton type="submit">Submit</OperationButton>)
    expect(screen.getByRole('button')).toHaveAttribute('type', 'submit')
  })

  it('preserves additional className alongside variant classes', () => {
    render(
      <OperationButton className="btn-sm">
        Small
      </OperationButton>,
    )
    const btn = screen.getByRole('button')
    expect(btn).toHaveClass('btn', 'btn-primary', 'btn-sm')
  })

  it('forwards arbitrary HTML button attributes (title, data-*, aria-*)', () => {
    render(
      <OperationButton
        title="Save tooltip"
        data-testid="save-btn"
        aria-label="Save row"
      >
        Save
      </OperationButton>,
    )
    const btn = screen.getByTestId('save-btn')
    expect(btn).toHaveAttribute('title', 'Save tooltip')
    expect(btn).toHaveAttribute('aria-label', 'Save row')
  })
})
