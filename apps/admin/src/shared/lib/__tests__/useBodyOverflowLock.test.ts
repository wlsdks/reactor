import { renderHook } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { useBodyOverflowLock } from '../useBodyOverflowLock'

describe('useBodyOverflowLock', () => {
  it('sets body overflow to hidden when active', () => {
    renderHook(() => useBodyOverflowLock(true))
    expect(document.body.style.overflow).toBe('hidden')
  })

  it('does not set overflow when inactive', () => {
    document.body.style.overflow = ''
    renderHook(() => useBodyOverflowLock(false))
    expect(document.body.style.overflow).toBe('')
  })

  it('restores overflow on unmount', () => {
    const { unmount } = renderHook(() => useBodyOverflowLock(true))
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('restores overflow when active changes to false', () => {
    const { rerender } = renderHook(
      ({ active }) => useBodyOverflowLock(active),
      { initialProps: { active: true } },
    )
    expect(document.body.style.overflow).toBe('hidden')
    rerender({ active: false })
    expect(document.body.style.overflow).toBe('')
  })
})
