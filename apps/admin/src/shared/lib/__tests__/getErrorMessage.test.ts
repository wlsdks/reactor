import { describe, it, expect, beforeAll } from 'vitest'
import { getErrorMessage, isAbortError, resolveApiError } from '../getErrorMessage'
import { ApiError, NetworkError } from '../../api/errors'
// Importing the i18n config initializes i18next with the Korean resource so
// resolveApiError() returns the project-localized strings instead of the
// hardcoded fallbacks.
import '../../i18n/config'

beforeAll(() => {
  // Sanity: i18next must be initialized before the resolver runs to assert
  // localized strings.
  expect(typeof window).toBe('object')
})

describe('getErrorMessage', () => {
  it('extracts message from Error instance', () => {
    expect(getErrorMessage(new Error('test error'))).toBe('test error')
  })

  it('returns string errors as-is', () => {
    expect(getErrorMessage('string error')).toBe('string error')
  })

  it('returns fallback for unknown types', () => {
    expect(getErrorMessage(42)).toBe('Unknown error')
    expect(getErrorMessage(null)).toBe('Unknown error')
    expect(getErrorMessage(undefined)).toBe('Unknown error')
    expect(getErrorMessage({ code: 500 })).toBe('Unknown error')
  })
})

describe('isAbortError', () => {
  it('returns true for AbortError DOMException', () => {
    expect(isAbortError(new DOMException('The operation was aborted', 'AbortError'))).toBe(true)
  })

  it('returns false for other DOMExceptions', () => {
    expect(isAbortError(new DOMException('timeout', 'TimeoutError'))).toBe(false)
  })

  it('returns false for regular errors', () => {
    expect(isAbortError(new Error('abort'))).toBe(false)
  })

  it('returns false for non-error values', () => {
    expect(isAbortError(null)).toBe(false)
    expect(isAbortError('AbortError')).toBe(false)
    expect(isAbortError(undefined)).toBe(false)
  })
})

describe('resolveApiError', () => {
  it('maps 401 → sessionExpired with login recovery', () => {
    const result = resolveApiError(ApiError.fromResponse(401, null))
    expect(result.message).toBe('세션이 만료됐어요')
    expect(result.recovery).toEqual({ type: 'login', label: '다시 로그인' })
    expect(result.raw?.status).toBe(401)
  })

  it('maps 403 → forbidden with hint and contact recovery', () => {
    const result = resolveApiError(ApiError.fromResponse(403, null))
    expect(result.message).toBe('권한이 없어요')
    expect(result.hint).toBe('이 작업은 ADMIN 권한이 필요해요')
    expect(result.recovery?.type).toBe('contact')
    expect(result.recovery?.label).toBe('관리자 문의')
  })

  it('maps 404 → notFound without recovery', () => {
    const result = resolveApiError(ApiError.fromResponse(404, null))
    expect(result.message).toBe('리소스를 찾을 수 없어요')
    expect(result.hint).toBeUndefined()
    expect(result.recovery).toBeUndefined()
  })

  it('maps 409 → conflict with retry recovery', () => {
    const result = resolveApiError(ApiError.fromResponse(409, null))
    expect(result.message).toContain('충돌')
    expect(result.recovery?.type).toBe('retry')
  })

  it('maps 429 → tooManyRequests with retry recovery and hint', () => {
    const result = resolveApiError(ApiError.fromResponse(429, null))
    expect(result.message).toBe('요청이 너무 많아요')
    expect(result.hint).toBe('잠시 후 다시 시도해 주세요')
    expect(result.recovery?.type).toBe('retry')
  })

  it('maps 5xx → serverError with retry recovery', () => {
    const result500 = resolveApiError(ApiError.fromResponse(500, null))
    const result503 = resolveApiError(ApiError.fromResponse(503, null))
    for (const result of [result500, result503]) {
      expect(result.message).toBe('서버 오류가 발생했어요')
      expect(result.recovery?.type).toBe('retry')
    }
  })

  it('maps an unconfigured JWT backend to an account recovery message', () => {
    const result = resolveApiError(ApiError.fromResponse(503, {
      detail: 'JWT authentication is not configured',
      error: 'JWT authentication is not configured',
    }))

    expect(result.message).toBe('관리자 로그인 연결을 확인해 주세요')
    expect(result.hint).toContain('로그인 정보')
    expect(result.recovery?.type).toBe('login')
    expect(result.raw?.status).toBe(503)
  })

  it('maps NetworkError → networkError with retry recovery', () => {
    const result = resolveApiError(new NetworkError())
    expect(result.message).toBe('네트워크 연결을 확인해 주세요')
    expect(result.recovery?.type).toBe('retry')
  })

  it('maps native fetch failure → networkError', () => {
    const result = resolveApiError(new TypeError('Failed to fetch'))
    expect(result.message).toBe('네트워크 연결을 확인해 주세요')
    expect(result.recovery?.type).toBe('retry')
  })

  it('falls back to ApiError userMessage for non-mapped 4xx', () => {
    const error = ApiError.fromResponse(418, { message: '커피포트입니다' })
    const result = resolveApiError(error)
    expect(result.message).toBe('커피포트입니다')
    expect(result.recovery).toBeUndefined()
  })

  it('falls back to unknownError for empty errors', () => {
    expect(resolveApiError(null).message).toBe('알 수 없는 오류가 발생했어요')
    expect(resolveApiError(undefined).message).toBe('알 수 없는 오류가 발생했어요')
    expect(resolveApiError({}).message).toBe('알 수 없는 오류가 발생했어요')
  })

  it('preserves bare Error message when not network-shaped', () => {
    const result = resolveApiError(new Error('something custom went wrong'))
    expect(result.message).toBe('something custom went wrong')
    expect(result.recovery).toBeUndefined()
  })

  it('preserves bare string error', () => {
    const result = resolveApiError('manual string')
    expect(result.message).toBe('manual string')
  })
})
