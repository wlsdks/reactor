import { useTranslation } from 'react-i18next'
import type { FeedbackRating, FeedbackReviewStatus } from '../types'

const SYSTEM_TAG_KEYS: Record<string, string> = {
  'BULK-REVIEWED': 'feedbackPage.systemTagLabels.bulkReviewed',
  RESOLVED: 'feedbackPage.systemTagLabels.resolved',
  'AUTO-CLASSIFIED': 'feedbackPage.systemTagLabels.autoClassified',
}

const REVIEW_TAG_KEYS: Record<string, string> = {
  actionable: 'feedbackPage.reviewTagLabels.actionable',
  resolved: 'feedbackPage.reviewTagLabels.resolved',
  'false-positive': 'feedbackPage.reviewTagLabels.falsePositive',
  'needs-followup': 'feedbackPage.reviewTagLabels.needsFollowup',
  promoted: 'feedbackPage.reviewTagLabels.promoted',
  langsmith: 'feedbackPage.reviewTagLabels.langsmith',
}

const DOMAIN_LABELS: Record<string, string> = {
  project_management: '프로젝트 관리',
  knowledge_base: '지식 검색',
  devops: '배포 운영',
  billing: '비용 관리',
}

const INTENT_LABELS: Record<string, string> = {
  jira_create: 'Jira 이슈 만들기',
  content_summary: '내용 요약',
  status_check: '상태 확인',
  cost_analysis: '비용 분석',
}

export function ratingBadgeClass(rating: FeedbackRating): string {
  return rating === 'thumbs_up' ? 'badge-green' : 'badge-red'
}

export function statusBadgeClass(status: FeedbackReviewStatus): string {
  return status === 'done' ? 'badge-green' : 'badge-yellow'
}

// Map raw enum / system tag values to localized labels.
// Unknown values (incl. user-defined review tags) pass through unchanged.
export function useLabelLocalizers() {
  const { t } = useTranslation()
  const localizeRating = (rating: FeedbackRating): string =>
    rating === 'thumbs_up'
      ? t('feedbackPage.ratingLabels.thumbsUp')
      : t('feedbackPage.ratingLabels.thumbsDown')
  const localizeStatus = (status: FeedbackReviewStatus): string =>
    status === 'done'
      ? t('feedbackPage.statusLabels.done')
      : t('feedbackPage.statusLabels.inbox')
  const localizeSystemTag = (tag: string): string => {
    const key = SYSTEM_TAG_KEYS[tag.toUpperCase()]
    return key ? t(key) : localizeReviewTag(tag)
  }
  const localizeReviewTag = (tag: string): string => {
    const key = REVIEW_TAG_KEYS[tag.trim().toLowerCase()]
    return key ? t(key) : t('feedbackPage.classificationLabels.unknownTag')
  }
  const localizeDomain = (domain: string): string =>
    DOMAIN_LABELS[domain] ?? t('feedbackPage.classificationLabels.unknownDomain')
  const localizeIntent = (intent: string): string =>
    INTENT_LABELS[intent] ?? t('feedbackPage.classificationLabels.unknownIntent')
  return {
    localizeRating,
    localizeStatus,
    localizeSystemTag,
    localizeReviewTag,
    localizeDomain,
    localizeIntent,
  }
}
