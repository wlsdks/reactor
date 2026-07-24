import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { copyToClipboard } from '../lib/clipboard'

export interface CopyButtonProps {
  /** Value placed on the clipboard. When empty the button is disabled. */
  value: string
  /** Label used in tooltip / aria-label / success toast (e.g. "ID"). */
  label?: string
  /** Visual size — `'sm'` (24×24 / 28h) or `'md'` (32×32 / 32h). */
  size?: 'sm' | 'md'
  /** Visual variant — icon-only or icon + truncated value. */
  variant?: 'icon' | 'icon-text'
  /** Extra class names appended to the button. */
  className?: string
}

const CHECK_FEEDBACK_MS = 1200

/**
 * Unified clipboard copy control.
 *
 * - `'icon'` variant renders a 16×16 clipboard SVG (28×28 / 32×32 hit target).
 * - `'icon-text'` variant renders the icon plus a mono-font truncated value
 *   (`12ch` clamp). Use for inline ID rows in detail panels.
 * - On click the global `copyToClipboard` helper writes the value, emits the
 *   built-in success / failure toast, and the icon swaps to a check mark for
 *   ~1.2 s as visual confirmation.
 */
export function CopyButton({
  value,
  label,
  size = 'sm',
  variant = 'icon',
  className,
}: CopyButtonProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current)
      }
    }
  }, [])

  const resolvedLabel = label ?? t('common.copy.defaultLabel')
  const ariaLabel = t('common.copy.aria', { label: resolvedLabel })
  const disabled = value.length === 0

  async function handleClick() {
    if (disabled) return
    const ok = await copyToClipboard(value, { label: resolvedLabel })
    if (!ok) return
    setCopied(true)
    if (timerRef.current !== null) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setCopied(false)
      timerRef.current = null
    }, CHECK_FEEDBACK_MS)
  }

  const classes = [
    'copy-button',
    `copy-button--${variant}`,
    `copy-button--${size}`,
    copied ? 'copy-button--copied' : '',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type="button"
      className={classes}
      onClick={handleClick}
      disabled={disabled}
      aria-label={ariaLabel}
      title={ariaLabel}
      data-copied={copied || undefined}
    >
      <span className="copy-button__icon" aria-hidden="true">
        {copied ? <CheckIcon /> : <ClipboardIcon />}
      </span>
      {variant === 'icon-text' && (
        <span className="copy-button__value" data-testid="copy-button-value">
          {value || ''}
        </span>
      )}
    </button>
  )
}

function ClipboardIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
    >
      <rect x="4.5" y="3" width="7" height="10.5" rx="1.25" />
      <path d="M6.25 3v-.5A1.25 1.25 0 0 1 7.5 1.25h1A1.25 1.25 0 0 1 9.75 2.5V3" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
    >
      <polyline points="3,8.5 6.5,12 13,4.5" />
    </svg>
  )
}
