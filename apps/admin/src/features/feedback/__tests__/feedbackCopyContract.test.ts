import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

type TranslationTree = Record<string, unknown>

const ko = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/shared/i18n/ko.json'), 'utf8'),
) as TranslationTree

function readFeedbackCopy(path: string): string {
  const value = path.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object') return undefined
    return (current as TranslationTree)[segment]
  }, ko)

  if (typeof value !== 'string') {
    throw new TypeError(`Missing string translation for ${path}`)
  }

  return value
}

describe('feedback primary copy contract', () => {
  it('uses an operator decision instead of implementation vocabulary for evaluation follow-up', () => {
    expect(readFeedbackCopy('feedbackPage.evalLifecycle.column')).toBe('품질 점검 반영')
    expect(readFeedbackCopy('feedbackPage.evalLifecycle.stage.ready')).toBe('대표 사례로 추가 가능')
    expect(readFeedbackCopy('feedbackPage.evalPromotion.title')).toBe('대표 점검 사례로 추가')
    expect(readFeedbackCopy('feedbackPage.evalPromotion.action')).toBe('대표 사례로 추가')
    expect(readFeedbackCopy('feedbackPage.evalPromotion.syncAction')).toBe('결과 저장 확인')

    for (const path of [
      'feedbackPage.evalLifecycle.column',
      'feedbackPage.evalLifecycle.stage.ready',
      'feedbackPage.evalPromotion.title',
      'feedbackPage.evalPromotion.description',
      'feedbackPage.evalPromotion.action',
      'feedbackPage.evalPromotion.syncAction',
    ]) {
      expect(readFeedbackCopy(path)).not.toMatch(/승격|Eval|LangSmith/)
    }
  })

  it('keeps the expandable feedback handoff in Korean operational language', () => {
    expect(readFeedbackCopy('feedbackPage.promotion.boundaryChain')).toBe('이 의견이 반영되는 곳')
    expect(readFeedbackCopy('feedbackPage.promotion.handoffQueue')).toBe('연동 상태 자세히 보기')
    expect(readFeedbackCopy('feedbackPage.promotion.releaseGateEvidence')).toBe('출시 판단에 반영된 정보')

    for (const path of [
      'feedbackPage.promotion.boundaryChain',
      'feedbackPage.promotion.handoffQueue',
      'feedbackPage.promotion.handoffReviewed',
      'feedbackPage.promotion.handoffEvalCase',
      'feedbackPage.promotion.handoffReadiness',
      'feedbackPage.promotion.releaseGateEvidence',
      'feedbackPage.promotion.productBoundaryFlow',
      'feedbackPage.promotion.langsmithSyncHandoff',
      'feedbackPage.promotion.openRagCandidates',
    ]) {
      expect(readFeedbackCopy(path)).not.toMatch(/evidence|handoff|readiness|queue|case|sync|boundary|provenance/i)
    }
  })
})
