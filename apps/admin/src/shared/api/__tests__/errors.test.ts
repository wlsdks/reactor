import { describe, it, expect } from 'vitest'
import { ApiError, NetworkError, sanitizeErrorMessage } from '../errors'

describe('ApiError', () => {
  it('creates with correct properties', () => {
    const err = new ApiError(404, 'NOT_FOUND', 'Not found', 'Entity 123 missing')
    expect(err).toBeInstanceOf(Error)
    expect(err.name).toBe('ApiError')
    expect(err.status).toBe(404)
    expect(err.code).toBe('NOT_FOUND')
    expect(err.userMessage).toBe('Not found')
    expect(err.serverMessage).toBe('Entity 123 missing')
    expect(err.message).toBe('Not found')
  })

  describe('fromResponse', () => {
    it('maps 400 to BAD_REQUEST', () => {
      const err = ApiError.fromResponse(400, null)
      expect(err.status).toBe(400)
      expect(err.code).toBe('BAD_REQUEST')
    })

    it('maps 403 to FORBIDDEN', () => {
      const err = ApiError.fromResponse(403, null)
      expect(err.code).toBe('FORBIDDEN')
    })

    it('maps 404 to NOT_FOUND', () => {
      const err = ApiError.fromResponse(404, null)
      expect(err.code).toBe('NOT_FOUND')
    })

    it('maps 409 to CONFLICT', () => {
      const err = ApiError.fromResponse(409, null)
      expect(err.code).toBe('CONFLICT')
    })

    it('maps 422 to VALIDATION', () => {
      const err = ApiError.fromResponse(422, null)
      expect(err.code).toBe('VALIDATION')
    })

    it('maps 429 to RATE_LIMIT', () => {
      const err = ApiError.fromResponse(429, null)
      expect(err.code).toBe('RATE_LIMIT')
    })

    it('maps 500 to SERVER_ERROR', () => {
      const err = ApiError.fromResponse(500, null)
      expect(err.code).toBe('SERVER_ERROR')
    })

    it('maps 502 to SERVER_ERROR', () => {
      const err = ApiError.fromResponse(502, null)
      expect(err.code).toBe('SERVER_ERROR')
    })

    it('maps unknown status to UNKNOWN', () => {
      const err = ApiError.fromResponse(418, null)
      expect(err.code).toBe('UNKNOWN')
    })

    it('extracts error field from body', () => {
      const err = ApiError.fromResponse(400, { error: 'Invalid name' })
      expect(err.serverMessage).toBe('Invalid name')
    })

    it('extracts message field from body', () => {
      const err = ApiError.fromResponse(400, { message: 'Name required' })
      expect(err.serverMessage).toBe('Name required')
    })

    it('extracts a FastAPI detail field when error and message are absent', () => {
      const err = ApiError.fromResponse(503, { detail: 'JWT authentication is not configured' })
      expect(err.serverMessage).toBe('JWT authentication is not configured')
      expect(err.userMessage).toBe('HTTP 503')
    })

    it('prefers error field over message field', () => {
      const err = ApiError.fromResponse(400, { error: 'Err', message: 'Msg' })
      expect(err.serverMessage).toBe('Err')
    })

    it('handles null body', () => {
      const err = ApiError.fromResponse(500, null)
      expect(err.serverMessage).toBeUndefined()
    })

    it('handles non-object body', () => {
      const err = ApiError.fromResponse(500, 'plain text')
      expect(err.serverMessage).toBeUndefined()
    })
  })
})

describe('NetworkError', () => {
  it('creates with correct properties', () => {
    const err = new NetworkError()
    expect(err).toBeInstanceOf(Error)
    expect(err.name).toBe('NetworkError')
  })
})

describe('sanitizeErrorMessage', () => {
  it('replaces "socket hang up" with network error', () => {
    const result = sanitizeErrorMessage('socket hang up')
    expect(result).toBe('네트워크 연결이 끊어졌어요')
  })

  it('replaces "ECONNREFUSED" with network error', () => {
    const result = sanitizeErrorMessage('connect ECONNREFUSED 127.0.0.1:3000')
    expect(result).toBe('네트워크 연결이 끊어졌어요')
  })

  it('replaces "ECONNRESET" with network error', () => {
    const result = sanitizeErrorMessage('read ECONNRESET')
    expect(result).toBe('네트워크 연결이 끊어졌어요')
  })

  it('replaces "timeout" with server error', () => {
    const result = sanitizeErrorMessage('Request timeout after 30000ms')
    expect(result).toBe('서버 오류가 발생했어요')
  })

  it('replaces "ETIMEDOUT" with server error', () => {
    const result = sanitizeErrorMessage('connect ETIMEDOUT 10.0.0.1:443')
    expect(result).toBe('서버 오류가 발생했어요')
  })

  it('replaces "Failed to fetch" with network error', () => {
    const result = sanitizeErrorMessage('Failed to fetch')
    expect(result).toBe('네트워크 연결이 끊어졌어요')
  })

  it('replaces "NetworkError" with network error', () => {
    const result = sanitizeErrorMessage('NetworkError when attempting to fetch resource')
    expect(result).toBe('네트워크 연결이 끊어졌어요')
  })

  it('returns original message for safe messages', () => {
    const result = sanitizeErrorMessage('Invalid email format')
    expect(result).toBe('Invalid email format')
  })

  it('is case-insensitive', () => {
    expect(sanitizeErrorMessage('Socket Hang Up')).toBe('네트워크 연결이 끊어졌어요')
    expect(sanitizeErrorMessage('TIMEOUT exceeded')).toBe('서버 오류가 발생했어요')
  })
})

describe('ApiError.fromResponse with technical server messages', () => {
  it('sanitizes socket hang up in server message', () => {
    const err = ApiError.fromResponse(500, { error: 'socket hang up' })
    expect(err.userMessage).toBe('네트워크 연결이 끊어졌어요')
    expect(err.serverMessage).toBe('socket hang up')
  })

  it('sanitizes ECONNREFUSED in server message', () => {
    const err = ApiError.fromResponse(502, { message: 'connect ECONNREFUSED' })
    expect(err.userMessage).toBe('네트워크 연결이 끊어졌어요')
  })

  it('sanitizes timeout in server message', () => {
    const err = ApiError.fromResponse(504, { error: 'Gateway Timeout' })
    expect(err.userMessage).toBe('서버 오류가 발생했어요')
  })

  it('uses server message when it is safe', () => {
    const err = ApiError.fromResponse(400, { error: 'Name must be unique' })
    expect(err.userMessage).toBe('Name must be unique')
  })

  it('falls back to i18n status string when no server message', () => {
    const err = ApiError.fromResponse(404, null)
    // i18n is not initialized in tests, so falls back to "HTTP 404"
    expect(err.userMessage).toBe('HTTP 404')
  })
})
