import { describe, expect, it } from 'vitest'
import { formatModelName } from '../modelName'

describe('formatModelName', () => {
  it('removes backend revision suffixes from known model names', () => {
    expect(formatModelName('claude-sonnet-4-20250514')).toBe('Claude Sonnet')
    expect(formatModelName('gemma4:12b')).toBe('Gemma')
  })

  it('keeps unknown model names available for operators', () => {
    expect(formatModelName('partner-custom-model')).toBe('partner-custom-model')
  })
})
