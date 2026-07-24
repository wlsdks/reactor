import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

type TranslationTree = Record<string, unknown>

const ko = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/shared/i18n/ko.json'), 'utf8'),
) as TranslationTree

function readCopy(path: string): string {
  const value = path.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object') return undefined
    return (current as TranslationTree)[segment]
  }, ko)

  if (typeof value !== 'string') {
    throw new TypeError(`Missing string translation for ${path}`)
  }

  return value
}

describe('RAG operator copy contract', () => {
  it('uses a task-oriented name and neutral details label', () => {
    expect(readCopy('nav.ragCache')).toBe('문서 검색과 답변 관리')
    expect(readCopy('ragCachePage.answerContract.technicalDetails')).toBe('자세한 확인 정보')
    expect(readCopy('ragCachePage.candidates.technicalDetails')).toBe('자세한 확인 정보')

    for (const path of [
      'nav.ragCache',
      'ragCachePage.answerContract.technicalDetails',
      'ragCachePage.candidates.technicalDetails',
    ]) {
      expect(readCopy(path)).not.toMatch(/RAG|캐시|개발자/i)
    }
  })
})
