import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  DataTable,
  EmptyState,
  LoadingSpinner,
  SideDrawer,
  TableSkeleton,
  Tooltip,
} from '../../../shared/ui'
import type { Column } from '../../../shared/ui'
import { formatDateTime } from '../../../shared/lib/formatters'
import type { IngestionCandidate } from '../types'
import './document-ingestion.css'

const CANDIDATE_API_LIMIT = 500
const PAGE_SIZE = 30
const KNOWN_CHANNEL_LABEL_KEYS: Record<string, string> = {
  slack: 'documentsPage.ingestion.channelLabels.slack',
  web: 'documentsPage.ingestion.channelLabels.web',
  api: 'documentsPage.ingestion.channelLabels.api',
  a2a: 'documentsPage.ingestion.channelLabels.a2a',
}

interface DocumentIngestionTabProps {
  candidates: IngestionCandidate[]
  loadingCandidates: boolean
  onFilter: (status: string, channel: string) => void
  onApprove: (candidate: IngestionCandidate, comment?: string) => void
  onReject: (candidate: IngestionCandidate, comment?: string) => void
  reviewingId: string | null
  onRefresh: () => void
}

export function DocumentIngestionTab({
  candidates,
  loadingCandidates,
  onFilter,
  onApprove,
  onReject,
  reviewingId,
  onRefresh,
}: DocumentIngestionTabProps) {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const [page, setPage] = useState(1)
  const [candidateStatus, setCandidateStatus] = useState('')
  const [candidateChannel, setCandidateChannel] = useState('')
  const [reviewComment, setReviewComment] = useState('')

  const selectedId = searchParams.get('candidate')
  const selectedCandidate = candidates.find(candidate => candidate.id === selectedId) ?? null
  const pendingCount = candidates.filter(candidate => candidate.status === 'PENDING').length
  const ingestedCount = candidates.filter(candidate => candidate.status === 'INGESTED').length
  const rejectedCount = candidates.filter(candidate => candidate.status === 'REJECTED').length

  function selectCandidate(candidate: IngestionCandidate | null) {
    setSearchParams(current => {
      const next = new URLSearchParams(current)
      if (candidate) next.set('candidate', candidate.id)
      else next.delete('candidate')
      return next
    })
    setReviewComment('')
  }

  function statusLabel(status: IngestionCandidate['status']): string {
    if (status === 'PENDING') return t('documentsPage.ingestion.status.pending')
    if (status === 'INGESTED') return t('documentsPage.ingestion.status.ingested')
    return t('documentsPage.ingestion.status.rejected')
  }

  function channelLabel(channel: string | null | undefined): string {
    if (!channel) return t('documentsPage.ingestion.channelUnknown')

    const key = KNOWN_CHANNEL_LABEL_KEYS[channel.trim().toLowerCase()]
    return key ? t(key) : channel
  }

  function handleApprove() {
    if (!selectedCandidate) return
    onApprove(selectedCandidate, reviewComment.trim() || undefined)
    setReviewComment('')
  }

  function handleReject() {
    if (!selectedCandidate) return
    onReject(selectedCandidate, reviewComment.trim() || undefined)
    setReviewComment('')
  }

  const candidateColumns: Column<IngestionCandidate>[] = [
    {
      key: 'status',
      header: t('common.status'),
      width: '18%',
      responsivePriority: 1,
      render: row => (
        <span className={`document-ingestion-status document-ingestion-status--${row.status.toLowerCase()}`}>
          <span aria-hidden="true" />
          {statusLabel(row.status)}
        </span>
      ),
    },
    {
      key: 'query',
      header: t('documentsPage.ingestion.question'),
      width: '48%',
      responsivePriority: 1,
      render: row => (
        <div className="document-ingestion-question">
          <Tooltip content={row.query || t('documentsPage.ingestion.questionUnavailable')}>
            <span>{row.query || t('documentsPage.ingestion.questionUnavailable')}</span>
          </Tooltip>
          <small>{channelLabel(row.channel)}</small>
        </div>
      ),
    },
    {
      key: 'capturedAt',
      header: t('documentsPage.captured'),
      width: '24%',
      responsivePriority: 2,
      render: row => formatDateTime(row.capturedAt),
    },
  ]

  const pagedCandidates = candidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const isReviewingSelected = selectedCandidate?.id === reviewingId

  return (
    <div className="document-ingestion-workspace">
      <header className="document-ingestion-header">
        <div>
          <h2>{t('documentsPage.ingestion.title')}</h2>
          <p>{t('documentsPage.ingestion.description')}</p>
        </div>
        <div className="document-ingestion-summary" aria-label={t('documentsPage.ingestion.summaryAria')}>
          <span><strong>{pendingCount}</strong>{t('documentsPage.ingestion.status.pending')}</span>
          <span><strong>{ingestedCount}</strong>{t('documentsPage.ingestion.status.ingested')}</span>
          <span><strong>{rejectedCount}</strong>{t('documentsPage.ingestion.status.rejected')}</span>
        </div>
      </header>

      <section className="document-ingestion-collection" aria-labelledby="document-ingestion-list-title">
        <div className="document-ingestion-collection__heading">
          <div>
            <h3 id="document-ingestion-list-title">{t('documentsPage.ingestion.listTitle')}</h3>
            <p>{t('documentsPage.ingestion.listDescription')}</p>
          </div>
          <div className="document-ingestion-collection__actions">
            <span>{t('common.showingCount', { shown: pagedCandidates.length, total: candidates.length })}</span>
            <button type="button" className="btn btn-secondary" onClick={onRefresh}>
              {t('common.refresh')}
            </button>
          </div>
        </div>

        <div className="document-ingestion-filters">
          <label>
            <span>{t('common.status')}</span>
            <select value={candidateStatus} onChange={event => setCandidateStatus(event.target.value)}>
              <option value="">{t('approvals.allStatuses')}</option>
              <option value="PENDING">{t('documentsPage.ingestion.status.pending')}</option>
              <option value="INGESTED">{t('documentsPage.ingestion.status.ingested')}</option>
              <option value="REJECTED">{t('documentsPage.ingestion.status.rejected')}</option>
            </select>
          </label>
          <label>
            <span>{t('documentsPage.channel')}</span>
            <input
              value={candidateChannel}
              onChange={event => setCandidateChannel(event.target.value)}
              placeholder={t('documentsPage.channelPlaceholder')}
            />
          </label>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              onFilter(candidateStatus, candidateChannel)
              setPage(1)
            }}
          >
            {t('documentsPage.filter')}
          </button>
        </div>

        {loadingCandidates ? (
          <div className="document-ingestion-loading"><TableSkeleton /></div>
        ) : candidates.length === 0 ? (
          <EmptyState message={t('documentsPage.noCandidates')} description={t('documentsPage.ingestion.emptyDescription')} />
        ) : (
          <>
            {candidates.length >= CANDIDATE_API_LIMIT && (
              <div className="document-ingestion-limit" role="status">
                {t('common.limitWarning', { limit: CANDIDATE_API_LIMIT })}
              </div>
            )}
            <DataTable
              tableId="document-ingestion-candidates"
              columns={candidateColumns}
              data={pagedCandidates}
              keyFn={row => row.id}
              selectedKey={selectedCandidate?.id ?? null}
              onRowClick={selectCandidate}
              page={page}
              pageSize={PAGE_SIZE}
              totalCount={candidates.length}
              onPageChange={setPage}
            />
          </>
        )}
      </section>

      <SideDrawer
        open={Boolean(selectedCandidate)}
        title={t('documentsPage.ingestion.reviewTitle')}
        onClose={() => selectCandidate(null)}
        size="wide"
      >
        {selectedCandidate && (
          <div className="document-ingestion-review">
            <div className="document-ingestion-review__status">
              <span className={`document-ingestion-status document-ingestion-status--${selectedCandidate.status.toLowerCase()}`}>
                <span aria-hidden="true" />
                {statusLabel(selectedCandidate.status)}
              </span>
              <p>{selectedCandidate.status === 'PENDING'
                ? t('documentsPage.ingestion.pendingDescription')
                : t('documentsPage.ingestion.reviewedDescription')}</p>
            </div>

            <section>
              <span className="document-ingestion-review__label">{t('documentsPage.ingestion.question')}</span>
              <p>{selectedCandidate.query || t('documentsPage.ingestion.questionUnavailable')}</p>
            </section>
            <section>
              <span className="document-ingestion-review__label">{t('documentsPage.ingestion.answer')}</span>
              <p>{selectedCandidate.response || t('documentsPage.ingestion.answerUnavailable')}</p>
            </section>

            {selectedCandidate.status === 'PENDING' && (
              <div className="form-group document-ingestion-review__comment">
                <label htmlFor="ingestion-review-comment">{t('documentsPage.reviewComment')}</label>
                <textarea
                  id="ingestion-review-comment"
                  rows={3}
                  value={reviewComment}
                  onChange={event => setReviewComment(event.target.value)}
                  placeholder={t('documentsPage.ingestion.commentPlaceholder')}
                />
              </div>
            )}

            {selectedCandidate.status === 'PENDING' && (
              <div className="document-ingestion-review__actions">
                <button type="button" className="btn btn-primary" disabled={isReviewingSelected} onClick={handleApprove}>
                  {isReviewingSelected ? <LoadingSpinner size="sm" /> : t('documentsPage.ingestion.approveAction')}
                </button>
                <button type="button" className="btn btn-secondary" disabled={isReviewingSelected} onClick={handleReject}>
                  {t('documentsPage.ingestion.rejectAction')}
                </button>
              </div>
            )}

            <details className="document-ingestion-review__technical">
              <summary>{t('documentsPage.ingestion.technicalDetails')}</summary>
              <dl>
                <div><dt>{t('documentsPage.ingestion.candidateId')}</dt><dd>{selectedCandidate.id}</dd></div>
                <div><dt>{t('documentsPage.run')}</dt><dd>{selectedCandidate.runId}</dd></div>
                <div><dt>{t('documentsPage.channel')}</dt><dd>{channelLabel(selectedCandidate.channel)}</dd></div>
                <div><dt>{t('documentsPage.captured')}</dt><dd>{formatDateTime(selectedCandidate.capturedAt)}</dd></div>
              </dl>
            </details>
          </div>
        )}
      </SideDrawer>
    </div>
  )
}
