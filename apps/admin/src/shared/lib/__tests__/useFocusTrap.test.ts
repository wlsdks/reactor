import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useFocusTrap } from '../useFocusTrap'

describe('useFocusTrap', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('returns without error when ref is null and active is false', () => {
    const ref = { current: null }
    const { result } = renderHook(() => useFocusTrap(ref, false))
    expect(result).toBeDefined()
  })

  it('returns without error when ref is null and active is true', () => {
    const ref = { current: null }
    const { result } = renderHook(() => useFocusTrap(ref, true))
    expect(result).toBeDefined()
  })

  it('does not add event listener when active is false', () => {
    const addEventListenerSpy = vi.spyOn(document, 'addEventListener')
    const ref = { current: document.createElement('div') }
    renderHook(() => useFocusTrap(ref, false))
    expect(addEventListenerSpy).not.toHaveBeenCalledWith('keydown', expect.any(Function))
  })

  it('adds and removes keydown listener when active is true', () => {
    const addEventListenerSpy = vi.spyOn(document, 'addEventListener')
    const removeEventListenerSpy = vi.spyOn(document, 'removeEventListener')

    const container = document.createElement('div')
    const button = document.createElement('button')
    container.appendChild(button)
    document.body.appendChild(container)

    const ref = { current: container }
    const { unmount } = renderHook(() => useFocusTrap(ref, true))

    expect(addEventListenerSpy).toHaveBeenCalledWith('keydown', expect.any(Function))

    unmount()

    expect(removeEventListenerSpy).toHaveBeenCalledWith('keydown', expect.any(Function))

    document.body.removeChild(container)
  })

  it('auto-focuses the first focusable element when activated', () => {
    const container = document.createElement('div')
    const button1 = document.createElement('button')
    const button2 = document.createElement('button')
    button1.textContent = 'First'
    button2.textContent = 'Second'
    container.appendChild(button1)
    container.appendChild(button2)
    document.body.appendChild(container)

    const focusSpy = vi.spyOn(button1, 'focus')
    const ref = { current: container }

    renderHook(() => useFocusTrap(ref, true))

    expect(focusSpy).toHaveBeenCalled()

    document.body.removeChild(container)
  })

  it('restores focus on unmount', () => {
    const previousButton = document.createElement('button')
    document.body.appendChild(previousButton)
    previousButton.focus()

    const container = document.createElement('div')
    const innerButton = document.createElement('button')
    container.appendChild(innerButton)
    document.body.appendChild(container)

    const ref = { current: container }
    const { unmount } = renderHook(() => useFocusTrap(ref, true))

    const restoreSpy = vi.spyOn(previousButton, 'focus')
    unmount()

    expect(restoreSpy).toHaveBeenCalled()

    document.body.removeChild(previousButton)
    document.body.removeChild(container)
  })

  it('does not call focus on a previously-focused element that has been removed from the DOM', () => {
    // Trigger element that gets unmounted while the modal is open — the
    // hook must NOT try to focus a detached node on cleanup, otherwise
    // browsers may dump focus to <body> with a noisy warning.
    const previousButton = document.createElement('button')
    document.body.appendChild(previousButton)
    previousButton.focus()

    const container = document.createElement('div')
    const innerButton = document.createElement('button')
    container.appendChild(innerButton)
    document.body.appendChild(container)

    const ref = { current: container }
    const { unmount } = renderHook(() => useFocusTrap(ref, true))

    // Simulate the trigger element being removed from the DOM while the
    // modal is open (e.g. parent re-rendered without it).
    document.body.removeChild(previousButton)

    const restoreSpy = vi.spyOn(previousButton, 'focus')
    unmount()

    expect(restoreSpy).not.toHaveBeenCalled()

    document.body.removeChild(container)
  })

  it('wraps focus from last to first element on Tab', () => {
    const container = document.createElement('div')
    const button1 = document.createElement('button')
    const button2 = document.createElement('button')
    const button3 = document.createElement('button')
    button1.textContent = 'First'
    button2.textContent = 'Middle'
    button3.textContent = 'Last'
    container.appendChild(button1)
    container.appendChild(button2)
    container.appendChild(button3)
    document.body.appendChild(container)

    const ref = { current: container }
    renderHook(() => useFocusTrap(ref, true))

    // Focus the last element
    button3.focus()
    expect(document.activeElement).toBe(button3)

    // Simulate Tab key at last element
    const focusSpy = vi.spyOn(button1, 'focus')
    const event = new KeyboardEvent('keydown', {
      key: 'Tab',
      bubbles: true,
      cancelable: true,
    })
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    document.dispatchEvent(event)

    expect(preventDefaultSpy).toHaveBeenCalled()
    expect(focusSpy).toHaveBeenCalled()

    document.body.removeChild(container)
  })

  it('wraps focus from first to last element on Shift+Tab', () => {
    const container = document.createElement('div')
    const button1 = document.createElement('button')
    const button2 = document.createElement('button')
    const button3 = document.createElement('button')
    button1.textContent = 'First'
    button2.textContent = 'Middle'
    button3.textContent = 'Last'
    container.appendChild(button1)
    container.appendChild(button2)
    container.appendChild(button3)
    document.body.appendChild(container)

    const ref = { current: container }
    renderHook(() => useFocusTrap(ref, true))

    // Focus the first element (should already be focused due to auto-focus)
    button1.focus()
    expect(document.activeElement).toBe(button1)

    // Simulate Shift+Tab key at first element
    const focusSpy = vi.spyOn(button3, 'focus')
    const event = new KeyboardEvent('keydown', {
      key: 'Tab',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    })
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    document.dispatchEvent(event)

    expect(preventDefaultSpy).toHaveBeenCalled()
    expect(focusSpy).toHaveBeenCalled()

    document.body.removeChild(container)
  })

  it('does not prevent default when Tab is pressed on a middle element', () => {
    const container = document.createElement('div')
    const button1 = document.createElement('button')
    const button2 = document.createElement('button')
    const button3 = document.createElement('button')
    container.appendChild(button1)
    container.appendChild(button2)
    container.appendChild(button3)
    document.body.appendChild(container)

    const ref = { current: container }
    renderHook(() => useFocusTrap(ref, true))

    // Focus the middle element
    button2.focus()
    expect(document.activeElement).toBe(button2)

    const event = new KeyboardEvent('keydown', {
      key: 'Tab',
      bubbles: true,
      cancelable: true,
    })
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    document.dispatchEvent(event)

    // Should NOT prevent default — middle element, not at boundary
    expect(preventDefaultSpy).not.toHaveBeenCalled()

    document.body.removeChild(container)
  })

  it('does nothing for non-Tab keys', () => {
    const container = document.createElement('div')
    const button1 = document.createElement('button')
    container.appendChild(button1)
    document.body.appendChild(container)

    const ref = { current: container }
    renderHook(() => useFocusTrap(ref, true))

    button1.focus()

    const event = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    })
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    document.dispatchEvent(event)

    expect(preventDefaultSpy).not.toHaveBeenCalled()

    document.body.removeChild(container)
  })

  it('handles container with no focusable elements during keydown', () => {
    const container = document.createElement('div')
    const span = document.createElement('span')
    span.textContent = 'Not focusable'
    container.appendChild(span)
    document.body.appendChild(container)

    const ref = { current: container }
    renderHook(() => useFocusTrap(ref, true))

    // Dispatch a Tab event — should not throw
    const event = new KeyboardEvent('keydown', {
      key: 'Tab',
      bubbles: true,
      cancelable: true,
    })
    expect(() => document.dispatchEvent(event)).not.toThrow()

    document.body.removeChild(container)
  })
})
