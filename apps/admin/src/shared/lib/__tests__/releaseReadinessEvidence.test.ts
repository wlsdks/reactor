import { describe, expect, it } from 'vitest'
import {
  hasLangsmithPromotedCaseCoverage,
  hasLangsmithSyncEvidence,
  type LangsmithSyncEvidence,
} from '../releaseReadinessEvidence'

const completeEvidence: LangsmithSyncEvidence = {
  datasetName: 'reactor-release-regression',
  exampleCount: 2,
  caseCount: 2,
  exampleIds: ['example-1', 'example-2'],
  caseIds: ['case-1', 'case-2'],
  metadataCaseIds: ['case-1', 'case-2'],
  splitCounts: { regression: 2 },
  secretFree: true,
  sdkContract: 'Client.create_dataset/create_example',
  sdkContractFields: {
    datasetApi: 'Client.create_dataset',
    exampleApi: 'Client.create_example',
    metadataApi: 'Client.create_example.metadata',
  },
  exampleContract: {
    metadataOnly: true,
    secretScan: 'passed',
    requiredMetadata: ['case_id', 'split', 'source_suite'],
  },
}

describe('releaseReadinessEvidence', () => {
  it('accepts complete LangSmith sync evidence', () => {
    expect(hasLangsmithSyncEvidence(completeEvidence)).toBe(true)
  })

  it('rejects partial LangSmith evidence without SDK fields and example contract', () => {
    expect(hasLangsmithSyncEvidence({
      ...completeEvidence,
      sdkContractFields: null,
      exampleContract: null,
    })).toBe(false)
  })

  it('requires promoted cases to be covered by synced metadata cases', () => {
    expect(hasLangsmithPromotedCaseCoverage(['case-1', 'case-2'], ['case-1', 'case-2'])).toBe(true)
    expect(hasLangsmithPromotedCaseCoverage(['case-1', 'case-2'], ['case-1'])).toBe(false)
  })
})
