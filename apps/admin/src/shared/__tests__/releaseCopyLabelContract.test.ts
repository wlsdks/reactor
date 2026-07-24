import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

type TranslationTree = Record<string, unknown>

const ko = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/shared/i18n/ko.json'), 'utf8'),
) as TranslationTree

const releaseCopyLabelKeys = [
  'dashboard.release.aggregateDiagnostics.copyCommand',
  'dashboard.release.recommendation.copyNextAction',
  'dashboard.release.warningList.copyReviewCommand',
  'dashboard.release.warningList.copyRemediationCommand',
  'dashboard.release.warningEvidence.copyReviewCommand',
  'dashboard.release.warningEvidence.copyRemediationCommand',
  'dashboard.release.warningReviewHandoff.copyReviewCommand',
  'dashboard.release.warningReviewHandoff.copyRemediationCommand',
  'dashboard.release.handoff.copyCommand',
  'dashboard.release.smokeHandoff.copyPreflightCommand',
  'dashboard.release.smokeHandoff.copyReleaseSmokeCommand',
  'dashboard.release.smoke.copyReadinessCommand',
  'integrationsPage.releaseSmoke.copyEnvTemplate',
  'integrationsPage.releaseSmoke.copyPreflightCommand',
  'integrationsPage.releaseSmoke.copyReleaseSmokeCommand',
  'integrationsPage.releaseSmoke.copyReadinessCommand',
  'modelsPage.providerSmoke.copyReadinessCommand',
  'feedbackPage.promotion.copyReadinessCommand',
  'evalsPage.langsmith.copyReadinessCommand',
] as const

function readTranslation(path: string): string {
  const value = path.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object') return undefined
    return (current as TranslationTree)[segment]
  }, ko)

  if (typeof value !== 'string') {
    throw new TypeError(`Missing string translation for ${path}`)
  }

  return value
}

describe('release copy label contract', () => {
  it('keeps release CopyButton labels as target names, leaving the copy verb to common.copy.aria', () => {
    expect(readTranslation('common.copy.aria')).toBe('{{label}} 복사')

    const labelsWithCopyVerb = releaseCopyLabelKeys
      .map((key) => [key, readTranslation(key)] as const)
      .filter(([, label]) => label.includes('복사'))

    expect(labelsWithCopyVerb).toEqual([])
  })
})
