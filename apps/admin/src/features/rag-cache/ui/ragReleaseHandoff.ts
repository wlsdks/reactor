import type { RagCandidateNextAction } from '../types'

function hasListValues(values: string[] | null | undefined): boolean {
  return (values?.filter(Boolean).length ?? 0) > 0
}

function hasNestedListValues(values: string[][] | null | undefined): boolean {
  return values?.some((group) => group.some(Boolean)) === true
}

function hasObjectValues(values: Record<string, unknown> | null | undefined): boolean {
  return Object.keys(values ?? {}).length > 0
}

export function hasRagReleaseActionEvidence(action: RagCandidateNextAction): boolean {
  return Boolean(
    action.releaseReadinessCommand
    || action.releaseReadinessFile
    || action.evalCaseId
    || action.sourceRunId
    || action.candidateTag
    || action.reportFile
    || action.caseFile
    || action.runFile
    || action.diagnosticsApi
    || action.suiteFile
    || action.datasetName
    || action.feedbackRating
    || action.feedbackSource
    || action.preflightFile
    || action.preflightEnvTemplate
    || action.replatformReadinessFile
    || action.smokePlanFile
    || action.releaseEvidenceFile
    || action.remediationCommand
    || action.envFileCommand
    || action.readinessReportArg
    || action.recommendedVersionBump
    || action.recommendedTagPattern
    || action.latestTagCommand
    || action.recommendedTagSource
    || hasListValues(action.workflowTags)
    || hasListValues(action.feedbackTags)
    || hasListValues(action.requiredReadinessReports)
    || Object.keys(action.readinessReports ?? {}).length > 0
    || hasNestedListValues(action.requiredEnvAnyOf)
    || hasListValues(action.missingEnvAnyOf)
    || hasListValues(action.recommendedEnv)
    || hasListValues(action.minorBoundaryReports)
    || hasListValues(action.dependsOnActionIds)
    || hasObjectValues(action.promotionCoverage)
    || hasObjectValues(action.citationMarkerContract)
  )
}
