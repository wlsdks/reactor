import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '../../../test/utils'
import userEvent from '@testing-library/user-event'
import { CollapsibleSection } from '../CollapsibleSection'

describe('CollapsibleSection', () => {
  it('renders title and hides children by default', () => {
    const { container } = render(
      <CollapsibleSection title="Details">
        <p>Hidden content</p>
      </CollapsibleSection>
    )
    expect(screen.getByText('Details')).toBeInTheDocument()
    expect(container.querySelector('details.collapsible-section')).not.toHaveAttribute('open')
  })

  it('shows children when defaultOpen is true', () => {
    const { container } = render(
      <CollapsibleSection title="Details" defaultOpen>
        <p>Visible content</p>
      </CollapsibleSection>
    )
    expect(container.querySelector('details.collapsible-section')).toHaveAttribute('open')
  })

  it('toggles open/closed on click', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <CollapsibleSection title="Details">
        <p>Content</p>
      </CollapsibleSection>
    )
    await user.click(screen.getByText('Details'))
    expect(container.querySelector('details.collapsible-section')).toHaveAttribute('open')
    await user.click(screen.getByText('Details'))
    expect(container.querySelector('details.collapsible-section')).not.toHaveAttribute('open')
  })

  it('renders badge when provided', () => {
    render(
      <CollapsibleSection title="Items" badge={5}>
        <p>Content</p>
      </CollapsibleSection>
    )
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('wires the provided body id to the disclosure content', () => {
    render(
      <CollapsibleSection title="Test" bodyId="test-body-1" defaultOpen>
        <p>body content</p>
      </CollapsibleSection>
    )
    const body = document.getElementById('test-body-1')
    expect(body).toBeInTheDocument()
    expect(body).toContainElement(screen.getByText('body content'))
  })

  it('auto-generates a stable id when bodyId is omitted', () => {
    render(
      <CollapsibleSection title="Auto" defaultOpen>
        <p>auto body</p>
      </CollapsibleSection>
    )
    const body = document.querySelector('.collapsible-body')
    expect(body?.id).toBeTruthy()
    expect(document.getElementById(body!.id)).toContainElement(screen.getByText('auto body'))
  })

  it('accepts a ReactNode title', () => {
    render(
      <CollapsibleSection
        title={<span data-testid="custom-title">Rich <em>title</em></span>}
        defaultOpen
      >
        <p>x</p>
      </CollapsibleSection>
    )
    expect(screen.getByTestId('custom-title')).toBeInTheDocument()
  })

  it('calls onToggle with the next open state when the toggle is clicked', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    render(
      <CollapsibleSection title="Toggle me" onToggle={onToggle}>
        <p>body</p>
      </CollapsibleSection>
    )
    await user.click(screen.getByText('Toggle me'))
    expect(onToggle).toHaveBeenCalledWith(true)
    await user.click(screen.getByText('Toggle me'))
    expect(onToggle).toHaveBeenCalledWith(false)
  })
})
