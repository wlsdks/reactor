import { describe, expect, it } from 'vitest'
import { formatSessionUser } from '../ui/shared/formatSessionUser'

function translate(key: string, options?: Record<string, unknown>): string {
  if (key === 'conversations.users.localUser') return 'Local user'
  if (key === 'conversations.users.anonymousUser') return `User ${String(options?.id ?? '')}`
  return key
}

describe('formatSessionUser', () => {
  it('replaces generated snake-case account keys with a readable label', () => {
    expect(formatSessionUser(translate, 'user_001')).toBe('User 001')
  })

  it('keeps supported operator identities readable without exposing opaque keys', () => {
    expect(formatSessionUser(translate, 'local-user')).toBe('Local user')
    expect(formatSessionUser(translate, 'abc_def_12345')).toBe('User abc def…')
  })
})
