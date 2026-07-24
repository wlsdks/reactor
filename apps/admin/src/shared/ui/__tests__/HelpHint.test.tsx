import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { render, screen, fireEvent, act } from '../../../test/utils'
import { HelpHint } from '../HelpHint'

describe('HelpHint', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    document.body
      .querySelectorAll('[role="tooltip"]')
      .forEach((node) => node.parentNode?.removeChild(node))
  })

  it('renders a focusable "!" trigger with the label as aria-label and title', () => {
    render(<HelpHint label="What is a category?" />)
    const btn = screen.getByRole('button', { name: 'What is a category?' })
    expect(btn).toBeInTheDocument()
    expect(btn).toHaveTextContent('!')
    expect(btn.getAttribute('title')).toBe('What is a category?')
    expect(btn.getAttribute('type')).toBe('button')
  })

  it('opens a tooltip with the configured label on focus', () => {
    render(<HelpHint label="Helpful description" />)
    fireEvent.focus(screen.getByRole('button'))
    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(screen.getByRole('tooltip')).toHaveTextContent('Helpful description')
  })

  it('forwards the placement prop to the underlying Tooltip', () => {
    render(<HelpHint label="bottom hint" placement="bottom" />)
    fireEvent.focus(screen.getByRole('button'))
    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(screen.getByRole('tooltip').getAttribute('data-placement')).toBe(
      'bottom',
    )
  })

  it('applies the md size class when size="md"', () => {
    render(<HelpHint label="medium" size="md" />)
    expect(screen.getByRole('button').className).toContain('help-hint--md')
  })

  it('appends a custom className without dropping the base class', () => {
    render(<HelpHint label="label" className="custom-extra" />)
    const btn = screen.getByRole('button')
    expect(btn.className).toContain('help-hint')
    expect(btn.className).toContain('custom-extra')
  })

  it('opens a centered explanation dialog on click', () => {
    render(<HelpHint title="전문 용어" label="운영자가 이해할 수 있는 자세한 설명" />)
    fireEvent.click(screen.getByRole('button', { name: '운영자가 이해할 수 있는 자세한 설명' }))

    expect(screen.getByRole('dialog', { name: '전문 용어' })).toBeInTheDocument()
    expect(screen.getByText('운영자가 이해할 수 있는 자세한 설명')).toBeInTheDocument()
  })
})
