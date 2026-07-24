import { useState } from 'react'
import { CheckCircle2, ExternalLink, MessageSquareWarning, Play, TriangleAlert } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner } from '../../../shared/ui'
import {
  RELEASE_RAG_ANSWER_PROBE_ANCHOR_ID,
  RELEASE_WORKFLOW_PATHS_BY_ID,
} from '../../../shared/releaseWorkflow'
import * as ragCacheApi from '../api'
import type { RagAnswerProbeResult, RagWeakAnswerPromotionResult } from '../types'

function statusBadge(result: RagAnswerProbeResult): 'PASS' | 'WARN' | 'FAIL' {
  if (result.status === 'grounded') return 'PASS'
  if (result.status === 'weak') return 'WARN'
  return 'FAIL'
}

function normalizedCitationDocumentId(documentId: string): string {
  return documentId.trim().replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'document'
}

export function citationMatchesDocumentId(citationId: string, documentId: string): boolean {
  return citationId.startsWith(`${normalizedCitationDocumentId(documentId)}:`)
}

function operatorAnswerContent(
  content: string | null,
  citationIds: string[],
  citationMarker: (index: number | null) => string,
): string {
  if (!content) return '-'

  return content.replace(/\[([A-Za-z0-9_:-]+)\]/g, (_marker, citationId: string) => {
    const index = citationIds.indexOf(citationId)
    return `[${citationMarker(index === -1 ? null : index + 1)}]`
  })
}

export function RagGroundedAnswerProbe() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const expectedDocumentId = searchParams.get('expectedDocumentId')?.trim() || null
  const [query, setQuery] = useState(() => searchParams.get('question')?.trim() ?? '')
  const [result, setResult] = useState<RagAnswerProbeResult | null>(null)
  const [promotion, setPromotion] = useState<RagWeakAnswerPromotionResult | null>(null)
  const [running, setRunning] = useState(false)
  const [promoting, setPromoting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const expectedDocumentMatched = result && expectedDocumentId
    ? result.citationIds.some((id) => citationMatchesDocumentId(id, expectedDocumentId))
    : null
  const answerContent = result
    ? operatorAnswerContent(
      result.content,
      result.citationIds,
      (index) => index == null
        ? t('ragCachePage.answerProbe.unverifiedCitation')
        : t('ragCachePage.answerProbe.citationMarker', { index }),
    )
    : '-'

  async function handleRun() {
    if (!query.trim()) return
    setRunning(true)
    setError(null)
    setResult(null)
    setPromotion(null)
    try {
      setResult(await ragCacheApi.askGroundedRag(query))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setRunning(false)
    }
  }

  async function handlePromote() {
    if (!result) return
    setPromoting(true)
    setError(null)
    try {
      setPromotion(await (expectedDocumentId
        ? ragCacheApi.promoteWeakRagAnswer(result, { expectedDocumentId })
        : ragCacheApi.promoteWeakRagAnswer(result)))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setPromoting(false)
    }
  }

  return (
    <section
      id={RELEASE_RAG_ANSWER_PROBE_ANCHOR_ID}
      className="rag-answer-probe"
      aria-labelledby="rag-answer-probe-title"
    >
      <div className="rag-answer-probe__header">
        <div>
          <h2 id="rag-answer-probe-title" className="section-title">
            {t('ragCachePage.answerProbe.title')}
          </h2>
          <p>{t('ragCachePage.answerProbe.description')}</p>
        </div>
      </div>

      <div className="rag-answer-probe__query">
        <div className="form-group">
          <label htmlFor="rag-answer-probe-query">{t('ragCachePage.answerProbe.question')}</label>
          <textarea
            id="rag-answer-probe-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t('ragCachePage.answerProbe.placeholder')}
            rows={3}
          />
        </div>
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => { void handleRun() }}
          disabled={running || !query.trim()}
        >
          {running ? <LoadingSpinner size="sm" /> : <Play size={16} aria-hidden="true" />}
          {t('ragCachePage.answerProbe.run')}
        </button>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {result && (
        <div className="rag-answer-probe__result" aria-label={t('ragCachePage.answerProbe.result')}>
          <div className="rag-answer-probe__status">
            <span className={`rag-answer-probe__status-dot rag-answer-probe__status-dot--${statusBadge(result).toLowerCase()}`} aria-hidden="true" />
            <strong>{
              result.status === 'grounded'
                ? t('ragCachePage.answerProbe.status.grounded')
                : result.status === 'weak'
                  ? t('ragCachePage.answerProbe.status.weak')
                  : t('ragCachePage.answerProbe.status.failed')
            }</strong>
          </div>

          {expectedDocumentId && (
            <div
              className={expectedDocumentMatched
                ? 'alert alert-success'
                : 'alert alert-warning'}
              role="status"
            >
              {expectedDocumentMatched
                ? <CheckCircle2 size={17} aria-hidden="true" />
                : <TriangleAlert size={17} aria-hidden="true" />}
              <span>
                <strong>{t('ragCachePage.answerProbe.expectedDocument')}:</strong>{' '}
                {expectedDocumentMatched
                  ? t('ragCachePage.answerProbe.expectedDocumentMatched')
                  : t('ragCachePage.answerProbe.expectedDocumentMismatch')}
              </span>
            </div>
          )}

          <p className="rag-answer-probe__answer">{answerContent}</p>

          {result.sourceLabels.length > 0 && (
            <section className="rag-answer-probe__sources" aria-labelledby="rag-answer-probe-sources-title">
              <h3 id="rag-answer-probe-sources-title">{t('ragCachePage.answerProbe.sourceEvidence')}</h3>
              <ul>
                {result.sourceLabels.map((sourceLabel, index) => (
                  <li key={sourceLabel}>
                    {t('ragCachePage.answerProbe.sourceLabel', { index: index + 1 })}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {result.recoverySteps.length > 0 && (
            <div className="rag-answer-probe__recovery">
              <h3>{t('ragCachePage.answerProbe.recoverySteps')}</h3>
              <ol>
                {result.recoverySteps.map((step) => <li key={step}>{step}</li>)}
              </ol>
            </div>
          )}

          {(result.status !== 'grounded' || (
            expectedDocumentId !== null
            && expectedDocumentMatched === false
          )) && result.runId && !promotion && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => { void handlePromote() }}
              disabled={promoting}
            >
              {promoting
                ? <LoadingSpinner size="sm" />
                : <MessageSquareWarning size={16} aria-hidden="true" />}
              {t('ragCachePage.answerProbe.promote')}
            </button>
          )}

          {promotion && (
            <div className="alert alert-success" role="status">
              <span>
                {t('ragCachePage.answerProbe.promoted', {
                  feedbackId: promotion.feedbackId,
                  status: promotion.reviewStatus,
                })}
              </span>
              <Link className="btn btn-secondary btn-sm" to={RELEASE_WORKFLOW_PATHS_BY_ID.feedback}>
                {t('ragCachePage.answerProbe.openFeedback')}
                <ExternalLink size={14} aria-hidden="true" />
              </Link>
            </div>
          )}

          <details className="rag-technical-details rag-answer-probe__technical">
            <summary>{t('ragCachePage.answerProbe.technicalDetails')}</summary>
            <dl className="rag-candidate-evidence">
              <div>
                <dt>{t('ragCachePage.answerProbe.run')}</dt>
                <dd>{result.runId ?? t('ragCachePage.answerProbe.missingRunId')}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.evidenceStatus')}</dt>
                <dd>{result.evidenceStatus ?? '-'}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.citationIds')}</dt>
                <dd>{result.citationIds.join(', ') || '-'}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.sourceLabels')}</dt>
                <dd>{result.sourceLabels.join(', ') || '-'}</dd>
              </div>
              {expectedDocumentId && (
                <div>
                  <dt>{t('ragCachePage.answerProbe.expectedDocument')}</dt>
                  <dd>{expectedDocumentId}</dd>
                </div>
              )}
              <div>
                <dt>{t('ragCachePage.answerProbe.citationStyle')}</dt>
                <dd>{result.answerContract?.citationStyle ?? '-'}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.uncitedClaims')}</dt>
                <dd>
                  {result.answerContract?.uncitedClaimsAllowed == null
                    ? '-'
                    : result.answerContract.uncitedClaimsAllowed
                      ? t('ragCachePage.answerProbe.allowed')
                      : t('ragCachePage.answerProbe.blocked')}
                </dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.missingEvidence')}</dt>
                <dd>{result.missingEvidence.join(', ') || '-'}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.operatorAction')}</dt>
                <dd>{result.operatorAction ?? '-'}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.retrievedChunks')}</dt>
                <dd>{result.retrievalSummary?.chunkCount ?? 0}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.matchedCitations')}</dt>
                <dd>{result.answerExtraction?.matchedCitationCount ?? 0}/{result.citationIds.length}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.hashMismatches')}</dt>
                <dd>{result.answerExtraction?.hashMismatchCount ?? 0}</dd>
              </div>
              <div>
                <dt>{t('ragCachePage.answerProbe.missingChunks')}</dt>
                <dd>{result.answerExtraction?.missingChunkCount ?? 0}</dd>
              </div>
            </dl>
            {result.citationIds.length > 0 && (
              <div className="rag-answer-probe__citations">
                <h3>{t('ragCachePage.answerProbe.citationEvidence')}</h3>
                <ul>
                  {result.citationIds.map((citationId) => (
                    <li key={citationId}>
                      <code>{citationId}</code>
                      {expectedDocumentId && citationMatchesDocumentId(citationId, expectedDocumentId) && (
                        <span>{t('ragCachePage.answerProbe.expectedDocumentMatched')}</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </details>
        </div>
      )}
    </section>
  )
}
