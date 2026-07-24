import { render, screen, fireEvent } from '../../../test/utils'
import { describe, it, expect, vi } from 'vitest'
import { SideDrawer } from '../SideDrawer'

describe('SideDrawer', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <SideDrawer open={false} title="Test" onClose={vi.fn()}>Content</SideDrawer>
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders title and children when open', () => {
    render(
      <SideDrawer open={true} title="Detail" onClose={vi.fn()}>
        <p>Drawer content</p>
      </SideDrawer>
    )
    expect(screen.getByText('Detail')).toBeInTheDocument()
    expect(screen.getByText('Drawer content')).toBeInTheDocument()
  })

  it('calls onClose when backdrop is clicked (default)', () => {
    const onClose = vi.fn()
    render(
      <SideDrawer open={true} title="Test" onClose={onClose}>Content</SideDrawer>
    )
    fireEvent.click(document.body.querySelector('.drawer-overlay')!)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not close on backdrop when closeOnBackdrop=false', () => {
    const onClose = vi.fn()
    render(
      <SideDrawer open={true} title="Test" onClose={onClose} closeOnBackdrop={false}>Content</SideDrawer>
    )
    fireEvent.click(document.body.querySelector('.drawer-overlay')!)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    render(
      <SideDrawer open={true} title="Test" onClose={onClose}>Content</SideDrawer>
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not propagate clicks from drawer body', () => {
    const onClose = vi.fn()
    render(
      <SideDrawer open={true} title="Test" onClose={onClose}>
        <button>Inner</button>
      </SideDrawer>
    )
    fireEvent.click(screen.getByText('Inner'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('has correct ARIA attributes', () => {
    render(
      <SideDrawer open={true} title="Test" onClose={vi.fn()}>Content</SideDrawer>
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('uses aria-labelledby pointing at the title', () => {
    render(
      <SideDrawer open={true} title="My Drawer Title" onClose={vi.fn()}>Content</SideDrawer>
    )
    const dialog = screen.getByRole('dialog')
    const labelledby = dialog.getAttribute('aria-labelledby')
    expect(labelledby).toBeTruthy()
    const titleEl = document.getElementById(labelledby!)
    expect(titleEl).not.toBeNull()
    expect(titleEl!.textContent).toBe('My Drawer Title')
  })

  it('renders close button and calls onClose when clicked', () => {
    const onClose = vi.fn()
    render(
      <SideDrawer open={true} title="Test" onClose={onClose}>Content</SideDrawer>
    )
    const closeBtn = screen.getByRole('button', { name: /close/i })
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('renders drawer header with title', () => {
    render(
      <SideDrawer open={true} title="Drawer Header" onClose={vi.fn()}>Body</SideDrawer>
    )
    const title = document.body.querySelector('.drawer-title')
    expect(title).not.toBeNull()
    expect(title!.textContent).toBe('Drawer Header')
  })

  it('renders children inside drawer-body', () => {
    render(
      <SideDrawer open={true} title="Test" onClose={vi.fn()}>
        <span data-testid="child">Hello</span>
      </SideDrawer>
    )
    const body = document.body.querySelector('.drawer-body')
    expect(body).not.toBeNull()
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('renders overlay with drawer-overlay class', () => {
    render(
      <SideDrawer open={true} title="Test" onClose={vi.fn()}>Content</SideDrawer>
    )
    const overlay = document.body.querySelector('.drawer-overlay')
    expect(overlay).not.toBeNull()
  })

  it('restores focus to previously focused element on close', () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'Open'
    document.body.appendChild(trigger)
    trigger.focus()

    const { rerender } = render(
      <SideDrawer open={true} title="Test" onClose={vi.fn()}>
        <button>Inside</button>
      </SideDrawer>
    )
    expect(document.activeElement).not.toBe(trigger)

    rerender(
      <SideDrawer open={false} title="Test" onClose={vi.fn()}>
        <button>Inside</button>
      </SideDrawer>
    )
    expect(document.activeElement).toBe(trigger)
    document.body.removeChild(trigger)
  })
})
