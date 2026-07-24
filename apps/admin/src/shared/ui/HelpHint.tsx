import './HelpHint.css'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DetailModal } from './DetailModal'
import { Tooltip, type TooltipPlacement } from './Tooltip'

export interface HelpHintProps {
  /** Tooltip body text. Also exposed as `aria-label` so screen readers announce it. */
  label: string
  /** Tooltip anchor side. Defaults to `'top'`. */
  placement?: TooltipPlacement
  /** Visual size — `'sm'` (16px, default) for inline header glyphs, `'md'` (18px) for form labels / cards. */
  size?: 'sm' | 'md'
  /** Optional extra class for the trigger button. */
  className?: string
  /** Short term name used as the centered explanation dialog title. */
  title?: string
}

/**
 * `HelpHint` — a tiny circular `!` glyph that surfaces a tooltip on hover and
 * focus. Toss / Karrot use this pattern next to ambiguous column headers and
 * form labels so operators can disambiguate jargon ("actor", "category",
 * "rollback readiness") without leaving the page.
 *
 * Reuses the existing `Tooltip` primitive for portal positioning, focus / hover
 * handling, and `aria-describedby` wiring; the trigger itself is a real
 * `<button>` so it lives on the keyboard tab order.
 */
export function HelpHint({
  label,
  placement = 'top',
  size = 'sm',
  className,
  title,
}: HelpHintProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const sizeClass = size === 'md' ? ' help-hint--md' : ''
  const composed = `help-hint${sizeClass}${className ? ` ${className}` : ''}`
  return (
    <>
      <Tooltip content={label} placement={placement}>
        <button
          type="button"
          className={composed}
          aria-label={label}
          title={label}
          onClick={() => setOpen(true)}
        >
          !
        </button>
      </Tooltip>
      {open ? (
        <DetailModal
          open
          title={title ?? t('common.technicalTermHelp')}
          onClose={() => setOpen(false)}
          size="default"
        >
          <p className="help-hint-dialog__description">{label}</p>
        </DetailModal>
      ) : null}
    </>
  )
}
