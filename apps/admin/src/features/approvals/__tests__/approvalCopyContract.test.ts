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

describe('approval operator copy contract', () => {
  it('uses decision-oriented language instead of implementation queue terminology', () => {
    expect(readCopy('approvals.opsTitle')).toBe('승인 요청 현황')
    expect(readCopy('approvals.attentionTitle')).toBe('확인이 필요한 요청')
    expect(readCopy('approvals.queueTitle')).toBe('승인 요청 목록')

    for (const path of [
      'approvals.opsTitle',
      'approvals.readinessSummary',
      'approvals.readinessDetails',
      'approvals.opsDescription',
      'approvals.pendingRequestsCard',
      'approvals.queueTitle',
      'approvals.filterDescription',
      'approvals.attentionTitle',
      'approvals.attentionDescription',
    ]) {
      expect(readCopy(path)).not.toMatch(/준비 상태|큐|엔드포인트|메타데이터/i)
    }
  })
})
