import { describe, expect, it } from 'vitest'
import ko from '../../../shared/i18n/ko.json'
import { RESOURCE_GROUPS } from '../constants'

describe('RBAC translation contract', () => {
  it('provides a Korean resource label for every recognized backend permission target', () => {
    const resourceLabels = ko.rbacPage.resources as Record<string, string>

    for (const resource of Object.keys(RESOURCE_GROUPS)) {
      expect(resourceLabels[resource]).toMatch(/\S/)
    }
  })
})
