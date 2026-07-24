import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '../../../test/utils'
import { ConfirmDialog } from '../ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders title and message', () => {
    render(
      <ConfirmDialog
        title="Delete Item"
        message="Are you sure you want to delete this item?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByText(/Delete Item/)).toBeInTheDocument()
    expect(screen.getByText('Are you sure you want to delete this item?')).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button is clicked', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        title="Confirm Action"
        message="Sure?"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /confirm/i }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Confirm Action"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('does NOT call onCancel when backdrop is clicked by default', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Confirm"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    // Default contract: confirm dialogs require an explicit choice
    fireEvent.click(document.body.querySelector('.modal-overlay')!)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('calls onCancel on backdrop click when closeOnBackdrop=true', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Confirm"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
        closeOnBackdrop
      />,
    )
    fireEvent.click(document.body.querySelector('.modal-overlay')!)
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onCancel when Escape is pressed', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Confirm"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onCancel when overlay close button (×) is clicked', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Confirm"
        message="Sure?"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('applies btn-danger class when danger prop is true', () => {
    render(
      <ConfirmDialog
        title="Delete"
        message="Delete?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        danger
      />,
    )
    const confirmBtn = document.body.querySelector('.btn-danger')
    expect(confirmBtn).toBeInTheDocument()
  })

  it('applies btn-primary class by default', () => {
    render(
      <ConfirmDialog
        title="Action"
        message="Proceed?"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const confirmBtn = document.body.querySelector('.btn-primary')
    expect(confirmBtn).toBeInTheDocument()
  })

  it('does not propagate click from inner modal content', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog
        title="Action"
        message="Content here"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    )
    const dialog = screen.getByRole('dialog')
    fireEvent.click(dialog)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('renders with correct ARIA attributes (role + modal + labelledby points to title)', () => {
    render(
      <ConfirmDialog
        title="Accessible Dialog"
        message="Test ARIA"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    const labelledby = dialog.getAttribute('aria-labelledby')
    expect(labelledby).toBeTruthy()
    const titleEl = document.getElementById(labelledby!)
    expect(titleEl).not.toBeNull()
    expect(titleEl!.textContent).toBe('Accessible Dialog')
  })

  it('renders message text in modal body', () => {
    render(
      <ConfirmDialog
        title="Title"
        message="Detailed explanation of the action"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    const message = document.body.querySelector('.modal-message')
    expect(message).toBeInTheDocument()
    expect(message!.textContent).toBe('Detailed explanation of the action')
  })

  it('restores focus to the previously focused element after unmount', () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Open'
    document.body.appendChild(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    const { unmount } = render(
      <ConfirmDialog
        title="T"
        message="M"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    // Focus moved into the dialog
    expect(document.activeElement).not.toBe(trigger)

    unmount()
    expect(document.activeElement).toBe(trigger)
    document.body.removeChild(trigger)
  })

  describe('confirmText (type-to-confirm guard)', () => {
    it('confirm button is enabled immediately when confirmText is not provided', () => {
      render(
        <ConfirmDialog
          title="No guard"
          message="Plain confirm"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />,
      )
      const confirmBtn = screen.getByRole('button', { name: /confirm/i })
      expect(confirmBtn).not.toBeDisabled()
    })

    it('confirm button is disabled until typed value matches confirmText exactly', () => {
      const onConfirm = vi.fn()
      render(
        <ConfirmDialog
          title="Delete resource"
          message="Type the resource name to proceed"
          onConfirm={onConfirm}
          onCancel={vi.fn()}
          danger
          confirmText="prod-payments"
        />,
      )
      const confirmBtn = screen.getByRole('button', { name: /confirm/i })
      expect(confirmBtn).toBeDisabled()

      const input = screen.getByRole('textbox')
      // Mismatched value keeps it disabled
      fireEvent.change(input, { target: { value: 'prod-payment' } })
      expect(confirmBtn).toBeDisabled()
      fireEvent.click(confirmBtn)
      expect(onConfirm).not.toHaveBeenCalled()
    })

    it('enables confirm and calls onConfirm when typed value matches', () => {
      const onConfirm = vi.fn()
      render(
        <ConfirmDialog
          title="Delete resource"
          message="Type the resource name to proceed"
          onConfirm={onConfirm}
          onCancel={vi.fn()}
          danger
          confirmText="prod-payments"
        />,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'prod-payments' } })

      const confirmBtn = screen.getByRole('button', { name: /confirm/i })
      expect(confirmBtn).not.toBeDisabled()
      fireEvent.click(confirmBtn)
      expect(onConfirm).toHaveBeenCalledOnce()
    })

    it('ignores surrounding whitespace when comparing typed value', () => {
      render(
        <ConfirmDialog
          title="Reset policy"
          message="Type RESET to confirm"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          danger
          confirmText="RESET"
        />,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '  RESET  ' } })
      expect(screen.getByRole('button', { name: /confirm/i })).not.toBeDisabled()
    })

    it('submits via Enter key when typed value matches', () => {
      const onConfirm = vi.fn()
      render(
        <ConfirmDialog
          title="Invalidate"
          message="Type INVALIDATE to confirm"
          onConfirm={onConfirm}
          onCancel={vi.fn()}
          danger
          confirmText="INVALIDATE"
        />,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'INVALIDATE' } })
      fireEvent.keyDown(input, { key: 'Enter' })
      expect(onConfirm).toHaveBeenCalledOnce()
    })

    it('does NOT submit via Enter key when typed value does not match', () => {
      const onConfirm = vi.fn()
      render(
        <ConfirmDialog
          title="Invalidate"
          message="Type INVALIDATE to confirm"
          onConfirm={onConfirm}
          onCancel={vi.fn()}
          danger
          confirmText="INVALIDATE"
        />,
      )
      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'invalidate' } })
      fireEvent.keyDown(input, { key: 'Enter' })
      expect(onConfirm).not.toHaveBeenCalled()
    })

    it('resets typed value when the dialog is unmounted and remounted', () => {
      const { unmount } = render(
        <ConfirmDialog
          title="Reset"
          message="Type RESET"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          confirmText="RESET"
        />,
      )
      const input = screen.getByRole('textbox') as HTMLInputElement
      fireEvent.change(input, { target: { value: 'RESET' } })
      expect(input.value).toBe('RESET')
      unmount()

      render(
        <ConfirmDialog
          title="Reset"
          message="Type RESET"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          confirmText="RESET"
        />,
      )
      const newInput = screen.getByRole('textbox') as HTMLInputElement
      expect(newInput.value).toBe('')
      expect(screen.getByRole('button', { name: /confirm/i })).toBeDisabled()
    })

    it('marks the input as aria-required and reflects aria-invalid until matching', () => {
      render(
        <ConfirmDialog
          title="Delete"
          message="Type token"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          danger
          confirmText="TOKEN"
        />,
      )
      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('aria-required', 'true')
      expect(input).toHaveAttribute('aria-invalid', 'true')
      fireEvent.change(input, { target: { value: 'TOKEN' } })
      expect(input).toHaveAttribute('aria-invalid', 'false')
    })

    it('uses confirmTextLabel when provided instead of the default label', () => {
      render(
        <ConfirmDialog
          title="Delete"
          message="Custom label"
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
          danger
          confirmText="my-key"
          confirmTextLabel="Type the setting key to confirm"
        />,
      )
      expect(screen.getByText(/Type the setting key to confirm/)).toBeInTheDocument()
    })

    it('treats empty confirmText as "no guard required"', () => {
      const onConfirm = vi.fn()
      render(
        <ConfirmDialog
          title="No guard"
          message="Empty token"
          onConfirm={onConfirm}
          onCancel={vi.fn()}
          confirmText=""
        />,
      )
      const confirmBtn = screen.getByRole('button', { name: /confirm/i })
      expect(confirmBtn).not.toBeDisabled()
      fireEvent.click(confirmBtn)
      expect(onConfirm).toHaveBeenCalledOnce()
    })
  })
})
