import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { ChevronRight, X } from 'lucide-react'
import { CopyButton, LoadingSpinner, ReleaseReportList, ReleaseReportMap } from '../../../shared/ui'
import { formatISODate } from '../../../shared/lib/formatters'
import {
  resolveReleaseActionRunbookItems,
  type ReleaseActionRunbookLabels,
} from '../../../shared/lib/releaseNextActionCommand'
import type { FeedbackEntry } from '../types'
import { FeedbackReviewPanel } from './FeedbackReviewPanel'
import { FeedbackEvalPromotionAction } from './FeedbackEvalPromotionAction'
import { useLabelLocalizers } from './feedbackLabels'
import { feedbackCanClose } from '../feedbackEvalLifecycle'

export interface FeedbackDetailDrawerProps {
  isLoading: boolean
  selected: FeedbackEntry | null
  onClose: () => void
  onDelete: (entry: FeedbackEntry) => void
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

function hasReleaseActionEvidence(action: NonNullable<FeedbackEntry['nextActions']>[number]): boolean {
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
    || formatList(action.requiredReadinessReports)
    || Object.keys(action.readinessReports ?? {}).length > 0
    || formatNestedEnv(action.requiredEnvAnyOf)
    || formatList(action.missingEnvAnyOf)
    || formatList(action.recommendedEnv)
    || formatList(action.minorBoundaryReports)
    || formatList(action.dependsOnActionIds)
  )
}

function resolveFeedbackActionState(feedback: FeedbackEntry, actionId: string): string | null {
  const explicit = feedback.nextActionStates?.[actionId]?.trim()
  if (explicit) return explicit
  if (feedback.readyNextActionIds?.includes(actionId)) return 'ready'
  if (feedback.blockedNextActionIds?.includes(actionId)) return 'blocked'
  return null
}

function feedbackActionStateClassName(state: string): string {
  const normalized = state.trim().toLowerCase()
  if (normalized === 'ready' || normalized === 'passed') return 'fb-release-action__state--ready'
  if (normalized === 'blocked' || normalized === 'failed') return 'fb-release-action__state--blocked'
  return 'fb-release-action__state--pending'
}

function feedbackActionStateLabel(state: string, t: TFunction): string {
  const normalized = state.trim().toLowerCase()
  if (normalized === 'ready') return t('feedbackPage.actionStateLabels.ready')
  if (normalized === 'passed') return t('feedbackPage.actionStateLabels.passed')
  if (normalized === 'blocked') return t('feedbackPage.actionStateLabels.blocked')
  if (normalized === 'failed') return t('feedbackPage.actionStateLabels.failed')
  return t('feedbackPage.actionStateLabels.pending')
}

export function FeedbackDetailDrawer({
  isLoading,
  selected,
  onClose,
  onDelete,
}: FeedbackDetailDrawerProps) {
  const { t } = useTranslation()
  const { localizeRating, localizeStatus } = useLabelLocalizers()

  if (isLoading) {
    return (
      <div className="detail-panel detail-panel--compact"><LoadingSpinner /></div>
    )
  }

  if (!selected) return null
  const releaseActions = (selected.nextActions ?? []).filter(hasReleaseActionEvidence)

  return (
    <div className="detail-panel detail-panel--compact">
      <div className="detail-panel-header">
        <div className="detail-header">
          <h2>{t('feedbackPage.selectedTitle')}</h2>
          <CopyButton value={selected.feedbackId} label={t('feedbackPage.feedbackId')} />
          <span className={`feedback-table__state ${selected.rating === 'thumbs_up' ? 'is-success' : 'is-error'}`}>
            <span aria-hidden="true" />
            {localizeRating(selected.rating)}
          </span>
          <span className={`feedback-table__state ${selected.reviewStatus === 'done' ? 'is-success' : 'is-warning'}`}>
            <span aria-hidden="true" />
            {localizeStatus(selected.reviewStatus)}
          </span>
        </div>
        <button
          className="detail-close-btn"
          onClick={onClose}
          aria-label={t('common.close')}
        ><X aria-hidden="true" size={16} strokeWidth={1.8} /></button>
      </div>

      <div className="detail-meta">
        <span title={selected.runId ?? undefined}>{t('feedbackPage.run')}: {selected.runId ? t('feedbackPage.runAvailable') : '-'}</span>
        <span>{t('feedbackPage.columns.created')}: {formatISODate(selected.timestamp)}</span>
      </div>

      <div className="detail-section">
        <h3>{t('feedbackPage.query')}</h3>
        <div className="feedback-detail__content">{selected.query || '-'}</div>
      </div>

      <div className="detail-section">
        <h3>{t('feedbackPage.response')}</h3>
        <div className="feedback-detail__content">{selected.response || '-'}</div>
      </div>

      {selected.comment && (
        <div className="detail-section">
          <h3>{t('feedbackPage.comment')}</h3>
          <div className="feedback-detail__content">{selected.comment}</div>
        </div>
      )}

      {releaseActions.length > 0 && (
        <div className="detail-section">
          <h3>{t('feedbackPage.releaseHandoff')}</h3>
          <div className="fb-release-actions" role="list">
            {releaseActions.map((action) => {
              const runbookItems = resolveReleaseActionRunbookItems(action, {
                command: t('feedbackPage.runbookCommand'),
                remediation: t('feedbackPage.runbookRemediation'),
                env: t('feedbackPage.runbookEnv'),
                readiness: t('feedbackPage.runbookReadiness'),
              } satisfies ReleaseActionRunbookLabels)
              return (
              <div key={action.id} className="fb-release-action" role="listitem">
                <div className="fb-release-action__head">
                  <span className="fb-release-action__id">{action.label}</span>
                  {resolveFeedbackActionState(selected, action.id) && (
                    <span
                      className={`fb-release-action__state ${feedbackActionStateClassName(
                        resolveFeedbackActionState(selected, action.id) ?? '',
                      )}`}
                    >
                      {feedbackActionStateLabel(resolveFeedbackActionState(selected, action.id) ?? '', t)}
                    </span>
                  )}
                </div>
                <details className="feedback-technical-details">
                  <summary>
                    <ChevronRight className="feedback-technical-details__chevron" aria-hidden="true" size={15} strokeWidth={1.8} />
                    {t('feedbackPage.technicalDetails')}
                  </summary>
                {runbookItems.length > 0 && (
                  <div
                    className="fb-release-action__runbook"
                    aria-label={t('feedbackPage.runbook')}
                  >
                    {runbookItems.map((item) => (
                      <div key={`${action.id}-${item.key}`} className="fb-release-action__runbook-item">
                        <div className="fb-release-action__runbook-head">
                          <span>{item.label}</span>
                          <CopyButton value={item.value} label={item.label} />
                        </div>
                        <code>{item.value}</code>
                      </div>
                    ))}
                  </div>
                )}
                <dl className="fb-release-action__meta">
                  <div>
                    <dt>{t('feedbackPage.actionId')}</dt>
                    <dd>{action.id}</dd>
                  </div>
                  {action.evalCaseId && (
                    <div>
                      <dt>{t('feedbackPage.promotion.caseIds')}</dt>
                      <dd>{action.evalCaseId}</dd>
                    </div>
                  )}
                  {action.feedbackId && (
                    <div>
                      <dt>{t('feedbackPage.feedbackId')}</dt>
                      <dd>{action.feedbackId}</dd>
                    </div>
                  )}
                  {action.sourceRunId && (
                    <div>
                      <dt>{t('feedbackPage.sourceRun')}</dt>
                      <dd>{action.sourceRunId}</dd>
                    </div>
                  )}
                  {action.candidateTag && (
                    <div>
                      <dt>{t('feedbackPage.candidateTag')}</dt>
                      <dd>{action.candidateTag}</dd>
                    </div>
                  )}
                  {action.subjectUserId && (
                    <div>
                      <dt>{t('feedbackPage.subjectUserId')}</dt>
                      <dd>{action.subjectUserId}</dd>
                    </div>
                  )}
                  {action.datasetName && (
                    <div>
                      <dt>{t('feedbackPage.dataset')}</dt>
                      <dd>{action.datasetName}</dd>
                    </div>
                  )}
                  {action.feedbackSource && (
                    <div>
                      <dt>{t('feedbackPage.feedbackSource')}</dt>
                      <dd>{action.feedbackSource}</dd>
                    </div>
                  )}
                  {formatList(action.feedbackTags) && (
                    <div>
                      <dt>{t('feedbackPage.feedbackTags')}</dt>
                      <dd>{formatList(action.feedbackTags)}</dd>
                    </div>
                  )}
                  {action.preflightFile && (
                    <div>
                      <dt>{t('feedbackPage.preflightFile')}</dt>
                      <dd>{action.preflightFile}</dd>
                    </div>
                  )}
                  {action.preflightEnvTemplate && (
                    <div>
                      <dt>{t('feedbackPage.preflightEnvTemplate')}</dt>
                      <dd>{action.preflightEnvTemplate}</dd>
                    </div>
                  )}
                  {action.replatformReadinessFile && (
                    <div>
                      <dt>{t('feedbackPage.replatformReadinessFile')}</dt>
                      <dd>{action.replatformReadinessFile}</dd>
                    </div>
                  )}
                  {action.smokePlanFile && (
                    <div>
                      <dt>{t('feedbackPage.smokePlanFile')}</dt>
                      <dd>{action.smokePlanFile}</dd>
                    </div>
                  )}
                  {action.releaseEvidenceFile && (
                    <div>
                      <dt>{t('feedbackPage.releaseEvidenceFile')}</dt>
                      <dd>{action.releaseEvidenceFile}</dd>
                    </div>
                  )}
                  {action.releaseReadinessFile && (
                    <div>
                      <dt>{t('feedbackPage.readinessFile')}</dt>
                      <dd>{action.releaseReadinessFile}</dd>
                    </div>
                  )}
                  {action.reportFile && (
                    <div>
                      <dt>{t('feedbackPage.reportFile')}</dt>
                      <dd>{action.reportFile}</dd>
                    </div>
                  )}
                  {action.caseFile && (
                    <div>
                      <dt>{t('feedbackPage.caseFile')}</dt>
                      <dd>{action.caseFile}</dd>
                    </div>
                  )}
                  {action.runFile && (
                    <div>
                      <dt>{t('feedbackPage.runFile')}</dt>
                      <dd>{action.runFile}</dd>
                    </div>
                  )}
                  {action.diagnosticsApi && (
                    <div>
                      <dt>{t('feedbackPage.diagnosticsApi')}</dt>
                      <dd>{action.diagnosticsApi}</dd>
                    </div>
                  )}
                  {action.suiteFile && (
                    <div>
                      <dt>{t('feedbackPage.suiteFile')}</dt>
                      <dd>{action.suiteFile}</dd>
                    </div>
                  )}
                  {action.readinessReportArg && (
                    <div>
                      <dt>{t('feedbackPage.readinessReportArg')}</dt>
                      <dd>{action.readinessReportArg}</dd>
                    </div>
                  )}
                  {formatList(action.requiredReadinessReports) && (
                    <div>
                      <dt>{t('feedbackPage.requiredReadinessReports')}</dt>
                      <dd>
                        <ReleaseReportList
                          reports={action.requiredReadinessReports}
                          includeStep
                          stepClassName="fb-release-action__step"
                        />
                      </dd>
                    </div>
                  )}
                  {action.readinessReports && Object.keys(action.readinessReports).length > 0 && (
                    <div>
                      <dt>{t('feedbackPage.readinessReports')}</dt>
                      <dd>
                        <ReleaseReportMap
                          reports={action.readinessReports}
                          includeStep
                          stepClassName="fb-release-action__step"
                        />
                      </dd>
                    </div>
                  )}
                  {formatNestedEnv(action.requiredEnvAnyOf) && (
                    <div>
                      <dt>{t('feedbackPage.requiredEnvAnyOf')}</dt>
                      <dd>{formatNestedEnv(action.requiredEnvAnyOf)}</dd>
                    </div>
                  )}
                  {formatList(action.missingEnvAnyOf) && (
                    <div>
                      <dt>{t('feedbackPage.missingEnvAnyOf')}</dt>
                      <dd>{formatList(action.missingEnvAnyOf)}</dd>
                    </div>
                  )}
                  {formatList(action.recommendedEnv) && (
                    <div>
                      <dt>{t('feedbackPage.recommendedEnv')}</dt>
                      <dd>{formatList(action.recommendedEnv)}</dd>
                    </div>
                  )}
                  {action.recommendedVersionBump && (
                    <div>
                      <dt>{t('feedbackPage.versionBump')}</dt>
                      <dd>{action.recommendedVersionBump}</dd>
                    </div>
                  )}
                  {action.recommendedTagPattern && (
                    <div>
                      <dt>{t('feedbackPage.tagPattern')}</dt>
                      <dd>{action.recommendedTagPattern}</dd>
                    </div>
                  )}
                  {action.latestTagCommand && (
                    <div>
                      <dt>{t('feedbackPage.latestTagCommand')}</dt>
                      <dd>{action.latestTagCommand}</dd>
                    </div>
                  )}
                  {action.recommendedTagSource && (
                    <div>
                      <dt>{t('feedbackPage.recommendedTagSource')}</dt>
                      <dd>{action.recommendedTagSource}</dd>
                    </div>
                  )}
                  {formatList(action.minorBoundaryReports) && (
                    <div>
                      <dt>{t('feedbackPage.minorBoundaryReports')}</dt>
                      <dd>
                        <ReleaseReportList
                          reports={action.minorBoundaryReports}
                          includeStep
                          stepClassName="fb-release-action__step"
                        />
                      </dd>
                    </div>
                  )}
                  {formatList(action.dependsOnActionIds) && (
                    <div>
                      <dt>{t('feedbackPage.dependsOnActionIds')}</dt>
                      <dd>{formatList(action.dependsOnActionIds)}</dd>
                    </div>
                  )}
                </dl>
                </details>
              </div>
              )
            })}
          </div>
        </div>
      )}

      <details className="feedback-technical-details">
        <summary>
          <ChevronRight className="feedback-technical-details__chevron" aria-hidden="true" size={15} strokeWidth={1.8} />
          {t('feedbackPage.metadata')}
        </summary>
        <pre className="code-block">
          {JSON.stringify(
            {
              intent: selected.intent,
              domain: selected.domain,
              model: selected.model,
              promptVersion: selected.promptVersion,
              durationMs: selected.durationMs,
              templateId: selected.templateId,
              toolsUsed: selected.toolsUsed,
              tags: selected.tags,
            },
            null,
            2,
          )}
        </pre>
      </details>

      <FeedbackReviewPanel
        key={`${selected.feedbackId}-${selected.version}`}
        feedback={selected}
      />

      <FeedbackEvalPromotionAction
        key={`eval-promotion-${selected.feedbackId}-${selected.version}`}
        feedback={selected}
      />

      <div className="detail-actions">
        <button
          className="btn btn-danger btn-sm"
          onClick={() => onDelete(selected)}
          disabled={!feedbackCanClose(selected)}
          title={!feedbackCanClose(selected) ? t('feedbackPage.evalLifecycle.deleteBlocked') : undefined}
        >
          {t('common.delete')}
        </button>
      </div>
    </div>
  )
}
