export interface LangsmithSyncEvidence {
  datasetName?: string | null
  exampleCount?: number | null
  caseCount?: number | null
  exampleIds?: string[] | null
  caseIds?: string[] | null
  metadataCaseIds?: string[] | null
  splitCounts?: Record<string, number> | null
  secretFree?: boolean | null
  sdkContract?: string | null
  sdkContractFields?: Record<string, unknown> | null
  exampleContract?: Record<string, unknown> | null
}

export function hasEvidenceEntries(values: string[] | null | undefined): boolean {
  return (values?.filter(Boolean).length ?? 0) > 0
}

export function hasLangsmithSyncEvidence(
  langsmithSync: LangsmithSyncEvidence | null | undefined,
): boolean {
  if (!langsmithSync) return false
  return Boolean(langsmithSync.datasetName)
    && (langsmithSync.exampleCount ?? 0) > 0
    && hasEvidenceEntries(langsmithSync.exampleIds)
    && (langsmithSync.caseCount ?? 0) > 0
    && hasEvidenceEntries(langsmithSync.caseIds)
    && hasEvidenceEntries(langsmithSync.metadataCaseIds)
    && Object.keys(langsmithSync.splitCounts ?? {}).length > 0
    && Boolean(langsmithSync.sdkContract)
    && Object.keys(langsmithSync.sdkContractFields ?? {}).length > 0
    && Object.keys(langsmithSync.exampleContract ?? {}).length > 0
    && langsmithSync.secretFree === true
}

export function hasLangsmithPromotedCaseCoverage(
  caseIds: string[] | null | undefined,
  syncedCaseIds: string[] | null | undefined,
): boolean {
  const cases = caseIds?.filter(Boolean) ?? []
  if (cases.length === 0) return false
  const synced = new Set(syncedCaseIds?.filter(Boolean) ?? [])
  return cases.every((caseId) => synced.has(caseId))
}
