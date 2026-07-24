import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useSessionExpiry } from '../useSessionExpiry'
import type { User } from '../types'

// ---------- mocks ----------

vi.mock('../../../shared/api/client', () => ({
  getAuthToken: vi.fn(),
}))

vi.mock('../../../shared/lib/jwt', () => ({
  getTokenExpiry: vi.fn(),
}))

const mockAddToast = vi.fn()
vi.mock('../../../shared/store/toast.store', () => ({
  useToastStore: {
    getState: () => ({ addToast: mockAddToast }),
  },
}))

vi.mock('../../../shared/i18n/config', () => ({
  default: {
    t: (key: string) => key,
  },
}))

import { getAuthToken } from '../../../shared/api/client'
import { getTokenExpiry } from '../../../shared/lib/jwt'

const mockGetAuthToken = vi.mocked(getAuthToken)
const mockGetTokenExpiry = vi.mocked(getTokenExpiry)

const fakeUser: User = {
  id: '1',
  email: 'admin@example.com',
  name: 'Admin',
  role: 'ADMIN',
}

describe('useSessionExpiry', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('does nothing when user is null', () => {
    renderHook(() => useSessionExpiry(null))

    expect(mockGetAuthToken).not.toHaveBeenCalled()
    expect(mockAddToast).not.toHaveBeenCalled()
  })

  it('does nothing when no token', () => {
    mockGetAuthToken.mockReturnValue(null)

    renderHook(() => useSessionExpiry(fakeUser))

    expect(mockGetAuthToken).toHaveBeenCalled()
    expect(mockGetTokenExpiry).not.toHaveBeenCalled()
    expect(mockAddToast).not.toHaveBeenCalled()
  })

  it('does nothing when token has no expiry', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    mockGetTokenExpiry.mockReturnValue(null)

    renderHook(() => useSessionExpiry(fakeUser))

    expect(mockGetTokenExpiry).toHaveBeenCalledWith('fake-token')
    expect(mockAddToast).not.toHaveBeenCalled()
  })

  it('does nothing when token is already expired', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    const nowSec = Math.floor(Date.now() / 1000)
    mockGetTokenExpiry.mockReturnValue(nowSec - 10)

    renderHook(() => useSessionExpiry(fakeUser))

    expect(mockAddToast).not.toHaveBeenCalled()
  })

  it('shows 5-minute warning at correct time', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    const nowSec = Math.floor(Date.now() / 1000)
    // Token expires in 600 seconds (10 minutes)
    mockGetTokenExpiry.mockReturnValue(nowSec + 600)

    renderHook(() => useSessionExpiry(fakeUser))

    // 5-min warning should fire at (600 - 300) * 1000 = 300_000 ms
    expect(mockAddToast).not.toHaveBeenCalled()

    vi.advanceTimersByTime(299_999)
    expect(mockAddToast).not.toHaveBeenCalled()

    vi.advanceTimersByTime(1)
    expect(mockAddToast).toHaveBeenCalledTimes(1)
    expect(mockAddToast).toHaveBeenCalledWith({
      type: 'warning',
      message: 'common.toast.sessionExpiring5',
    })
  })

  it('shows 1-minute warning at correct time', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    const nowSec = Math.floor(Date.now() / 1000)
    // Token expires in 600 seconds (10 minutes)
    mockGetTokenExpiry.mockReturnValue(nowSec + 600)

    renderHook(() => useSessionExpiry(fakeUser))

    // 1-min warning should fire at (600 - 60) * 1000 = 540_000 ms
    vi.advanceTimersByTime(540_000)
    expect(mockAddToast).toHaveBeenCalledTimes(2) // 5-min + 1-min
    expect(mockAddToast).toHaveBeenLastCalledWith({
      type: 'warning',
      message: 'common.toast.sessionExpiring1',
    })
  })

  it('skips 5-minute warning when less than 5 minutes remain', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    const nowSec = Math.floor(Date.now() / 1000)
    // Token expires in 200 seconds (< 5 minutes)
    mockGetTokenExpiry.mockReturnValue(nowSec + 200)

    renderHook(() => useSessionExpiry(fakeUser))

    // Only 1-min warning should exist: at (200 - 60) * 1000 = 140_000 ms
    vi.advanceTimersByTime(140_000)
    expect(mockAddToast).toHaveBeenCalledTimes(1)
    expect(mockAddToast).toHaveBeenCalledWith({
      type: 'warning',
      message: 'common.toast.sessionExpiring1',
    })
  })

  it('splits long token lifetimes into safe timeout windows', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    const timeoutSpy = vi.spyOn(globalThis, 'setTimeout')
    const nowSec = Math.floor(Date.now() / 1000)
    mockGetTokenExpiry.mockReturnValue(nowSec + 10_000_000)

    renderHook(() => useSessionExpiry(fakeUser))

    expect(timeoutSpy).toHaveBeenCalledTimes(2)
    for (const [, delay] of timeoutSpy.mock.calls) {
      expect(delay).toBeLessThanOrEqual(2_147_483_647)
    }
    expect(mockAddToast).not.toHaveBeenCalled()
  })

  it('cleans up timers on unmount', () => {
    mockGetAuthToken.mockReturnValue('fake-token')
    const nowSec = Math.floor(Date.now() / 1000)
    mockGetTokenExpiry.mockReturnValue(nowSec + 600)

    const { unmount } = renderHook(() => useSessionExpiry(fakeUser))

    unmount()

    // Advance past all timer points — nothing should fire
    vi.advanceTimersByTime(600_000)
    expect(mockAddToast).not.toHaveBeenCalled()
  })
})
