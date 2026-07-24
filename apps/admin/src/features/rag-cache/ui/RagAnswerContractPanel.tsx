import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import {
  RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'
import type { RagPolicyState, VectorStoreStats } from '../types'

interface RagAnswerContractPanelProps {
  vectorStoreStats: VectorStoreStats | null
  ragPolicy: RagPolicyState | null
  pendingCandidatesCount: number
  onJumpToCandidates: () => void
}

export function RagAnswerContractPanel({
  vectorStoreStats,
  ragPolicy,
  pendingCandidatesCount,
  onJumpToCandidates,
}: RagAnswerContractPanelProps) {
  const { t } = useTranslation()
  const indexedDocs = vectorStoreStats?.documentCount ?? 0
  const canSearch = vectorStoreStats?.available === true && indexedDocs > 0
  const policyEnabled = ragPolicy?.effective?.enabled === true

  return (
    <section
      id={RELEASE_RAG_ANSWER_CONTRACT_ANCHOR_ID}
      className="rag-answer-contract-panel rag-answer-contract-panel--operator"
      aria-labelledby="rag-answer-contract-title"
    >
      <div className="rag-answer-contract-panel__header">
        <div>
          <h2 id="rag-answer-contract-title" className="section-title">
            {t('ragCachePage.answerContract.operatorTitle')}
          </h2>
          <p className="section-description">
            {t('ragCachePage.answerContract.operatorDescription')}
          </p>
        </div>
      </div>

      <dl className="rag-answer-contract-panel__summary">
        <div>
          <dt>{t('ragCachePage.answerContract.prepareDocuments')}</dt>
          <dd>
            <strong>{indexedDocs}</strong>
            <span>{canSearch
              ? t('ragCachePage.answerContract.checkAnswerReady')
              : t('ragCachePage.answerContract.checkAnswerBlocked')}</span>
          </dd>
        </div>
        <div>
          <dt>{t('ragCachePage.answerContract.reviewWeakAnswers')}</dt>
          <dd>
            <strong>{pendingCandidatesCount}</strong>
            <span>{t('ragCachePage.answerContract.reviewWeakAnswersDesc', {
              pending: pendingCandidatesCount,
            })}</span>
          </dd>
        </div>
      </dl>

      <div className="rag-answer-contract-panel__actions">
        <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.ingest}>
          {t('ragCachePage.answerContract.openDocuments')}
        </Link>
        <a className="btn btn-secondary btn-sm" href="#rag-answer-probe">
          {t('ragCachePage.answerContract.openAnswerTest')}
        </a>
        {pendingCandidatesCount > 0 && (
          <button
            className="btn btn-secondary btn-sm"
            type="button"
            onClick={onJumpToCandidates}
          >
            {t('ragCachePage.answerContract.openReviewQueue', { count: pendingCandidatesCount })}
          </button>
        )}
      </div>

      <details className="rag-technical-details">
        <summary>{t('ragCachePage.answerContract.technicalDetails')}</summary>
        <dl>
          <div>
            <dt>{t('ragCachePage.answerContract.technicalSearchStore')}</dt>
            <dd>{vectorStoreStats?.available ? t('ragCachePage.available') : t('ragCachePage.unavailable')}</dd>
          </div>
          <div>
            <dt>{t('ragCachePage.answerContract.technicalCollection')}</dt>
            <dd>{policyEnabled ? t('ragCachePage.policy.enabled') : t('ragCachePage.policy.disabled')}</dd>
          </div>
        </dl>
      </details>
    </section>
  )
}
