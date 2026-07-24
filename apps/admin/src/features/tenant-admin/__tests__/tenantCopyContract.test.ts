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

describe('tenant operator copy contract', () => {
  it('uses organization language in tenant-facing management views', () => {
    expect(readCopy('platformAdminPage.tenantAnalytics')).toBe('조직별 사용 현황')
    expect(readCopy('platformAdminPage.noTenants')).toBe('등록된 조직 없음')
    expect(readCopy('tenantsPage.analyticsLoadError')).toBe('조직별 사용 현황을 불러오지 못했습니다')

    for (const path of [
      'platformAdminPage.tenantAnalytics',
      'platformAdminPage.noTenants',
      'tenantsPage.analyticsLoadError',
      'tenantsPage.analyticsEmptyDescription',
      'tenantsPage.emptyDescription',
      'tenantsPage.detailLoadError',
    ]) {
      expect(readCopy(path)).not.toContain('테넌트')
    }
  })
})
