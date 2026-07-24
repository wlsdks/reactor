import { render, screen, fireEvent } from '../../../test/utils'
import { describe, it, expect, vi } from 'vitest'
import { DetailModal } from '../DetailModal'

describe('DetailModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <DetailModal open={false} title="Test" onClose={vi.fn()}>Content</DetailModal>
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders title and children when open', () => {
    render(
      <DetailModal open={true} title="Analysis" onClose={vi.fn()}>
        <p>Modal body</p>
      </DetailModal>
    )
    expect(screen.getByText('Analysis')).toBeInTheDocument()
    expect(screen.getByText('Modal body')).toBeInTheDocument()
  })

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    render(
      <DetailModal open={true} title="Test" onClose={onClose}>Content</DetailModal>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when overlay is clicked (default)', () => {
    const onClose = vi.fn()
    render(
      <DetailModal open={true} title="Test" onClose={onClose}>Content</DetailModal>
    )
    fireEvent.click(document.body.querySelector('.modal-overlay')!)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not close on overlay when closeOnBackdrop=false', () => {
    const onClose = vi.fn()
    render(
      <DetailModal open={true} title="Test" onClose={onClose} closeOnBackdrop={false}>Content</DetailModal>
    )
    fireEvent.click(document.body.querySelector('.modal-overlay')!)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose when the close button (×) is clicked', () => {
    const onClose = vi.fn()
    render(
      <DetailModal open={true} title="Test" onClose={onClose}>Content</DetailModal>
    )
    fireEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('uses aria-labelledby pointing at the title', () => {
    render(
      <DetailModal open={true} title="My Title" onClose={vi.fn()}>x</DetailModal>
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    const labelledby = dialog.getAttribute('aria-labelledby')
    expect(labelledby).toBeTruthy()
    expect(document.getElementById(labelledby!)!.textContent).toBe('My Title')
  })

  it('has no action buttons (unlike ConfirmDialog)', () => {
    render(
      <DetailModal open={true} title="Test" onClose={vi.fn()}>Content</DetailModal>
    )
    expect(screen.queryByRole('button', { name: /^confirm$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^cancel$/i })).not.toBeInTheDocument()
  })

  it('restores focus to previously focused element on close', () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Open'
    document.body.appendChild(trigger)
    trigger.focus()

    const { rerender } = render(
      <DetailModal open={true} title="Test" onClose={vi.fn()}>
        <button>Inside</button>
      </DetailModal>
    )
    expect(document.activeElement).not.toBe(trigger)

    rerender(
      <DetailModal open={false} title="Test" onClose={vi.fn()}>
        <button>Inside</button>
      </DetailModal>
    )
    expect(document.activeElement).toBe(trigger)
    document.body.removeChild(trigger)
  })
})
