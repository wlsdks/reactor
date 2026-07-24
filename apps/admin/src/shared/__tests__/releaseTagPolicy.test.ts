import { describe, expect, it } from 'vitest'
import {
  evaluateReleaseTagPolicy,
  normalizeRemoteTagRefs,
} from '../../../scripts/release-tag-policy.mjs'

describe('verify-release-tags policy', () => {
  it('shares the backend release tag while allowing older monorepo tags', () => {
    const result = evaluateReleaseTagPolicy({
      packageVersion: '1.2.0',
      backendVersion: '1.2.0',
      localTags: ['v1.1.0', 'v1.2.0', 'v1.1.37', 'v1.0.14'],
      remoteTags: ['v1.1.0', 'v1.2.0', 'v1.1.38', 'v2.0.0'],
    })

    expect(result.ok).toBe(true)
    expect(result.requiredTag).toBe('v1.2.0')
  })

  it('fails when backend and admin versions diverge', () => {
    const result = evaluateReleaseTagPolicy({
      packageVersion: '1.2.0',
      backendVersion: '1.3.0',
      localTags: ['v1.2.0'],
      remoteTags: ['v1.2.0'],
    })

    expect(result.ok).toBe(false)
    expect(result.failures).toEqual([
      'admin version 1.2.0 does not match backend version 1.3.0',
    ])
  })

  it('normalizes annotated remote tag refs before allowlist checks', () => {
    expect(normalizeRemoteTagRefs([
      '1111111\trefs/tags/v1.1.0',
      '2222222\trefs/tags/v1.1.0^{}',
      '3333333\trefs/tags/v1.1.1',
    ])).toEqual(['v1.1.0', 'v1.1.1'])
  })
})
