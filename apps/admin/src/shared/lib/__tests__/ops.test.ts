import { describe, it, expect } from 'vitest'
import { summarizeStatus, classifyLoadIssue } from '../ops'

describe('summarizeStatus', () => {
  it('returns FAIL if any signal is FAIL', () => {
    const signals = [
      { status: 'PASS' as const },
      { status: 'FAIL' as const },
      { status: 'WARN' as const },
    ]
    expect(summarizeStatus(signals)).toBe('FAIL')
  })

  it('returns WARN if any signal is WARN and none are FAIL', () => {
    const signals = [
      { status: 'PASS' as const },
      { status: 'WARN' as const },
    ]
    expect(summarizeStatus(signals)).toBe('WARN')
  })

  it('returns PASS when all signals are PASS', () => {
    const signals = [
      { status: 'PASS' as const },
      { status: 'PASS' as const },
    ]
    expect(summarizeStatus(signals)).toBe('PASS')
  })

  it('returns PASS for empty signal array', () => {
    expect(summarizeStatus([])).toBe('PASS')
  })
})

describe('classifyLoadIssue', () => {
  it('returns null for null input', () => {
    expect(classifyLoadIssue(null)).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(classifyLoadIssue('')).toBeNull()
  })

  it('returns null for whitespace-only string', () => {
    expect(classifyLoadIssue('   ')).toBeNull()
  })

  it('returns notAdvertised for HTTP 404', () => {
    expect(classifyLoadIssue('HTTP 404 Not Found')).toBe('notAdvertised')
  })

  it('returns accessDenied for HTTP 401', () => {
    expect(classifyLoadIssue('HTTP 401 Unauthorized')).toBe('accessDenied')
  })

  it('returns accessDenied for HTTP 403', () => {
    expect(classifyLoadIssue('HTTP 403 Forbidden')).toBe('accessDenied')
  })

  it('returns transportFailure for socket hang up', () => {
    expect(classifyLoadIssue('socket hang up')).toBe('transportFailure')
  })

  it('returns transportFailure for failed to fetch', () => {
    expect(classifyLoadIssue('Failed to fetch')).toBe('transportFailure')
  })

  it('returns transportFailure for NetworkError', () => {
    expect(classifyLoadIssue('NetworkError when attempting')).toBe('transportFailure')
  })

  it('returns transportFailure for empty reply', () => {
    expect(classifyLoadIssue('empty reply from server')).toBe('transportFailure')
  })

  it('returns httpError for other error messages', () => {
    expect(classifyLoadIssue('HTTP 500 Internal Server Error')).toBe('httpError')
  })
})
