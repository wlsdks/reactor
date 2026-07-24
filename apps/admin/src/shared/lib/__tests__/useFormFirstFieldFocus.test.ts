import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useFormFirstFieldFocus } from '../useFormFirstFieldFocus'

describe('useFormFirstFieldFocus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  function setupContainer(html: string): HTMLDivElement {
    const container = document.createElement('div')
    container.innerHTML = html
    document.body.appendChild(container)
    return container
  }

  it('focuses the first input when open becomes true', () => {
    const container = setupContainer(
      '<input id="first" /><input id="second" />',
    )
    const first = container.querySelector('#first') as HTMLInputElement
    const focusSpy = vi.spyOn(first, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('skips disabled inputs', () => {
    const container = setupContainer(
      '<input id="first" disabled /><input id="second" />',
    )
    const second = container.querySelector('#second') as HTMLInputElement
    const focusSpy = vi.spyOn(second, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('skips readonly inputs', () => {
    const container = setupContainer(
      '<input id="first" readonly /><input id="second" />',
    )
    const first = container.querySelector('#first') as HTMLInputElement
    const second = container.querySelector('#second') as HTMLInputElement
    const firstSpy = vi.spyOn(first, 'focus')
    const secondSpy = vi.spyOn(second, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(firstSpy).not.toHaveBeenCalled()
    expect(secondSpy).toHaveBeenCalledTimes(1)
  })

  it('skips hidden inputs', () => {
    const container = setupContainer(
      '<input id="first" type="hidden" /><input id="second" />',
    )
    const second = container.querySelector('#second') as HTMLInputElement
    const focusSpy = vi.spyOn(second, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('skips aria-hidden elements', () => {
    const container = setupContainer(
      '<div aria-hidden="true"><input id="first" /></div><input id="second" />',
    )
    const first = container.querySelector('#first') as HTMLInputElement
    const second = container.querySelector('#second') as HTMLInputElement
    const firstSpy = vi.spyOn(first, 'focus')
    const secondSpy = vi.spyOn(second, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(firstSpy).not.toHaveBeenCalled()
    expect(secondSpy).toHaveBeenCalledTimes(1)
  })

  it('does not focus when open is false', () => {
    const container = setupContainer('<input id="first" />')
    const first = container.querySelector('#first') as HTMLInputElement
    const focusSpy = vi.spyOn(first, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, false))

    vi.advanceTimersByTime(200)

    expect(focusSpy).not.toHaveBeenCalled()
  })

  it('does not throw when ref is null', () => {
    const ref = { current: null }
    expect(() => {
      renderHook(() => useFormFirstFieldFocus(ref, true))
      vi.advanceTimersByTime(50)
    }).not.toThrow()
  })

  it('does not throw when no focusable form fields exist', () => {
    const container = setupContainer('<span>No fields</span>')
    const ref = { current: container }
    expect(() => {
      renderHook(() => useFormFirstFieldFocus(ref, true))
      vi.advanceTimersByTime(50)
    }).not.toThrow()
  })

  it('respects a custom selector', () => {
    const container = setupContainer(
      '<input id="first" /><button id="custom-target" type="button">go</button>',
    )
    const button = container.querySelector('#custom-target') as HTMLButtonElement
    const input = container.querySelector('#first') as HTMLInputElement
    const buttonSpy = vi.spyOn(button, 'focus')
    const inputSpy = vi.spyOn(input, 'focus')

    const ref = { current: container }
    renderHook(() =>
      useFormFirstFieldFocus(ref, true, { selector: 'button[type="button"]' }),
    )

    vi.advanceTimersByTime(50)

    expect(buttonSpy).toHaveBeenCalledTimes(1)
    expect(inputSpy).not.toHaveBeenCalled()
  })

  it('respects a custom delay', () => {
    const container = setupContainer('<input id="first" />')
    const first = container.querySelector('#first') as HTMLInputElement
    const focusSpy = vi.spyOn(first, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true, { delay: 200 }))

    // Should not fire before custom delay elapses.
    vi.advanceTimersByTime(50)
    expect(focusSpy).not.toHaveBeenCalled()

    vi.advanceTimersByTime(150)
    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('cancels pending focus when the hook unmounts before delay elapses', () => {
    const container = setupContainer('<input id="first" />')
    const first = container.querySelector('#first') as HTMLInputElement
    const focusSpy = vi.spyOn(first, 'focus')

    const ref = { current: container }
    const { unmount } = renderHook(() => useFormFirstFieldFocus(ref, true))

    unmount()
    vi.advanceTimersByTime(50)

    expect(focusSpy).not.toHaveBeenCalled()
  })

  it('focuses textarea when no input is present', () => {
    const container = setupContainer('<textarea id="first"></textarea>')
    const textarea = container.querySelector('#first') as HTMLTextAreaElement
    const focusSpy = vi.spyOn(textarea, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('focuses select when no input or textarea is present', () => {
    const container = setupContainer(
      '<select id="first"><option>a</option></select>',
    )
    const select = container.querySelector('#first') as HTMLSelectElement
    const focusSpy = vi.spyOn(select, 'focus')

    const ref = { current: container }
    renderHook(() => useFormFirstFieldFocus(ref, true))

    vi.advanceTimersByTime(50)

    expect(focusSpy).toHaveBeenCalledTimes(1)
  })
})
