import { useTranslation } from 'react-i18next'
import { CopyButton, OperationButton, SideDrawer } from '../../../shared/ui'
import {
  resolveReleaseActionRunbookItems,
  type ReleaseActionRunbookLabels,
} from '../../../shared/lib/releaseNextActionCommand'
import { formatDate, localizeReviewStatus } from './ragCandidatesUtils'
import { hasRagReleaseActionEvidence } from './ragReleaseHandoff'
import type { RagCandidate, RagCandidateNextAction } from '../types'

interface RagCandidateDetailDrawerProps {
  candidate: RagCandidate | null
  onClose: () => void
  onRequestApprove: () => void
  onRequestReject: () => void
  approvePending: boolean
  rejectPending: boolean
}

type ActionReviewState = 'ready' | 'blocked' | 'pending'

interface TechnicalRow {
  label: string
  value: string
}

function formatList(values: string[] | null | undefined): string {
  return values?.filter(Boolean).join(', ') ?? ''
}

function formatNestedEnv(values: string[][] | null | undefined): string {
  return values
    ?.filter((group) => group.length > 0)
    .map((group) => group.join(' or '))
    .join('; ') ?? ''
}

function formatEvidenceValue(value: boolean | number | string | string[] | null): string {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  return value ?? ''
}

function formatEvidenceMap(values: Record<string, boolean | number | string | string[] | null> | null | undefined): string {
  return Object.entries(values ?? {})
    .map(([key, value]) => `${key}: ${formatEvidenceValue(value)}`)
    .filter((value) => !value.endsWith(': '))
    .join(', ')
}

function resolveActionReviewState(candidate: RagCandidate, actionId: string): ActionReviewState {
  const explicit = candidate.nextActionStates?.[actionId]?.trim().toLowerCase()
  if (explicit === 'ready' || explicit === 'passed') return 'ready'
  if (explicit === 'blocked' || explicit === 'failed') return 'blocked'
  if (candidate.readyNextActionIds?.includes(actionId)) return 'ready'
  if (candidate.blockedNextActionIds?.includes(actionId)) return 'blocked'
  return 'pending'
}

function actionPurposeKey(action: RagCandidateNextAction): string {
  if (action.evalCaseId || action.datasetName || action.caseFile) return 'sync'
  if (action.releaseReadinessCommand || action.releaseReadinessFile) return 'readiness'
  return 'review'
}

function optionalRow(label: string, value: string | null | undefined): TechnicalRow[] {
  return value?.trim() ? [{ label, value }] : []
}

function actionTechnicalRows(
  action: RagCandidateNextAction,
  t: (key: string) => string,
): TechnicalRow[] {
  const readinessReports = action.readinessReports
    ? Object.entries(action.readinessReports)
      .map(([report, path]) => `${report}: ${path}`)
      .join(', ')
    : ''

  return [
    { label: t('ragCachePage.candidates.actionId'), value: action.id },
    ...optionalRow(t('ragCachePage.candidates.actionLabel'), action.label),
    ...optionalRow(t('ragCachePage.candidates.sourceRun'), action.sourceRunId),
    ...optionalRow(t('ragCachePage.candidates.candidateTag'), action.candidateTag),
    ...optionalRow(t('ragCachePage.candidates.workflowTags'), formatList(action.workflowTags)),
    ...optionalRow(t('ragCachePage.candidates.dataset'), action.datasetName),
    ...optionalRow(t('ragCachePage.candidates.evalCase'), action.evalCaseId),
    ...optionalRow(t('ragCachePage.candidates.feedbackRating'), action.feedbackRating),
    ...optionalRow(t('ragCachePage.candidates.feedbackSource'), action.feedbackSource),
    ...optionalRow(t('ragCachePage.candidates.feedbackTags'), formatList(action.feedbackTags)),
    ...optionalRow(t('ragCachePage.candidates.preflightFile'), action.preflightFile),
    ...optionalRow(t('ragCachePage.candidates.preflightEnvTemplate'), action.preflightEnvTemplate),
    ...optionalRow(t('ragCachePage.candidates.replatformReadinessFile'), action.replatformReadinessFile),
    ...optionalRow(t('ragCachePage.candidates.smokePlanFile'), action.smokePlanFile),
    ...optionalRow(t('ragCachePage.candidates.releaseEvidenceFile'), action.releaseEvidenceFile),
    ...optionalRow(t('ragCachePage.candidates.caseFile'), action.caseFile),
    ...optionalRow(t('ragCachePage.candidates.runFile'), action.runFile),
    ...optionalRow(t('ragCachePage.candidates.reportFile'), action.reportFile),
    ...optionalRow(t('ragCachePage.candidates.diagnosticsApi'), action.diagnosticsApi),
    ...optionalRow(t('ragCachePage.candidates.readinessFile'), action.releaseReadinessFile),
    ...optionalRow(t('ragCachePage.candidates.suiteFile'), action.suiteFile),
    ...optionalRow(t('ragCachePage.candidates.readinessReportArg'), action.readinessReportArg),
    ...optionalRow(
      t('ragCachePage.candidates.requiredReadinessReports'),
      formatList(action.requiredReadinessReports),
    ),
    ...optionalRow(t('ragCachePage.candidates.readinessReports'), readinessReports),
    ...optionalRow(
      t('ragCachePage.candidates.requiredEnvAnyOf'),
      formatNestedEnv(action.requiredEnvAnyOf),
    ),
    ...optionalRow(t('ragCachePage.candidates.missingEnvAnyOf'), formatList(action.missingEnvAnyOf)),
    ...optionalRow(t('ragCachePage.candidates.recommendedEnv'), formatList(action.recommendedEnv)),
    ...optionalRow(t('ragCachePage.candidates.versionBump'), action.recommendedVersionBump),
    ...optionalRow(t('ragCachePage.candidates.tagPattern'), action.recommendedTagPattern),
    ...optionalRow(t('ragCachePage.candidates.latestTagCommand'), action.latestTagCommand),
    ...optionalRow(t('ragCachePage.candidates.recommendedTagSource'), action.recommendedTagSource),
    ...optionalRow(t('ragCachePage.candidates.minorBoundaryReports'), formatList(action.minorBoundaryReports)),
    ...optionalRow(t('ragCachePage.candidates.dependsOnActionIds'), formatList(action.dependsOnActionIds)),
    ...optionalRow(t('ragCachePage.candidates.promotionCoverage'), formatEvidenceMap(action.promotionCoverage)),
    ...optionalRow(
      t('ragCachePage.candidates.citationMarkerContract'),
      formatEvidenceMap(action.citationMarkerContract),
    ),
  ]
}

export function RagCandidateDetailDrawer({
  candidate,
  onClose,
  onRequestApprove,
  onRequestReject,
  approvePending,
  rejectPending,
}: RagCandidateDetailDrawerProps) {
  const { t } = useTranslation()
  const busy = approvePending || rejectPending
  const releaseActions = (candidate?.nextActions ?? []).filter(hasRagReleaseActionEvidence)

  return (
    <SideDrawer
      open={candidate !== null}
      title={t('ragCachePage.candidates.title')}
      onClose={onClose}
    >
      {candidate && (
        <div className="candidate-review-drawer">
          <header className="candidate-review-drawer__header">
            <div className="candidate-review-drawer__status-line">
              <span
                className={`candidate-review-drawer__status-dot candidate-review-drawer__status-dot--${candidate.status.toLowerCase()}`}
                aria-hidden="true"
              />
              <strong>{localizeReviewStatus(candidate.status, t)}</strong>
              <span>{candidate.channel || '-'}</span>
              <span>{formatDate(candidate.capturedAt)}</span>
            </div>
            <p>{t('ragCachePage.candidates.detailDescription')}</p>
          </header>

          <section className="candidate-review-drawer__content" aria-labelledby="candidate-review-question">
            <h3 id="candidate-review-question">{t('ragCachePage.candidates.query')}</h3>
            <p>{candidate.query}</p>
          </section>

          <section className="candidate-review-drawer__content" aria-labelledby="candidate-review-response">
            <h3 id="candidate-review-response">{t('ragCachePage.candidates.response')}</h3>
            <p>{candidate.response}</p>
          </section>

          {releaseActions.length > 0 && (
            <section className="candidate-review-drawer__checks" aria-labelledby="candidate-review-checks">
              <h3 id="candidate-review-checks">{t('ragCachePage.candidates.nextChecks')}</h3>
              <p>{t('ragCachePage.candidates.nextChecksDescription')}</p>
              <ul>
                {releaseActions.map((action) => {
                  const state = resolveActionReviewState(candidate, action.id)
                  return (
                    <li key={action.id}>
                      <strong>{t(`ragCachePage.candidates.actionKind.${actionPurposeKey(action)}`)}</strong>
                      <span className={`candidate-review-drawer__action-state candidate-review-drawer__action-state--${state}`}>
                        <span aria-hidden="true" />
                        {t(`ragCachePage.candidates.actionState.${state}`)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            </section>
          )}

          <details className="rag-technical-details candidate-review-drawer__technical">
            <summary>{t('ragCachePage.candidates.technicalDetails')}</summary>
            <dl>
              <div>
                <dt>{t('ragCachePage.candidates.candidateId')}</dt>
                <dd>{candidate.id}</dd>
              </div>
              {candidate.runId && (
                <div>
                  <dt>{t('ragCachePage.candidates.sourceRun')}</dt>
                  <dd>{candidate.runId}</dd>
                </div>
              )}
              {candidate.ingestedDocumentId && (
                <div>
                  <dt>{t('ragCachePage.candidates.ingestedDocument')}</dt>
                  <dd>{candidate.ingestedDocumentId}</dd>
                </div>
              )}
            </dl>

            {releaseActions.map((action, index) => {
              const runbookItems = resolveReleaseActionRunbookItems(action, {
                command: t('ragCachePage.candidates.runbookCommand'),
                remediation: t('ragCachePage.candidates.runbookRemediation'),
                env: t('ragCachePage.candidates.runbookEnv'),
                readiness: t('ragCachePage.candidates.runbookReadiness'),
              } satisfies ReleaseActionRunbookLabels)
              const rows = actionTechnicalRows(action, t)

              return (
                <section key={action.id} className="candidate-review-drawer__technical-action">
                  <h3>{t('ragCachePage.candidates.technicalAction', { index: index + 1 })}</h3>
                  <dl>
                    {rows.map((row) => (
                      <div key={`${action.id}-${row.label}`}>
                        <dt>{row.label}</dt>
                        <dd>{row.value}</dd>
                      </div>
                    ))}
                  </dl>
                  {runbookItems.length > 0 && (
                    <section aria-label={t('ragCachePage.candidates.runbook')}>
                      <h4>{t('ragCachePage.candidates.runbook')}</h4>
                      <ul className="candidate-review-drawer__runbook">
                        {runbookItems.map((item) => (
                          <li key={`${action.id}-${item.key}`}>
                            <span>{item.label}</span>
                            <CopyButton value={item.value} label={item.label} />
                            <code>{item.value}</code>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                </section>
              )
            })}
          </details>

          {candidate.status === 'PENDING' && (
            <div className="modal-actions candidate-review-drawer__actions">
              <OperationButton
                variant="danger"
                onClick={onRequestReject}
                isOperating={rejectPending}
                disabled={busy && !rejectPending}
              >
                {t('ragCachePage.candidates.reject')}
              </OperationButton>
              <OperationButton
                variant="primary"
                onClick={onRequestApprove}
                isOperating={approvePending}
                disabled={busy && !approvePending}
              >
                {t('ragCachePage.candidates.approve')}
              </OperationButton>
            </div>
          )}
        </div>
      )}
    </SideDrawer>
  )
}
