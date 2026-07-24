import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link, useSearchParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { OperationButton, PageHeader, RefreshButton, SkeletonTable, WorkspaceUnavailable } from '../../../shared/ui'
import { formatISODate } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { queryKeys } from '../../../shared/lib/queryKeys'
import {
  buildDebugReplayInspectorHref,
  isDebugReplayCaptureReplayable,
} from '../../chat-inspector/prefill'
import { listDebugReplayCaptures, getDebugReplayCapture } from '../api'
import './debug-replay.css'

/**
 * R538: 실패 요청 캡처 목록 + 상세 보기.
 *
 * 운영자가 실패한 요청의 저장된 입력과 안전한 오류 요약을 검토한 뒤
 * 별도 응답 테스트로 넘긴다. 원시 진단 정보는 접힌 개발자 영역에만 둔다.
 * userId 는 backend 에서 SHA-256 prefix 16자로 익명화됨. TTL 7일 후 자동 삭제.
 */
export function DebugReplayManager() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('capture')

  const selectCapture = (captureId: string | null) => {
    const nextParams = new URLSearchParams(searchParams)
    if (captureId) nextParams.set('capture', captureId)
    else nextParams.delete('capture')
    setSearchParams(nextParams, { replace: true })
  }

  const {
    data: captures = [],
    isLoading,
    isFetching,
    error: listError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.debugReplay.list(),
    queryFn: () => listDebugReplayCaptures('default', 100),
  })

  const {
    data: selected,
    isLoading: isDetailLoading,
    error: detailError,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: queryKeys.debugReplay.detail(selectedId ?? ''),
    queryFn: () => (selectedId ? getDebugReplayCapture(selectedId) : Promise.resolve(null)),
    enabled: Boolean(selectedId),
  })

  const errorLabels: Record<string, string> = {
    RATE_LIMITED: t('debugReplay.errors.rateLimited'),
    CIRCUIT_BREAKER_OPEN: t('debugReplay.errors.circuitBreakerOpen'),
    UNKNOWN: t('debugReplay.errors.unknown'),
    TIMEOUT: t('debugReplay.errors.timeout'),
    MODEL_TIMEOUT: t('debugReplay.errors.modelTimeout'),
    MODEL_ERROR: t('debugReplay.errors.modelError'),
    TOOL_ERROR: t('debugReplay.errors.toolError'),
    GUARD_BLOCKED: t('debugReplay.errors.guardBlocked'),
  }
  const localizeErrorCode = (code: string | null | undefined) => {
    if (!code) return null
    return errorLabels[code] ?? t('debugReplay.errors.unclassified')
  }

  if (isLoading) {
    return (
      <div className="debug-replay-manager">
        <SkeletonTable rows={6} columns={4} />
      </div>
    )
  }

  return (
    <div className="debug-replay-manager">
      <PageHeader
        title={t('debugReplayPage.title')}
        description={t('debugReplayPage.description')}
        actions={listError ? undefined : <RefreshButton onRefresh={() => void refetch()} isFetching={isFetching} />}
      />

      {listError ? (
        <WorkspaceUnavailable
          title={t('debugReplay.unavailableTitle')}
          description={t('debugReplay.unavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={refetch}
          isRetrying={isFetching}
          secondaryAction={{ label: t('debugReplay.openHealth'), to: '/health' }}
          guide={{
            title: t('debugReplay.recoveryGuideTitle'),
            steps: [
              t('debugReplay.recoveryCheckAccount'),
              t('debugReplay.recoveryCheckStatus'),
              t('debugReplay.recoveryRetry'),
            ],
            technicalLabel: t('debugReplay.technicalError'),
            technicalDetail: getErrorMessage(listError),
          }}
        />
      ) : captures.length === 0 ? (
        <section className="debug-replay-empty" aria-labelledby="debug-replay-empty-title">
          <h2 id="debug-replay-empty-title">{t('debugReplay.empty')}</h2>
          <p>{t('debugReplay.emptyDescription')}</p>
          <Link className="btn btn-secondary" to="/chat-inspector">
            {t('debugReplay.openInspector')}
          </Link>
        </section>
      ) : (
        <div className="debug-replay-workspace">
          <section className="debug-replay-list" aria-labelledby="debug-replay-list-title">
            <header>
              <div>
                <h2 id="debug-replay-list-title">{t('debugReplay.listTitle')}</h2>
              </div>
              <p>{t('debugReplay.listCount', { count: captures.length })}</p>
            </header>
            <div className="debug-replay-list__rows">
              {captures.map((capture) => {
                const selectedRow = capture.id === selectedId
                return (
                  <button
                    key={capture.id}
                    type="button"
                    className="debug-replay-row"
                    aria-pressed={selectedRow}
                    onClick={() => selectCapture(capture.id)}
                  >
                    <span className="debug-replay-row__time">{formatISODate(capture.capturedAt)}</span>
                    <span className="debug-replay-row__body">
                      <strong>{capture.userPrompt.trim() || t('debugReplay.promptUnavailable')}</strong>
                      <span>{localizeErrorCode(capture.errorCode) ?? t('debugReplay.errors.unknown')}</span>
                    </span>
                    <ChevronRight className="debug-replay-row__chevron" aria-hidden="true" />
                  </button>
                )
              })}
            </div>
          </section>

          <section className="debug-replay-detail" aria-labelledby="debug-replay-detail-title">
            <header>
              <h2 id="debug-replay-detail-title">{t('debugReplay.reviewTitle')}</h2>
            </header>
            {!selectedId ? (
              <p className="debug-replay-detail__placeholder">{t('debugReplay.selectPrompt')}</p>
            ) : isDetailLoading ? (
              <SkeletonTable rows={3} columns={1} />
            ) : detailError ? (
              <section className="debug-replay-detail__unavailable" aria-labelledby="debug-replay-detail-unavailable-title">
                <h3 id="debug-replay-detail-unavailable-title">{t('debugReplay.detailUnavailableTitle')}</h3>
                <p>{t('debugReplay.detailUnavailable')}</p>
                <div className="detail-actions">
                  <OperationButton variant="secondary" onClick={() => void refetchDetail()}>
                    {t('common.retry')}
                  </OperationButton>
                  <OperationButton variant="ghost" onClick={() => selectCapture(null)}>
                    {t('debugReplay.chooseAnother')}
                  </OperationButton>
                </div>
                <details className="debug-replay-technical">
                  <summary>{t('debugReplay.technicalError')}</summary>
                  <p>{getErrorMessage(detailError)}</p>
                </details>
              </section>
            ) : selected ? (
              <>
                <dl className="debug-replay-detail__facts">
                  <div>
                    <dt>{t('debugReplay.failureReason')}</dt>
                    <dd>{localizeErrorCode(selected.errorCode) ?? t('debugReplay.errors.unknown')}</dd>
                  </div>
                  <div>
                    <dt>{t('debugReplay.capturedAt')}</dt>
                    <dd><time dateTime={selected.capturedAt}>{formatISODate(selected.capturedAt)}</time></dd>
                  </div>
                </dl>
                <section className="debug-replay-detail__prompt" aria-labelledby="debug-replay-detail-prompt-title">
                  <h3 id="debug-replay-detail-prompt-title">{t('debugReplay.prompt')}</h3>
                  <blockquote>{selected.userPrompt || t('debugReplay.promptUnavailable')}</blockquote>
                </section>
                <div className="debug-replay-detail__actions">
                  {isDebugReplayCaptureReplayable(selected) ? (
                    <Link className="btn btn-primary" to={buildDebugReplayInspectorHref(selected)}>
                      {t('debugReplay.openReplayTest')}
                    </Link>
                  ) : (
                    <OperationButton type="button" disabled disabledReason={t('debugReplay.replayUnavailable')}>
                      {t('debugReplay.openReplayTest')}
                    </OperationButton>
                  )}
                  <p>{isDebugReplayCaptureReplayable(selected) ? t('debugReplay.replaySafety') : t('debugReplay.replayUnavailable')}</p>
                </div>
                <details className="debug-replay-technical">
                  <summary>{t('debugReplay.technicalDetails')}</summary>
                  <dl>
                    <div><dt>{t('debugReplay.captureId')}</dt><dd><code>{selected.id}</code></dd></div>
                    <div><dt>{t('debugReplay.errorCode')}</dt><dd><code>{selected.errorCode ?? '-'}</code></dd></div>
                    <div><dt>{t('debugReplay.errorMessage')}</dt><dd><code>{selected.errorMessage ?? '-'}</code></dd></div>
                    <div><dt>{t('debugReplay.model')}</dt><dd><code>{selected.modelId ?? '-'}</code></dd></div>
                    <div><dt>{t('debugReplay.tools')}</dt><dd><code>{selected.toolsAttempted ?? '-'}</code></dd></div>
                    <div><dt>{t('debugReplay.userHash')}</dt><dd><code>{selected.userHash ?? '-'}</code></dd></div>
                    <div><dt>{t('debugReplay.expiresAt')}</dt><dd>{formatISODate(selected.expiresAt)}</dd></div>
                  </dl>
                </details>
              </>
            ) : null}
          </section>
        </div>
      )}
    </div>
  )
}
