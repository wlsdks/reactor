import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import { render, screen, fireEvent, act } from '../../../test/utils'
import { Tooltip } from '../Tooltip'

describe('Tooltip', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    // Tear down React trees while fake timers are still active so any pending
    // `setTimeout` from `openTooltip` does not fire after the test finishes.
    cleanup()
    vi.useRealTimers()
    // Belt-and-braces: scrub any tooltip portal that survived unmount.
    document.body
      .querySelectorAll('[role="tooltip"]')
      .forEach((node) => node.parentNode?.removeChild(node))
  })

  it('renders the trigger and no tooltip by default', () => {
    render(
      <Tooltip content="hello">
        <button type="button">trigger</button>
      </Tooltip>,
    )
    expect(screen.getByRole('button', { name: 'trigger' })).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('shows the tooltip after the configured delay on hover', () => {
    render(
      <Tooltip content="hello on hover" delay={150}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    fireEvent.mouseEnter(screen.getByRole('button'))
    // Before the delay elapses no tooltip should appear.
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(150)
    })
    expect(screen.getByRole('tooltip')).toHaveTextContent('hello on hover')
  })

  it('shows the tooltip on focus', () => {
    render(
      <Tooltip content="focus content" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    fireEvent.focus(screen.getByRole('button'))
    expect(screen.getByRole('tooltip')).toHaveTextContent('focus content')
  })

  it('hides the tooltip on Escape', () => {
    render(
      <Tooltip content="esc content" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    fireEvent.focus(screen.getByRole('button'))
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('hides the tooltip on blur and on mouseleave', () => {
    render(
      <Tooltip content="leave content" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    const btn = screen.getByRole('button')
    fireEvent.mouseEnter(btn)
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.mouseLeave(btn)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    fireEvent.focus(btn)
    expect(screen.getByRole('tooltip')).toBeInTheDocument()
    fireEvent.blur(btn)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('wires aria-describedby on the trigger when the tooltip is visible', () => {
    render(
      <Tooltip content="aria content" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    const btn = screen.getByRole('button')
    expect(btn.getAttribute('aria-describedby')).toBeFalsy()
    fireEvent.focus(btn)
    const tooltip = screen.getByRole('tooltip')
    const describedBy = btn.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(describedBy).toBe(tooltip.id)
  })

  it('does not open when disabled', () => {
    render(
      <Tooltip content="disabled content" disabled delay={0}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    const btn = screen.getByRole('button')
    fireEvent.mouseEnter(btn)
    fireEvent.focus(btn)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('preserves the original onClick handler attached to the trigger', () => {
    const onClick = vi.fn()
    render(
      <Tooltip content="click content" delay={0}>
        <button type="button" onClick={onClick}>trigger</button>
      </Tooltip>,
    )
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('exposes the configured placement via data-placement on the floating panel', () => {
    render(
      <Tooltip content="bottom content" placement="bottom" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>,
    )
    fireEvent.focus(screen.getByRole('button'))
    expect(screen.getByRole('tooltip').getAttribute('data-placement')).toBe('bottom')
  })
})
