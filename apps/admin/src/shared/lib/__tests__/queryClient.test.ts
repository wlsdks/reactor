import { describe, it, expect, beforeEach, vi } from 'vitest'
import { queryClient } from '../queryClient'
import { errorLogger } from '../errorLogger'
import { useToastStore } from '../../store/toast.store'
import { ApiError } from '../../api/errors'

beforeEach(() => {
  // Drop any toasts queued by previous tests so assertions are positional.
  const state = useToastStore.getState()
  for (const toast of state.toasts) state.removeToast(toast.id)
  queryClient.clear()
  vi.restoreAllMocks()
})

describe('queryClient defaults', () => {
  it('exposes hardened query defaults (staleTime, gcTime, networkMode, structuralSharing)', () => {
    const defaults = queryClient.getDefaultOptions().queries
    expect(defaults?.staleTime).toBe(30_000)
    expect(defaults?.gcTime).toBe(5 * 60_000)
    expect(defaults?.refetchOnWindowFocus).toBe(false)
    expect(defaults?.refetchOnReconnect).toBe(true)
    expect(defaults?.structuralSharing).toBe(true)
    expect(defaults?.networkMode).toBe('online')
  })

  it('exposes hardened mutation defaults (networkMode)', () => {
    const defaults = queryClient.getDefaultOptions().mutations
    expect(defaults?.networkMode).toBe('online')
  })

  it('does not retry 4xx ApiError responses', () => {
    const retry = queryClient.getDefaultOptions().queries?.retry
    expect(typeof retry).toBe('function')
    if (typeof retry !== 'function') return
    const fourHundred = ApiError.fromResponse(404, null)
    expect(retry(0, fourHundred)).toBe(false)
    expect(retry(1, fourHundred)).toBe(false)
  })

  it('retries 5xx errors up to 2 attempts', () => {
    const retry = queryClient.getDefaultOptions().queries?.retry
    if (typeof retry !== 'function') throw new Error('retry must be a function')
    const fiveHundred = ApiError.fromResponse(500, null)
    expect(retry(0, fiveHundred)).toBe(true)
    expect(retry(1, fiveHundred)).toBe(true)
    expect(retry(2, fiveHundred)).toBe(false)
  })
})

describe('queryClient queryCache.onError', () => {
  it('forwards query errors to errorLogger.capture', async () => {
    const captureSpy = vi.spyOn(errorLogger, 'capture').mockImplementation(() => {})
    const failingFetch = () => Promise.reject(ApiError.fromResponse(500, null))

    await expect(
      queryClient.fetchQuery({
        queryKey: ['test', 'capture'],
        queryFn: failingFetch,
        retry: false,
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(captureSpy).toHaveBeenCalledTimes(1)
    expect(captureSpy.mock.calls[0][1]).toMatchObject({
      action: 'query',
      queryKey: JSON.stringify(['test', 'capture']),
    })
  })

  it('skips errorLogger.capture when meta.skipGlobalError is set', async () => {
    const captureSpy = vi.spyOn(errorLogger, 'capture').mockImplementation(() => {})
    const failingFetch = () => Promise.reject(ApiError.fromResponse(500, null))

    await expect(
      queryClient.fetchQuery({
        queryKey: ['test', 'skip'],
        queryFn: failingFetch,
        retry: false,
        meta: { skipGlobalError: true },
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(captureSpy).not.toHaveBeenCalled()
  })

  it('does not surface a toast for query errors (queries handle their own UI)', async () => {
    vi.spyOn(errorLogger, 'capture').mockImplementation(() => {})
    const failingFetch = () => Promise.reject(ApiError.fromResponse(500, null))

    await expect(
      queryClient.fetchQuery({
        queryKey: ['test', 'no-toast'],
        queryFn: failingFetch,
        retry: false,
      }),
    ).rejects.toBeInstanceOf(ApiError)

    expect(useToastStore.getState().toasts).toHaveLength(0)
  })
})
