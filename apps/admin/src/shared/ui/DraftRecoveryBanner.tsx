import { useTranslation } from 'react-i18next'
import { formatRelativeTimeKo } from '../lib/formatRelativeTimeKo'

export interface DraftRecoveryBannerProps {
  /** Renders the banner when true; returns null otherwise so callers can stay declarative. */
  open: boolean
  /** ISO timestamp when the draft was saved; renders "X분 전 임시저장됨" when present. */
  savedAt?: string
  /** Apply the recovered draft (caller wires `form.reset(draft)`). */
  onAccept: () => void
  /** Discard the recovered draft (clears localStorage). */
  onDismiss: () => void
}

/**
 * DraftRecoveryBanner
 *
 * Amber-tinted notice rendered at the top of a form / modal body when an
 * earlier draft was recovered from localStorage. Uses the brand attention
 * tokens (`--color-attention-dim` / `--color-attention-border`) so the
 * affordance reads as "review me" — opt-in, not an error.
 *
 * The banner deliberately stays small (single horizontal row on wide modals,
 * stacked on narrow ones) and never blocks the form below: the admin can
 * dismiss without applying and continue with a clean slate.
 */
export function DraftRecoveryBanner({
  open,
  savedAt,
  onAccept,
  onDismiss,
}: DraftRecoveryBannerProps) {
  const { t } = useTranslation()
  if (!open) return null

  const relative = savedAt ? formatRelativeTimeKo(savedAt) : null
  const savedLabel = relative
    ? t('common.draft.savedRelative', { time: relative })
    : null

  return (
    <div
      className="draft-recovery-banner"
      role="status"
      aria-live="polite"
      data-testid="draft-recovery-banner"
    >
      <div className="draft-recovery-banner__copy">
        <span className="draft-recovery-banner__title">
          {t('common.draft.recoveryTitle')}
        </span>
        <span className="draft-recovery-banner__hint">
          {t('common.draft.recoveryHint')}
          {savedLabel ? <> · <span>{savedLabel}</span></> : null}
        </span>
      </div>
      <div className="draft-recovery-banner__actions">
        <button
          type="button"
          className="btn btn-sm btn-secondary"
          onClick={onDismiss}
          data-testid="draft-recovery-dismiss"
        >
          {t('common.draft.dismiss')}
        </button>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          onClick={onAccept}
          data-testid="draft-recovery-accept"
        >
          {t('common.draft.accept')}
        </button>
      </div>
    </div>
  )
}
