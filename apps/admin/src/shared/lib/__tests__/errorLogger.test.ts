import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../../i18n/config', () => ({
  default: {
    t: (key: string) => key,
  },
}))

import { errorLogger } from '../errorLogger'
import { ApiError } from '../../api/errors'

describe('errorLogger', () => {
  beforeEach(() => {
    errorLogger.clearErrors()
  })

  it('logs plain Error with name and message in dev', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    errorLogger.capture(new Error('test error'))
    expect(spy).toHaveBeenCalledWith('[Reactor]', expect.objectContaining({
      name: 'Error',
      message: 'test error',
    }))
    spy.mockRestore()
  })

  it('logs ApiError with status but not serverMessage (sensitive data)', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const err = new ApiError(404, 'NOT_FOUND', 'Not found', 'Entity missing')
    errorLogger.capture(err, { action: 'deleteItem' })
    expect(spy).toHaveBeenCalledWith('[Reactor]', expect.objectContaining({
      name: 'ApiError',
      status: 404,
      action: 'deleteItem',
    }))
    // serverMessage must NOT be logged (may contain sensitive server details)
    const loggedObj = spy.mock.calls[0]?.[1] as Record<string, unknown>
    expect(loggedObj).not.toHaveProperty('serverMessage')
    spy.mockRestore()
  })

  it('includes context fields', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    errorLogger.capture(new Error('x'), { component: 'Sidebar', userId: 'u1' })
    expect(spy).toHaveBeenCalledWith('[Reactor]', expect.objectContaining({
      component: 'Sidebar',
      userId: 'u1',
    }))
    spy.mockRestore()
  })

  it('buffers errors for later retrieval', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    errorLogger.capture(new Error('first'))
    errorLogger.capture(new Error('second'))

    const recent = errorLogger.getRecentErrors()
    expect(recent).toHaveLength(2)
    expect(recent[0].message).toBe('first')
    expect(recent[1].message).toBe('second')
    expect(recent[0].timestamp).toBeLessThanOrEqual(recent[1].timestamp)
    spy.mockRestore()
  })

  it('limits buffer to MAX_BUFFER entries', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    for (let i = 0; i < 105; i++) {
      errorLogger.capture(new Error(`error-${i}`))
    }
    const recent = errorLogger.getRecentErrors()
    expect(recent).toHaveLength(100)
    // Oldest entries should have been shifted out
    expect(recent[0].message).toBe('error-5')
    expect(recent[99].message).toBe('error-104')
    spy.mockRestore()
  })

  it('clearErrors empties the buffer', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    errorLogger.capture(new Error('to-clear'))
    expect(errorLogger.getRecentErrors()).toHaveLength(1)

    errorLogger.clearErrors()
    expect(errorLogger.getRecentErrors()).toHaveLength(0)
    spy.mockRestore()
  })

  it('returns a copy from getRecentErrors (not the internal buffer)', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    errorLogger.capture(new Error('test'))
    const a = errorLogger.getRecentErrors()
    const b = errorLogger.getRecentErrors()
    expect(a).not.toBe(b)
    expect(a).toEqual(b)
    spy.mockRestore()
  })

  it('stores stack and status in error reports', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const apiErr = new ApiError(500, 'INTERNAL', 'Server error', 'secret detail')
    errorLogger.capture(apiErr, { action: 'fetchData' })

    const reports = errorLogger.getRecentErrors()
    expect(reports).toHaveLength(1)
    expect(reports[0].status).toBe(500)
    expect(reports[0].stack).toBeDefined()
    expect(reports[0].context).toEqual({ action: 'fetchData' })
    spy.mockRestore()
  })
})
