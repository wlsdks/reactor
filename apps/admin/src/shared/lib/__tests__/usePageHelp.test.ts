import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePageHelp, usePageHelpStore } from '../usePageHelp'

function reset() {
  act(() => {
    usePageHelpStore.setState({ helpKey: null, isOpen: false })
  })
}

describe('usePageHelp', () => {
  beforeEach(() => {
    reset()
  })

  it('registers the helpKey on mount', () => {
    renderHook(() => usePageHelp({ helpKey: 'foo.help' }))
    expect(usePageHelpStore.getState().helpKey).toBe('foo.help')
  })

  it('returns the current store snapshot', () => {
    const { result } = renderHook(() => usePageHelp({ helpKey: 'foo.help' }))
    expect(result.current.helpKey).toBe('foo.help')
    expect(result.current.isOpen).toBe(false)
    expect(typeof result.current.open).toBe('function')
    expect(typeof result.current.close).toBe('function')
  })

  it('open() and close() toggle isOpen', () => {
    const { result } = renderHook(() => usePageHelp({ helpKey: 'foo.help' }))
    act(() => result.current.open())
    expect(usePageHelpStore.getState().isOpen).toBe(true)
    act(() => result.current.close())
    expect(usePageHelpStore.getState().isOpen).toBe(false)
  })

  it('clears the helpKey on unmount when it still owns it', () => {
    const { unmount } = renderHook(() => usePageHelp({ helpKey: 'foo.help' }))
    expect(usePageHelpStore.getState().helpKey).toBe('foo.help')
    unmount()
    expect(usePageHelpStore.getState().helpKey).toBeNull()
  })

  it('does not clear the helpKey if a different page already registered', () => {
    const { unmount } = renderHook(() => usePageHelp({ helpKey: 'foo.help' }))
    // Sibling page mounts and overrides the key before the first unmounts —
    // simulates a fast route transition.
    act(() => {
      usePageHelpStore.getState().setHelpKey('bar.help')
    })
    unmount()
    expect(usePageHelpStore.getState().helpKey).toBe('bar.help')
  })

  it('updates the registered key when helpKey prop changes', () => {
    const { rerender } = renderHook(({ key }) => usePageHelp({ helpKey: key }), {
      initialProps: { key: 'a.help' },
    })
    expect(usePageHelpStore.getState().helpKey).toBe('a.help')
    rerender({ key: 'b.help' })
    expect(usePageHelpStore.getState().helpKey).toBe('b.help')
  })
})
