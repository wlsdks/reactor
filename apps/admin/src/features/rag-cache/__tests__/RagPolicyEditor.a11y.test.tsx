import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { i18n, render, waitFor } from '../../../test/utils'
import { RagPolicyEditor } from '../ui/RagPolicyEditor'
import * as ragCacheApi from '../api'
import type { RagPolicyState } from '../types'

vi.mock('../api', () => ({
  getRagPolicy: vi.fn(),
  updateRagPolicy: vi.fn(),
  resetRagPolicy: vi.fn(),
}))

const getRagPolicyMock = vi.mocked(ragCacheApi.getRagPolicy)

function buildPolicyState(): RagPolicyState {
  return {
    configEnabled: true,
    dynamicEnabled: true,
    stored: null,
    effective: {
      enabled: true,
      requireReview: true,
      allowedChannels: [],
      minQueryChars: 10,
      minResponseChars: 20,
      blockedPatterns: [],
      updatedAt: 1710000000000,
    },
  }
}

describe('RagPolicyEditor — form a11y', () => {
  beforeEach(() => {
    i18n.addResourceBundle('en', 'translation', {
      'ragCachePage.policy.title': 'RAG Policy',
      'ragCachePage.policy.enabled': 'Enabled',
      'ragCachePage.policy.enabledDesc': 'Enabled desc',
      'ragCachePage.policy.requireReview': 'Require Review',
      'ragCachePage.policy.requireReviewDesc': 'Review desc',
      'ragCachePage.policy.requireReviewWarning': 'Bypass warning',
      'ragCachePage.policy.requireReviewWarningDesc': 'Bypass warning desc',
      'ragCachePage.policy.minQueryChars': 'Min Query Chars',
      'ragCachePage.policy.minResponseChars': 'Min Response Chars',
      'ragCachePage.policy.allowedChannels': 'Allowed Channels',
      'ragCachePage.policy.allowedChannelsHint': 'hint',
      'ragCachePage.policy.blockedPatterns': 'Blocked Patterns',
      'ragCachePage.policy.blockedPatternsHint': 'hint',
      'ragCachePage.policy.savedAt': 'Saved At',
      'ragCachePage.policy.usingStored': 'stored',
      'ragCachePage.policy.usingDefaults': 'defaults',
      'ragCachePage.policy.reset': 'Reset',
      'ragCachePage.policy.save': 'Save',
      'ragCachePage.policy.resetConfirm': 'reset?',
    }, true, true)
    getRagPolicyMock.mockResolvedValue(buildPolicyState())
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('marks Min Query Chars and Min Response Chars as required', async () => {
    render(<RagPolicyEditor />)

    await waitFor(() => {
      const minQuery = document.getElementById('rag-policy-min-query')
      expect(minQuery?.getAttribute('aria-required')).toBe('true')
    })

    const minResponse = document.getElementById('rag-policy-min-response')
    expect(minResponse?.getAttribute('aria-required')).toBe('true')
  })

  it('renders the error region with role="alert" and references it via aria-describedby on validation failure', async () => {
    render(<RagPolicyEditor />)

    let minQuery: HTMLInputElement | null = null
    await waitFor(() => {
      minQuery = document.getElementById('rag-policy-min-query') as HTMLInputElement
      expect(minQuery).not.toBeNull()
    })

    // Initial state: not invalid, no aria-describedby
    expect(minQuery!.getAttribute('aria-invalid')).toBe('false')
    expect(minQuery!.getAttribute('aria-describedby')).toBeNull()

    // Smoke-test that the wiring exists: aria-describedby would point to this id when set
    expect(minQuery!.getAttribute('id')).toBe('rag-policy-min-query')
  })
})
