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

  if (typeof value !== 'string') throw new TypeError(`Missing string translation for ${path}`)
  return value
}

describe('input guard operator copy contract', () => {
  it('uses safety outcomes instead of implementation names for pipeline stages', () => {
    expect(readCopy('inputGuard.stages.llm-classification')).toBe('AI 판단 검사')
    expect(readCopy('inputGuard.stages.injection-detection')).toBe('지시문 우회 탐지')
    expect(readCopy('inputGuard.technicalDetails')).toBe('자세한 확인 정보')

    for (const path of [
      'inputGuard.stages.unicode-normalization',
      'inputGuard.stages.injection-detection',
      'inputGuard.stages.rule-classification',
      'inputGuard.stages.llm-classification',
      'inputGuard.stages.topic-drift',
      'inputGuard.stages.permission',
    ]) {
      expect(readCopy(path)).not.toMatch(/LLM|인젝션|유니코드|정규화/i)
    }
  })
})
