import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { OperationButton } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { useToastStore } from '../../../shared/store/toast.store'
import { formatISODate } from '../../../shared/lib/formatters'
import * as feedbackApi from '../api'
import type { FeedbackEntry, FeedbackReviewStatus } from '../types'
import { STANDARD_REVIEW_TAGS } from '../schema'
import { feedbackCanClose } from '../feedbackEvalLifecycle'
import { useLabelLocalizers } from './feedbackLabels'

interface Props {
  feedback: FeedbackEntry
}

/**
 * Review panel — inside detail drawer.
 *
 * UX rationale:
 * - Status toggle (inbox/done) + tag chips (actionable/resolved/...) + note textarea.
 * - Version-aware: shows "Review outdated" banner when backend returns 409.
 * - Form dirty state triggers Save; cancel reverts to current version.
 *
 * Caller must pass `key={feedback.feedbackId}-${feedback.version}` so a new
 * feedback selection or post-save version bump remounts this component and
 * re-initializes local form state from the freshly-fetched entry. This avoids
 * the setState-in-effect anti-pattern that caused React Compiler bail-outs.
 */
export function FeedbackReviewPanel({ feedback }: Props) {
  const { t } = useTranslation()
  const { localizeReviewTag } = useLabelLocalizers()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)

  const [status, setStatus] = useState<FeedbackReviewStatus>(feedback.reviewStatus)
  const [tags, setTags] = useState<string[]>(feedback.reviewTags)
  const [note, setNote] = useState(feedback.reviewNote ?? '')
  const [conflict, setConflict] = useState<string | null>(null)
  const closeBlocked = !feedbackCanClose(feedback)

  const mutation = useMutation({
    mutationFn: () => feedbackApi.updateReview(feedback.feedbackId, feedback.version, {
      status,
      tags,
      tagMode: 'set',
      note: note.trim() || null,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feedback.all() })
      addToast({ type: 'success', message: t('feedbackPage.review.saved') })
      setConflict(null)
    },
    onError: (err: unknown) => {
      const msg = getErrorMessage(err)
      if (msg.toLowerCase().includes('version_conflict') || msg.toLowerCase().includes('conflict')) {
        setConflict(t('feedbackPage.review.conflict'))
      } else {
        addToast({ type: 'error', message: msg })
      }
    },
  })

  function toggleTag(tag: string) {
    setTags((prev) => prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag])
  }

  const dirty = status !== feedback.reviewStatus ||
    !arraysEqual(tags, feedback.reviewTags) ||
    note !== (feedback.reviewNote ?? '')

  return (
    <div className="fb-review-panel">
      <h3 className="fb-review-panel__title">{t('feedbackPage.review.title')}</h3>
      {feedback.reviewedBy && (
        <div className="fb-review-panel__meta">
          {t('feedbackPage.review.lastReviewedBy', {
            actor: feedback.reviewedBy,
            at: feedback.reviewedAt ? formatISODate(feedback.reviewedAt) : '-',
          })}
          {' · v'}{feedback.version}
        </div>
      )}

      {conflict && (
        <div className="fb-conflict-banner" role="alert">
          {conflict}
        </div>
      )}

      {closeBlocked && (
        <div className="alert alert-warning" role="status">
          {t('feedbackPage.evalLifecycle.closeBlocked')}
        </div>
      )}

      <div>
        <div className="fb-toolbar__label" style={{ marginBottom: 'var(--space-2)' }}>
          {t('feedbackPage.review.status')}
        </div>
        <div className="fb-status-toggle">
          <button
            type="button"
            className={`fb-status-toggle__btn${status === 'inbox' ? ' fb-status-toggle__btn--active' : ''}`}
            onClick={() => setStatus('inbox')}
          >
            {t('feedbackPage.review.statusInbox')}
          </button>
          <button
            type="button"
            className={`fb-status-toggle__btn${status === 'done' ? ' fb-status-toggle__btn--active' : ''}`}
            onClick={() => setStatus('done')}
            disabled={closeBlocked}
            title={closeBlocked ? t('feedbackPage.evalLifecycle.closeBlocked') : undefined}
          >
            {t('feedbackPage.review.statusDone')}
          </button>
        </div>
      </div>

      <div>
        <div className="fb-toolbar__label" style={{ marginBottom: 'var(--space-2)' }}>
          {t('feedbackPage.review.tags')}
        </div>
        <div className="fb-tag-chips">
          {STANDARD_REVIEW_TAGS.map((tag) => (
            <button
              key={tag}
              type="button"
              className={`fb-tag-chip${tags.includes(tag) ? ' fb-tag-chip--selected' : ''}`}
              onClick={() => toggleTag(tag)}
            >
              {localizeReviewTag(tag)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="fb-toolbar__label" style={{ marginBottom: 'var(--space-2)' }}>
          {t('feedbackPage.review.note')}
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder={t('feedbackPage.review.notePlaceholder')}
          style={{
            width: '100%',
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: 'var(--text-sm)',
            padding: 'var(--space-2) var(--space-3)',
            background: 'var(--bg-input, var(--bg-root))',
            color: 'var(--text-primary)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            resize: 'vertical',
          }}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
        <OperationButton
          variant="secondary"
          className="btn-sm"
          onClick={() => {
            setStatus(feedback.reviewStatus)
            setTags(feedback.reviewTags)
            setNote(feedback.reviewNote ?? '')
            setConflict(null)
          }}
          disabled={!dirty || mutation.isPending}
        >
          {t('common.cancel')}
        </OperationButton>
        <OperationButton
          variant="primary"
          className="btn-sm"
          onClick={() => mutation.mutate()}
          disabled={!dirty || !!conflict}
          isOperating={mutation.isPending}
        >
          {t('common.save')}
        </OperationButton>
      </div>
    </div>
  )
}

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  const sortedA = [...a].sort()
  const sortedB = [...b].sort()
  return sortedA.every((v, i) => v === sortedB[i])
}
