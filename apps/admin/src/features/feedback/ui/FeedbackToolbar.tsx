import { useTranslation } from 'react-i18next'
import type { FeedbackRating, FeedbackReviewStatus } from '../types'

export interface FeedbackToolbarProps {
  qFilter: string
  onQFilterChange: (value: string) => void
  ratingFilter: '' | FeedbackRating
  onRatingFilterChange: (value: '' | FeedbackRating) => void
  statusFilter: '' | FeedbackReviewStatus
  onStatusFilterChange: (value: '' | FeedbackReviewStatus) => void
  hasCommentFilter: '' | 'yes' | 'no'
  onHasCommentFilterChange: (value: '' | 'yes' | 'no') => void
  fromFilter: string
  onFromFilterChange: (value: string) => void
  toFilter: string
  onToFilterChange: (value: string) => void
  shown: number
  total: number
}

export function FeedbackToolbar({
  qFilter,
  onQFilterChange,
  ratingFilter,
  onRatingFilterChange,
  statusFilter,
  onStatusFilterChange,
  hasCommentFilter,
  onHasCommentFilterChange,
  fromFilter,
  onFromFilterChange,
  toFilter,
  onToFilterChange,
  shown,
  total,
}: FeedbackToolbarProps) {
  const { t } = useTranslation()

  return (
    <div className="fb-toolbar">
      <input
        className="fb-toolbar__search"
        type="search"
        placeholder={t('feedbackPage.filters.searchPlaceholder')}
        value={qFilter}
        onChange={(e) => onQFilterChange(e.target.value)}
        aria-label={t('feedbackPage.filters.search')}
      />

      <div className="fb-toolbar__group">
        <label className="fb-toolbar__label" htmlFor="fb-rating">
          {t('feedbackPage.columns.rating')}
        </label>
        <select
          id="fb-rating"
          value={ratingFilter}
          onChange={(e) => onRatingFilterChange(e.target.value as FeedbackRating | '')}
        >
          <option value="">{t('feedbackPage.filters.all')}</option>
          <option value="thumbs_up">👍 {t('feedbackPage.ratingLabels.thumbsUp')}</option>
          <option value="thumbs_down">👎 {t('feedbackPage.ratingLabels.thumbsDown')}</option>
        </select>
      </div>

      <div className="fb-toolbar__group">
        <label className="fb-toolbar__label" htmlFor="fb-status">
          {t('feedbackPage.columns.status')}
        </label>
        <select
          id="fb-status"
          value={statusFilter}
          onChange={(e) => onStatusFilterChange(e.target.value as FeedbackReviewStatus | '')}
        >
          <option value="">{t('feedbackPage.filters.all')}</option>
          <option value="inbox">{t('feedbackPage.statusLabels.inbox')}</option>
          <option value="done">{t('feedbackPage.statusLabels.done')}</option>
        </select>
      </div>

      <div className="fb-toolbar__group">
        <label className="fb-toolbar__label" htmlFor="fb-comment">
          {t('feedbackPage.filters.hasComment')}
        </label>
        <select
          id="fb-comment"
          value={hasCommentFilter}
          onChange={(e) => onHasCommentFilterChange(e.target.value as '' | 'yes' | 'no')}
        >
          <option value="">{t('feedbackPage.filters.all')}</option>
          <option value="yes">{t('feedbackPage.filters.commentYes')}</option>
          <option value="no">{t('feedbackPage.filters.commentNo')}</option>
        </select>
      </div>

      <input
        type="date"
        value={fromFilter}
        onChange={(e) => onFromFilterChange(e.target.value)}
        title={t('feedbackPage.filters.from')}
      />
      <input
        type="date"
        value={toFilter}
        onChange={(e) => onToFilterChange(e.target.value)}
        title={t('feedbackPage.filters.to')}
      />

      <div className="fb-toolbar__spacer" />
      <span className="fb-toolbar__meta">
        {t('feedbackPage.resultsSummary', { shown, total })}
      </span>
    </div>
  )
}
