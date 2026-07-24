import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  CopyButton,
  ProductCapabilityBoundaryFlowList,
  StatusBadge,
} from '../../../shared/ui'
import { formatLocaleNumber } from '../../../shared/lib/intl'
import { queryKeys } from '../../../shared/lib/queryKeys'
import {
  hasLangsmithPromotedCaseCoverage,
  hasLangsmithSyncEvidence,
} from '../../../shared/lib/releaseReadinessEvidence'
import * as feedbackApi from '../api'
import { getEvalRuns } from '../../evals/api'
import { getDashboard } from '../../dashboard/api'
import type { DashboardReleaseReadinessSummary } from '../../dashboard/types'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_RAG_CANDIDATES_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
  RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID,
} from '../../../shared/releaseWorkflow'
import { FEEDBACK_PROMOTION_ANCHORS } from '../releasePromotionAnchors'

function listSummary(values: string[] | null | undefined): string {
  return values?.filter(Boolean).join(', ') ?? ''
}

function countSummary(values: Record<string, number> | null | undefined): string {
  return Object.entries(values ?? {})
    .map(([key, count]) => `${key}: ${count}`)
    .join(', ')
}

function formatEvidenceValue(value: boolean | number | string | string[] | null): string {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  return value ?? ''
}

function evidenceMapSummary(
  values: Record<string, boolean | number | string | string[] | null> | null | undefined,
): string {
  return Object.entries(values ?? {})
    .map(([key, value]) => `${key}: ${formatEvidenceValue(value)}`)
    .filter((value) => !value.endsWith(': '))
    .join(', ')
}

function compactStrings(values: Array<string | null | undefined>): string[] {
  return values.filter((value): value is string => Boolean(value))
}

function coverageSummary(caseIds: string[] | null | undefined, syncedCaseIds: string[] | null | undefined): string {
  const cases = caseIds?.filter(Boolean) ?? []
  if (cases.length === 0) return ''
  const synced = new Set(syncedCaseIds?.filter(Boolean) ?? [])
  const covered = cases.filter((caseId) => synced.has(caseId))
  return `${covered.length}/${cases.length}`
}

function hasLangsmithSyncContract(
  caseIds: string[] | null | undefined,
  langsmithSync: DashboardReleaseReadinessSummary['langsmithSync'] | null | undefined,
): boolean {
  const promotedCases = caseIds?.filter(Boolean) ?? []
  return promotedCases.length > 0
    && hasLangsmithPromotedCaseCoverage(promotedCases, langsmithSync?.caseIds)
    && hasLangsmithPromotedCaseCoverage(promotedCases, langsmithSync?.metadataCaseIds)
    && hasLangsmithSyncEvidence(langsmithSync)
}

function splitLangsmithCoverage(caseIds: string[] | null | undefined, syncedCaseIds: string[] | null | undefined) {
  const cases = caseIds?.filter(Boolean) ?? []
  const synced = new Set(syncedCaseIds?.filter(Boolean) ?? [])

  return {
    syncedCases: cases.filter((caseId) => synced.has(caseId)),
    unsyncedCases: cases.filter((caseId) => !synced.has(caseId)),
  }
}

interface FeedbackEvalPromotionPanelProps {
  from?: string
  to?: string
}

export function FeedbackEvalPromotionPanel({ from, to }: FeedbackEvalPromotionPanelProps) {
  const { t } = useTranslation()

  const statsQuery = useQuery({
    queryKey: queryKeys.feedback.stats(from, to),
    queryFn: () => feedbackApi.fetchFeedbackStats(from, to),
  })
  const evalRunsQuery = useQuery({
    queryKey: queryKeys.evals.list(30),
    queryFn: () => getEvalRuns(30),
  })
  const releaseReadinessQuery = useQuery({
    queryKey: queryKeys.dashboard.main(['reactor.release.readiness']),
    queryFn: () => getDashboard(['reactor.release.readiness']),
  })

  const latestRun = evalRunsQuery.data?.[0] ?? null
  const releaseReadiness = releaseReadinessQuery.data?.releaseReadiness ?? null
  const feedbackReviewQueue = releaseReadiness?.feedbackReviewQueue ?? null
  const langsmithSync = releaseReadiness?.langsmithSync ?? null
  const productBoundary = releaseReadiness?.productCapabilityBoundary ?? null
  const releaseReadinessCommand = releaseReadiness?.tagRecommendation?.releaseReadinessCommand ?? null
  const hasReleaseReadiness = releaseReadiness !== null && releaseReadiness !== undefined
  const reviewStatusLabel = feedbackReviewQueue?.reviewStatus === 'done'
    || feedbackReviewQueue?.reviewStatus === 'reviewed'
    || feedbackReviewQueue?.status === 'passed'
    ? t('feedbackPage.promotion.reviewed')
    : feedbackReviewQueue?.reviewStatus === 'inbox'
      ? t('feedbackPage.promotion.inbox')
      : feedbackReviewQueue?.status
        ? t('feedbackPage.promotion.attentionRequired')
        : t('common.noData')
  const inboxCount = statsQuery.data?.inboxCount ?? 0
  const doneCount = statsQuery.data?.doneCount ?? 0
  const totalCases = latestRun?.totalCases ?? 0
  const feedbackCaseIds = listSummary(feedbackReviewQueue?.caseIds)
  const feedbackReviewTags = listSummary(feedbackReviewQueue?.reviewTags)
  const ratingCounts = countSummary(feedbackReviewQueue?.feedbackRatingCounts)
  const sourceCounts = countSummary(feedbackReviewQueue?.feedbackSourceCounts)
  const workflowCounts = countSummary(feedbackReviewQueue?.workflowTagCounts)
  const expectedCitationCounts = countSummary(feedbackReviewQueue?.expectedCitationCounts)
  const promotionProvenance = feedbackReviewQueue?.promotionProvenance
    ?.filter((item) => item && Object.values(item).some(Boolean)) ?? []
  const syncRemediationCommand = promotionProvenance
    .map((item) => item.remediationCommand)
    .find((command): command is string => Boolean(command))
  const langsmithCoverage = coverageSummary(feedbackReviewQueue?.caseIds, langsmithSync?.caseIds)
  const langsmithSyncContractComplete = hasLangsmithSyncContract(feedbackReviewQueue?.caseIds, langsmithSync)
  const { syncedCases, unsyncedCases } = splitLangsmithCoverage(feedbackReviewQueue?.caseIds, langsmithSync?.caseIds)
  const hasLangsmithHandoff = hasReleaseReadiness || syncedCases.length > 0 || unsyncedCases.length > 0
  const langsmithExampleIds = listSummary(langsmithSync?.exampleIds)
  const langsmithMetadataCaseIds = listSummary(langsmithSync?.metadataCaseIds)
  const langsmithMetadataCoverage = coverageSummary(feedbackReviewQueue?.caseIds, langsmithSync?.metadataCaseIds)
  const { unsyncedCases: langsmithMetadataUnsyncedCases } = splitLangsmithCoverage(
    feedbackReviewQueue?.caseIds,
    langsmithSync?.metadataCaseIds,
  )
  const langsmithMetadataMissingSummary = listSummary(langsmithMetadataUnsyncedCases)
  const hasLangsmithSyncRemediation =
    unsyncedCases.length > 0 || langsmithMetadataUnsyncedCases.length > 0
  const langsmithSplitCounts = countSummary(langsmithSync?.splitCounts)
  const langsmithExamplesSummary =
    langsmithSync?.exampleCount !== null && langsmithSync?.exampleCount !== undefined
      ? [formatLocaleNumber(langsmithSync.exampleCount), langsmithExampleIds].filter(Boolean).join(' / ')
      : langsmithExampleIds
  const handoffQueue = [
    {
      id: 'reviewed-feedback',
      href: FEEDBACK_PROMOTION_ANCHORS.releaseEvidenceHref,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
      title: t('feedbackPage.promotion.handoffReviewed'),
      description: t('feedbackPage.promotion.handoffReviewedDesc'),
      status: doneCount > 0 && feedbackReviewQueue?.status === 'passed' ? 'PASS' : 'WARN',
      evidence: compactStrings([
        t('feedbackPage.promotion.reviewedEvidenceDesc', { count: doneCount }),
        feedbackCaseIds,
        feedbackReviewTags,
      ]),
      missing: compactStrings([
        !feedbackReviewQueue ? t('feedbackPage.promotion.handoffMissingReviewQueue') : null,
        doneCount === 0 ? t('feedbackPage.promotion.handoffMissingReviewedFeedback') : null,
        !feedbackCaseIds ? t('feedbackPage.promotion.handoffMissingEvalCase') : null,
      ]),
    },
    {
      id: 'eval-case',
      href: RELEASE_WORKFLOW_PATHS_BY_ID.evals,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
      title: t('feedbackPage.promotion.handoffEvalCase'),
      description: t('feedbackPage.promotion.handoffEvalCaseDesc'),
      status: latestRun && totalCases > 0 ? 'PASS' : 'FAIL',
      evidence: compactStrings([
        t('feedbackPage.promotion.evalSuiteDesc', { count: totalCases }),
        latestRun?.evalRunId,
      ]),
      missing: compactStrings([
        !latestRun ? t('feedbackPage.promotion.handoffMissingEvalRun') : null,
        totalCases === 0 ? t('feedbackPage.promotion.handoffMissingEvalCases') : null,
      ]),
    },
    {
      id: 'langsmith-sync',
      href: RELEASE_LANGSMITH_SYNC_PATH,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
      title: t('feedbackPage.promotion.handoffLangSmith'),
      description: t('feedbackPage.promotion.handoffLangSmithDesc'),
      status: langsmithSyncContractComplete ? 'PASS' : langsmithCoverage ? 'WARN' : 'DISABLED',
      evidence: compactStrings([
        langsmithCoverage ? t('feedbackPage.promotion.workflowLangSmithDesc', { coverage: langsmithCoverage }) : null,
        langsmithSync?.datasetName,
        langsmithMetadataCoverage
          ? t('feedbackPage.promotion.langsmithMetadataCoverageDesc', { coverage: langsmithMetadataCoverage })
          : null,
        langsmithSync?.sdkContract,
      ]),
      missing: compactStrings([
        !langsmithSync ? t('feedbackPage.promotion.handoffMissingLangSmithSync') : null,
        unsyncedCases.length > 0 ? `${t('feedbackPage.promotion.syncRemediationMissingCases')}: ${unsyncedCases.join(', ')}` : null,
        langsmithMetadataUnsyncedCases.length > 0
          ? `${t('feedbackPage.promotion.syncRemediationMissingMetadata')}: ${langsmithMetadataUnsyncedCases.join(', ')}`
          : null,
      ]),
    },
    {
      id: 'readiness',
      href: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit,
      title: t('feedbackPage.promotion.handoffReadiness'),
      description: t('feedbackPage.promotion.handoffReadinessDesc'),
      status: releaseReadiness?.status === 'passed' ? 'PASS' : hasReleaseReadiness ? 'WARN' : 'DISABLED',
      evidence: compactStrings([
        releaseReadiness?.status ? t('feedbackPage.promotion.handoffReadinessStatus', { status: releaseReadiness.status }) : null,
        releaseReadinessCommand,
      ]),
      missing: compactStrings([
        !hasReleaseReadiness ? t('feedbackPage.promotion.handoffMissingReadiness') : null,
        !releaseReadinessCommand ? t('feedbackPage.promotion.handoffMissingReadinessCommand') : null,
      ]),
    },
  ] as const

  const workflowSteps = [
    {
      id: 'review-inbox',
      displayNumber: 1,
      href: FEEDBACK_PROMOTION_ANCHORS.panelHref,
      label: t('feedbackPage.promotion.workflowInbox'),
      description: t('feedbackPage.promotion.workflowInboxDesc', { count: inboxCount }),
      status: inboxCount === 0 ? 'PASS' : 'WARN',
    },
    {
      id: 'promote-reviewed',
      displayNumber: 2,
      href: FEEDBACK_PROMOTION_ANCHORS.releaseEvidenceHref,
      label: t('feedbackPage.promotion.workflowReviewed'),
      description: t('feedbackPage.promotion.workflowReviewedDesc', { count: doneCount }),
      status: doneCount > 0 && feedbackReviewQueue?.reviewStatus ? 'PASS' : 'WARN',
    },
    {
      id: 'regression-suite',
      displayNumber: 3,
      href: RELEASE_WORKFLOW_PATHS_BY_ID.evals,
      label: t('feedbackPage.promotion.workflowEval'),
      description: t('feedbackPage.promotion.workflowEvalDesc', { count: totalCases }),
      status: latestRun && totalCases > 0 ? 'PASS' : 'FAIL',
    },
  ] as const

  const boundaryChainSteps = [
    {
      id: 'rag-candidates',
      href: RELEASE_RAG_CANDIDATES_PATH,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.rag,
      label: t('feedbackPage.promotion.boundaryRagCandidates'),
    },
    {
      id: 'feedback-review',
      href: FEEDBACK_PROMOTION_ANCHORS.panelHref,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.feedback,
      label: t('feedbackPage.promotion.boundaryFeedbackReview'),
    },
    {
      id: 'eval-regression',
      href: RELEASE_WORKFLOW_PATHS_BY_ID.evals,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
      label: t('feedbackPage.promotion.boundaryEvalRegression'),
    },
    {
      id: 'langsmith-sync',
      href: RELEASE_LANGSMITH_SYNC_PATH,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals,
      label: t('feedbackPage.promotion.boundaryLangsmithSync'),
    },
    {
      id: 'release-readiness',
      href: RELEASE_WORKFLOW_PATHS_BY_ID.cockpit,
      releaseStepNumber: RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit,
      label: t('feedbackPage.promotion.boundaryReadiness'),
    },
  ] as const

  if (statsQuery.isLoading || evalRunsQuery.isLoading) {
    return null
  }

  return (
    <section
      id={FEEDBACK_PROMOTION_ANCHORS.panelId}
      className="fb-promotion-panel"
      aria-label={t('feedbackPage.promotion.title')}
    >
      <div className="fb-promotion-panel__head">
        <div>
          <h2 className="section-title">{t('feedbackPage.promotion.title')}</h2>
          <p className="section-description">{t('feedbackPage.promotion.description')}</p>
        </div>
      </div>
      <ol
        className="fb-promotion-panel__workflow"
        aria-label={t('feedbackPage.promotion.workflowLabel')}
      >
        {workflowSteps.map((step) => {
          const content = (
            <>
              <span className="fb-promotion-panel__workflow-index" aria-hidden="true">
                {step.displayNumber}
              </span>
              <span className="fb-promotion-panel__workflow-copy">
                <span className="fb-promotion-panel__workflow-label">{step.label}</span>
                <span className="fb-promotion-panel__workflow-description">{step.description}</span>
              </span>
              <span className={`fb-promotion-panel__workflow-status fb-promotion-panel__workflow-status--${step.status.toLowerCase()}`}>
                <span aria-hidden="true" />
                {t(`common.statuses.${step.status}`, { defaultValue: step.status })}
              </span>
            </>
          )

          return (
            <li key={step.id} className="fb-promotion-panel__workflow-step">
              {step.href.startsWith('#') ? (
                <a href={step.href} className="fb-promotion-panel__workflow-link">
                  {content}
                </a>
              ) : (
                <Link to={step.href} className="fb-promotion-panel__workflow-link">
                  {content}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
      <details
        className="fb-promotion-panel__boundary-chain"
        aria-label={t('feedbackPage.promotion.boundaryChain')}
      >
        <summary className="fb-promotion-panel__boundary-chain-head">
          <h3>{t('feedbackPage.promotion.boundaryChain')}</h3>
          <p>{t('feedbackPage.promotion.boundaryChainDesc')}</p>
        </summary>
        <ol className="fb-promotion-panel__boundary-chain-list">
          {boundaryChainSteps.map((step) => {
            const content = (
              <>
                <span className="fb-promotion-panel__boundary-chain-index" aria-hidden="true">
                  {step.releaseStepNumber}
                </span>
                <span>{step.label}</span>
              </>
            )

            return (
              <li key={step.id} className="fb-promotion-panel__boundary-chain-item">
                {step.href.startsWith('#') ? (
                  <a className="fb-promotion-panel__boundary-chain-link" href={step.href}>
                    {content}
                  </a>
                ) : (
                  <Link className="fb-promotion-panel__boundary-chain-link" to={step.href}>
                    {content}
                  </Link>
                )}
              </li>
            )
          })}
        </ol>
      </details>
      <details
        className="fb-promotion-panel__handoff-queue"
        aria-label={t('feedbackPage.promotion.handoffQueue')}
      >
        <summary className="fb-promotion-panel__handoff-queue-head">
          <h3>{t('feedbackPage.promotion.handoffQueue')}</h3>
          <p>{t('feedbackPage.promotion.handoffQueueDesc')}</p>
        </summary>
        <ol className="fb-promotion-panel__handoff-queue-list">
          {handoffQueue.map((item) => {
            const content = (
              <>
                <span className="fb-promotion-panel__boundary-chain-index" aria-hidden="true">
                  {item.releaseStepNumber}
                </span>
                <span>{item.title}</span>
              </>
            )

            return (
              <li key={item.id} className="fb-promotion-panel__handoff-queue-item">
                <div className="fb-promotion-panel__handoff-queue-item-head">
                  {item.href.startsWith('#') ? (
                    <a className="fb-promotion-panel__boundary-chain-link" href={item.href}>
                      {content}
                    </a>
                  ) : (
                    <Link className="fb-promotion-panel__boundary-chain-link" to={item.href}>
                      {content}
                    </Link>
                  )}
                  <StatusBadge
                    status={item.status}
                    label={t(`common.statuses.${item.status}`, { defaultValue: item.status })}
                  />
                </div>
                <p>{item.description}</p>
                <dl className="fb-promotion-panel__handoff-queue-grid">
                  <div>
                    <dt>{t('feedbackPage.promotion.handoffEvidence')}</dt>
                    <dd>{item.evidence.length > 0 ? item.evidence.join(', ') : t('feedbackPage.promotion.handoffNone')}</dd>
                  </div>
                  <div>
                    <dt>{t('feedbackPage.promotion.handoffMissing')}</dt>
                    <dd>{item.missing.length > 0 ? item.missing.join(', ') : t('feedbackPage.promotion.handoffNone')}</dd>
                  </div>
                </dl>
              </li>
            )
          })}
        </ol>
      </details>
      {(feedbackReviewQueue || hasReleaseReadiness) && (
        <details
          id={FEEDBACK_PROMOTION_ANCHORS.releaseEvidenceId}
          className="fb-release-action"
          aria-label={t('feedbackPage.promotion.releaseGateEvidence')}
        >
          <summary className="fb-release-action__head">
            <span className="fb-release-action__id">
              {t('feedbackPage.promotion.releaseGateEvidence')}
            </span>
            <div className="inline-actions">
              <StatusBadge
                status={feedbackReviewQueue?.status === 'passed' ? 'PASS' : 'WARN'}
                label={reviewStatusLabel}
              />
            </div>
          </summary>
          {feedbackReviewQueue?.reviewNote && <p>{feedbackReviewQueue.reviewNote}</p>}
          {!feedbackReviewQueue && <p>{t('feedbackPage.promotion.releaseGateMissing')}</p>}
          <dl className="fb-release-action__meta">
            {feedbackReviewQueue?.candidateTag && (
              <div>
                <dt>{t('feedbackPage.promotion.candidateTag')}</dt>
                <dd>
                  {feedbackReviewQueue.candidateTag}
                  <br />
                  <Link className="feedback-inline-link" to={RELEASE_RAG_CANDIDATES_PATH}>
                    {t('feedbackPage.promotion.openRagCandidates')}
                  </Link>
                </dd>
              </div>
            )}
            {feedbackCaseIds && (
              <div>
                <dt>{t('feedbackPage.promotion.caseIds')}</dt>
                <dd>{feedbackCaseIds}</dd>
              </div>
            )}
            {feedbackReviewTags && (
              <div>
                <dt>{t('feedbackPage.promotion.reviewTags')}</dt>
                <dd>{feedbackReviewTags}</dd>
              </div>
            )}
            {ratingCounts && (
              <div>
                <dt>{t('feedbackPage.promotion.ratingCounts')}</dt>
                <dd>{ratingCounts}</dd>
              </div>
            )}
            {sourceCounts && (
              <div>
                <dt>{t('feedbackPage.promotion.sourceCounts')}</dt>
                <dd>{sourceCounts}</dd>
              </div>
            )}
            {workflowCounts && (
              <div>
                <dt>{t('feedbackPage.promotion.workflowCounts')}</dt>
                <dd>{workflowCounts}</dd>
              </div>
            )}
            {expectedCitationCounts && (
              <div>
                <dt>{t('feedbackPage.promotion.expectedCitationCounts')}</dt>
                <dd>{expectedCitationCounts}</dd>
              </div>
            )}
            {langsmithCoverage && (
              <div>
                <dt>{t('feedbackPage.promotion.langsmithCoverage')}</dt>
                <dd>{langsmithCoverage}</dd>
              </div>
            )}
            {productBoundary && (
              <div>
                <dt>{t('feedbackPage.promotion.productBoundaryFlow')}</dt>
                <dd>
                  <ProductCapabilityBoundaryFlowList
                    as="ul"
                    evidence={productBoundary.evidence}
                    missingEvidence={productBoundary.missingEvidence}
                    className="fb-langsmith-handoff__provenance"
                    ariaLabel={t('feedbackPage.promotion.productBoundaryFlow')}
                    stepClassName="fb-langsmith-handoff__step"
                    fallbackEvidenceLabel={t('feedbackPage.promotion.productBoundaryFlow')}
                    statusIconOnly
                  />
                </dd>
              </div>
            )}
          </dl>
          {hasLangsmithHandoff && (
            <div
              className="fb-langsmith-handoff"
              aria-label={t('feedbackPage.promotion.langsmithSyncHandoff')}
            >
              <div className="fb-langsmith-handoff__head">
                <span>{t('feedbackPage.promotion.langsmithSyncHandoff')}</span>
                <Link className="feedback-inline-link" to={RELEASE_LANGSMITH_SYNC_PATH}>
                  <span className="fb-langsmith-handoff__step">
                    {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals}
                  </span>
                  {t('feedbackPage.promotion.openLangsmithSync')}
                </Link>
              </div>
              <dl className="fb-langsmith-handoff__grid">
                <div>
                  <dt>{t('feedbackPage.promotion.syncedCases')}</dt>
                  <dd>{syncedCases.length > 0 ? syncedCases.join(', ') : '-'}</dd>
                </div>
                <div>
                  <dt>{t('feedbackPage.promotion.unsyncedCases')}</dt>
                  <dd>{unsyncedCases.length > 0 ? unsyncedCases.join(', ') : '-'}</dd>
                </div>
                {langsmithSync?.datasetName && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithDataset')}</dt>
                    <dd>{langsmithSync.datasetName}</dd>
                  </div>
                )}
                {langsmithExamplesSummary && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithExamples')}</dt>
                    <dd>{langsmithExamplesSummary}</dd>
                  </div>
                )}
                {langsmithMetadataCaseIds && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithMetadataCases')}</dt>
                    <dd>{langsmithMetadataCaseIds}</dd>
                  </div>
                )}
                {langsmithMetadataCoverage && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithMetadataCoverage')}</dt>
                    <dd>
                      {t('feedbackPage.promotion.langsmithMetadataCoverageDesc', {
                        coverage: langsmithMetadataCoverage,
                      })}
                    </dd>
                  </div>
                )}
                {langsmithMetadataMissingSummary && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithMetadataUnsyncedCases')}</dt>
                    <dd>{langsmithMetadataMissingSummary}</dd>
                  </div>
                )}
                {langsmithSplitCounts && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithSplitCounts')}</dt>
                    <dd>{langsmithSplitCounts}</dd>
                  </div>
                )}
                {langsmithSync?.secretFree !== null && langsmithSync?.secretFree !== undefined && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithSecretScan')}</dt>
                    <dd>
                      <StatusBadge
                        status={langsmithSync.secretFree ? 'PASS' : 'WARN'}
                        label={
                          langsmithSync.secretFree
                            ? t('feedbackPage.promotion.secretFree')
                            : t('feedbackPage.promotion.secretScanMissing')
                        }
                      />
                    </dd>
                  </div>
                )}
                {langsmithSync?.sdkContract && (
                  <div>
                    <dt>{t('feedbackPage.promotion.langsmithSdkContract')}</dt>
                    <dd>{langsmithSync.sdkContract}</dd>
                  </div>
                )}
                {promotionProvenance.length > 0 && (
                  <div className="fb-langsmith-handoff__wide">
                    <dt>{t('feedbackPage.promotion.promotionProvenance')}</dt>
                    <dd>
                      {promotionProvenance.map((item, index) => {
                        const promotionCoverage = evidenceMapSummary(item.promotionCoverage)
                        const citationMarkerContract = evidenceMapSummary(item.citationMarkerContract)
                        return (
                          <dl
                            key={`${item.caseId ?? item.sourceRunId ?? 'promotion-provenance'}-${index}`}
                            className="fb-langsmith-handoff__provenance"
                          >
                            {item.caseId && (
                              <div>
                                <dt>{t('feedbackPage.promotion.caseIds')}</dt>
                                <dd>{item.caseId}</dd>
                              </div>
                            )}
                            {item.sourceRunId && (
                              <div>
                                <dt>{t('feedbackPage.promotion.sourceRun')}</dt>
                                <dd>{item.sourceRunId}</dd>
                              </div>
                            )}
                            {item.runFile && (
                              <div>
                                <dt>{t('feedbackPage.promotion.runFile')}</dt>
                                <dd>{item.runFile}</dd>
                              </div>
                            )}
                            {item.caseFile && (
                              <div>
                                <dt>{t('feedbackPage.promotion.caseFile')}</dt>
                                <dd>{item.caseFile}</dd>
                              </div>
                            )}
                            {item.diagnosticsApi && (
                              <div>
                                <dt>{t('feedbackPage.promotion.diagnosticsApi')}</dt>
                                <dd>{item.diagnosticsApi}</dd>
                              </div>
                            )}
                            {item.remediationCommand && (
                              <div>
                                <dt>{t('feedbackPage.promotion.remediationCommand')}</dt>
                                <dd>{item.remediationCommand}</dd>
                              </div>
                            )}
                            {promotionCoverage && (
                              <div>
                                <dt>{t('feedbackPage.promotion.promotionCoverage')}</dt>
                                <dd>{promotionCoverage}</dd>
                              </div>
                            )}
                            {citationMarkerContract && (
                              <div>
                                <dt>{t('feedbackPage.promotion.citationMarkerContract')}</dt>
                                <dd>{citationMarkerContract}</dd>
                              </div>
                            )}
                          </dl>
                        )
                      })}
                    </dd>
                  </div>
                )}
              </dl>
              {hasLangsmithSyncRemediation && (
                <div
                  className="fb-langsmith-handoff__remediation"
                  aria-label={t('feedbackPage.promotion.syncRemediation')}
                >
                  <div className="fb-langsmith-handoff__remediation-head">
                    <span>{t('feedbackPage.promotion.syncRemediation')}</span>
                    <StatusBadge status="WARN" label="WARN" />
                  </div>
                  <p>{t('feedbackPage.promotion.syncRemediationDesc')}</p>
                  <dl>
                    {unsyncedCases.length > 0 && (
                      <div>
                        <dt>{t('feedbackPage.promotion.syncRemediationMissingCases')}</dt>
                        <dd>{unsyncedCases.join(', ')}</dd>
                      </div>
                    )}
                    {langsmithMetadataUnsyncedCases.length > 0 && (
                      <div>
                        <dt>{t('feedbackPage.promotion.syncRemediationMissingMetadata')}</dt>
                        <dd>{langsmithMetadataUnsyncedCases.join(', ')}</dd>
                      </div>
                    )}
                  </dl>
                  <div className="fb-langsmith-handoff__command">
                    <div className="fb-langsmith-handoff__command-head">
                      <span>{t('feedbackPage.promotion.syncRemediationCommand')}</span>
                      <Link className="fb-langsmith-handoff__command-link" to={RELEASE_LANGSMITH_SYNC_PATH}>
                        <span className="fb-langsmith-handoff__step">
                          {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.evals}
                        </span>
                        {t('feedbackPage.promotion.openLangsmithSync')}
                      </Link>
                      {syncRemediationCommand && (
                        <CopyButton
                          value={syncRemediationCommand}
                          label={t('feedbackPage.promotion.syncRemediationCommand')}
                        />
                      )}
                    </div>
                    {syncRemediationCommand
                      ? <code>{syncRemediationCommand}</code>
                      : <span>{t('feedbackPage.promotion.syncRemediationCommand')}</span>}
                  </div>
                </div>
              )}
              {releaseReadinessCommand && (
                <div className="fb-langsmith-handoff__command">
                  <div className="fb-langsmith-handoff__command-head">
                    <span>{t('feedbackPage.promotion.readinessCommand')}</span>
                    <Link className="fb-langsmith-handoff__command-link" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
                      <span className="fb-langsmith-handoff__step">
                        {RELEASE_WORKFLOW_STEP_NUMBERS_BY_ID.cockpit}
                      </span>
                      {t('nav.releaseCockpit')}
                    </Link>
                    <CopyButton
                      value={releaseReadinessCommand}
                      label={t('feedbackPage.promotion.copyReadinessCommand')}
                    />
                  </div>
                  <code>{releaseReadinessCommand}</code>
                </div>
              )}
            </div>
          )}
        </details>
      )}
    </section>
  )
}
