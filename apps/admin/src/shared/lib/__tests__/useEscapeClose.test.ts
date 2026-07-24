import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useEscapeClose } from '../useEscapeClose'

describe('useEscapeClose', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('invokes the handler when Escape is pressed and active is true', () => {
    const onClose = vi.fn()
    renderHook(() => useEscapeClose(onClose, { active: true }))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('defaults active to true when no options are passed', () => {
    const onClose = vi.fn()
    renderHook(() => useEscapeClose(onClose))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('does not invoke the handler when active is false', () => {
    const onClose = vi.fn()
    renderHook(() => useEscapeClose(onClose, { active: false }))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('ignores keys other than Escape', () => {
    const onClose = vi.fn()
    renderHook(() => useEscapeClose(onClose, { active: true }))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('removes the keydown listener on unmount', () => {
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const onClose = vi.fn()
    const { unmount } = renderHook(() => useEscapeClose(onClose, { active: true }))
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
  })

  it('does not attach a listener while inactive', () => {
    const addSpy = vi.spyOn(document, 'addEventListener')
    const onClose = vi.fn()
    renderHook(() => useEscapeClose(onClose, { active: false }))
    expect(addSpy).not.toHaveBeenCalledWith('keydown', expect.any(Function))
  })
})
