import type { FeedbackEntry } from './types'

export type FeedbackEvalLifecycleStage =
  | 'not_required'
  | 'blocked'
  | 'ready'
  | 'sync_pending'
  | 'closed'

export function feedbackRequiresEvalClosure(feedback: FeedbackEntry): boolean {
  return feedback.rating === 'thumbs_down'
    && Boolean(feedback.nextActions?.some((action) => action.id === 'promote-eval'))
}

export function feedbackEvalLifecycleStage(feedback: FeedbackEntry): FeedbackEvalLifecycleStage {
  if (!feedbackRequiresEvalClosure(feedback)) return 'not_required'
  const tags = new Set(feedback.reviewTags.map((tag) => tag.trim().toLowerCase()))
  if (
    tags.has('promoted')
    && tags.has('langsmith')
    && feedback.reviewStatus === 'done'
    && Boolean(feedback.reviewNote?.trim())
  ) return 'closed'
  if (tags.has('promoted')) return 'sync_pending'
  if (feedback.blockedNextActionIds?.includes('promote-eval')) return 'blocked'
  return 'ready'
}

export function feedbackCanClose(feedback: FeedbackEntry): boolean {
  const stage = feedbackEvalLifecycleStage(feedback)
  return stage === 'not_required' || stage === 'closed'
}
