import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CloudUpload, FlaskConical, ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { OperationButton, StatusBadge } from '../../../shared/ui'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { useToastStore } from '../../../shared/store/toast.store'
import {
  RELEASE_LANGSMITH_SYNC_PATH,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'
import * as feedbackApi from '../api'
import type {
  FeedbackEntry,
  FeedbackEvalPromotionResult,
  FeedbackLangSmithClosureResult,
} from '../types'

interface Props {
  feedback: FeedbackEntry
}

export function FeedbackEvalPromotionAction({ feedback }: Props) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const addToast = useToastStore((state) => state.addToast)
  const [result, setResult] = useState<FeedbackEvalPromotionResult | null>(null)
  const [syncResult, setSyncResult] = useState<FeedbackLangSmithClosureResult | null>(null)
  const action = feedback.nextActions?.find((candidate) => candidate.id === 'promote-eval')
  const blocked = feedback.blockedNextActionIds?.includes('promote-eval') ?? false
  const promoted = feedback.reviewTags.includes('promoted') || result !== null
  const synced = feedback.reviewTags.includes('langsmith') || syncResult !== null

  const mutation = useMutation({
    mutationFn: () => feedbackApi.promoteFeedbackToEval(feedback),
    onSuccess: (promotion) => {
      setResult(promotion)
      void queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })
      addToast({
        type: 'success',
        message: t('feedbackPage.evalPromotion.saved', { caseId: promotion.evalCase.id }),
      })
    },
    onError: (error) => addToast({ type: 'error', message: getErrorMessage(error) }),
  })

  const syncMutation = useMutation({
    mutationFn: () => {
      const activeFeedback = result?.feedback ?? feedback
      const activeCaseId = result?.evalCase.id ?? action?.evalCaseId
      if (!activeCaseId) throw new Error('LangSmith sync requires evalCaseId')
      return feedbackApi.syncFeedbackEvalToLangSmith(
        activeFeedback,
        activeCaseId,
        action?.datasetName ?? 'reactor-admin-regression',
      )
    },
    onSuccess: (closure) => {
      setSyncResult(closure)
      void queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })
      addToast({
        type: 'success',
        message: t('feedbackPage.evalPromotion.synced', {
          datasetName: closure.sync.datasetName,
        }),
      })
    },
    onError: (error) => addToast({ type: 'error', message: getErrorMessage(error) }),
  })

  if (!action || feedback.rating !== 'thumbs_down') return null
  const caseId = result?.evalCase.id ?? action.evalCaseId
  const sourceRunId = result?.evalCase.sourceRunId ?? action.sourceRunId ?? feedback.runId

  return (
    <section className="fb-eval-promotion" aria-labelledby="feedback-eval-promotion-title">
      <div className="fb-eval-promotion__head">
        <div>
          <h3 id="feedback-eval-promotion-title">{t('feedbackPage.evalPromotion.title')}</h3>
          <p>{t('feedbackPage.evalPromotion.description')}</p>
        </div>
        <StatusBadge
          status={synced ? 'PASS' : promoted ? 'WARN' : blocked ? 'FAIL' : 'WARN'}
          label={
            synced
              ? t('feedbackPage.evalPromotion.syncCompleted')
              : promoted
              ? t('feedbackPage.evalPromotion.promoted')
              : blocked
                ? t('feedbackPage.evalPromotion.blocked')
                : t('feedbackPage.evalPromotion.ready')
          }
        />
      </div>

      {promoted ? (
        <div className={`alert ${synced ? 'alert-success' : 'alert-warning'}`} role="status">
          <span>
            {synced
              ? t('feedbackPage.evalPromotion.syncEvidence', {
                  datasetName: syncResult?.sync.datasetName ?? action.datasetName ?? '-',
                  examples: syncResult?.sync.examples ?? 1,
                })
              : t('feedbackPage.evalPromotion.pendingLangSmith')}
          </span>
          {synced ? (
            <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.cockpit}>
              {t('feedbackPage.evalPromotion.openReadiness')}
              <ExternalLink size={14} aria-hidden="true" />
            </Link>
          ) : (
            <>
              <OperationButton
                variant="primary"
                className="btn-sm"
                onClick={() => syncMutation.mutate()}
                isOperating={syncMutation.isPending}
              >
                <CloudUpload size={16} aria-hidden="true" />
                {t('feedbackPage.evalPromotion.syncAction')}
              </OperationButton>
              <Link className="btn btn-secondary btn-sm" to={RELEASE_LANGSMITH_SYNC_PATH}>
                {t('feedbackPage.evalPromotion.openLangSmith')}
                <ExternalLink size={14} aria-hidden="true" />
              </Link>
            </>
          )}
        </div>
      ) : (
        <OperationButton
          variant="primary"
          onClick={() => mutation.mutate()}
          disabled={blocked || !caseId || !sourceRunId}
          isOperating={mutation.isPending}
        >
          <FlaskConical size={16} aria-hidden="true" />
          {t('feedbackPage.evalPromotion.action')}
        </OperationButton>
      )}

      <details className="feedback-technical-details">
        <summary>{t('feedbackPage.technicalDetails')}</summary>
        <dl className="fb-eval-promotion__provenance">
          <div>
            <dt>{t('feedbackPage.evalPromotion.caseId')}</dt>
            <dd>{caseId ?? '-'}</dd>
          </div>
          <div>
            <dt>{t('feedbackPage.evalPromotion.sourceRun')}</dt>
            <dd>{sourceRunId ?? '-'}</dd>
          </div>
        </dl>
      </details>
    </section>
  )
}
