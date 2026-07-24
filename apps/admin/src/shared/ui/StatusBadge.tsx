import type { ReactNode } from 'react'
import {
  CheckIcon,
  DotIcon,
  HourglassIcon,
  InfoIcon,
  ProcessingIcon,
  StarIcon,
  WarningIcon,
  XIcon,
} from './icons/StatusIcons'
import { Tooltip } from './Tooltip'

interface StatusBadgeProps {
  status: string
  /** Optional override label rendered inside the badge. Defaults to the status string. */
  label?: string
  /**
   * Render the icon only (no visible text). The status / label is exposed
   * to assistive tech via `aria-label`. Useful in dense table cells.
   */
  iconOnly?: boolean
  /**
   * Opt out of the icon prefix and fall back to the legacy text-only badge.
   * Default `false` — the icon ships by default for WCAG 1.4.1 compliance.
   */
  hideIcon?: boolean
}

/**
 * Semantic intent — drives both the color class and the icon. Status strings
 * are mapped to one of these intents so colorblind users have a redundant
 * non-color cue (icon shape) for every badge.
 */
type Intent =
  | 'success'
  | 'warning'
  | 'error'
  | 'info'
  | 'pending'
  | 'processing'
  | 'attention'
  | 'neutral'

// F-9 migration: visible status pills now use semantic intent classes.
// SUCCESS → badge-success (success intent), PENDING → badge-pending
// (pending-review intent, violet), ERROR → badge-error (error intent).
// Remaining statuses still use legacy hue-based classes; migrate as needed.
const colorMap: Record<string, string> = {
  CONNECTED: 'badge-green',
  ACTIVE: 'badge-green',
  SUCCESS: 'badge-success',
  SUCCEEDED: 'badge-success',
  COMPLETED: 'badge-success',
  APPROVED: 'badge-green',
  INDEXED: 'badge-green',
  ENABLED: 'badge-green',
  PASS: 'badge-green',

  PENDING: 'badge-pending',
  RUNNING: 'badge-yellow',
  DRAFT: 'badge-yellow',
  WARN: 'badge-yellow',

  DISCONNECTED: 'badge-gray',
  ARCHIVED: 'badge-gray',
  SKIPPED: 'badge-gray',
  DISABLED: 'badge-gray',
  CANCELLED: 'badge-gray',
  PENDING_REVIEW: 'badge-pending',

  FAILED: 'badge-red',
  REJECTED: 'badge-red',
  TIMED_OUT: 'badge-red',
  ERROR: 'badge-error',
  FAIL: 'badge-red',
}

/**
 * Status string → semantic intent. Drives the icon shape so that users with
 * color-vision deficiency can still distinguish badges by their glyph.
 */
const intentMap: Record<string, Intent> = {
  CONNECTED: 'success',
  ACTIVE: 'success',
  SUCCESS: 'success',
  SUCCEEDED: 'success',
  COMPLETED: 'success',
  APPROVED: 'success',
  INDEXED: 'success',
  ENABLED: 'success',
  PASS: 'success',

  WARN: 'warning',
  DRAFT: 'warning',

  RUNNING: 'processing',
  PROCESSING: 'processing',

  PENDING: 'pending',
  PENDING_REVIEW: 'pending',

  FAILED: 'error',
  REJECTED: 'error',
  TIMED_OUT: 'error',
  ERROR: 'error',
  FAIL: 'error',

  DISCONNECTED: 'neutral',
  ARCHIVED: 'neutral',
  SKIPPED: 'neutral',
  DISABLED: 'neutral',
  CANCELLED: 'neutral',
}

const iconForIntent: Record<Intent, () => ReactNode> = {
  success: () => <CheckIcon />,
  warning: () => <WarningIcon />,
  error: () => <XIcon />,
  info: () => <InfoIcon />,
  pending: () => <HourglassIcon />,
  processing: () => <ProcessingIcon />,
  attention: () => <StarIcon />,
  neutral: () => <DotIcon />,
}

export function StatusBadge({ status, label, iconOnly = false, hideIcon = false }: StatusBadgeProps) {
  const upper = status.toUpperCase()
  const cls = colorMap[upper] ?? 'badge-gray'
  const intent: Intent = intentMap[upper] ?? 'neutral'
  const visibleText = label ?? status
  const Icon = iconForIntent[intent]

  if (iconOnly) {
    // Icon-only badge always truncates to the icon glyph; surface the full
    // status name through a Tooltip on hover so sighted users discover the
    // label without opening the row. Screen readers still get `aria-label`.
    return (
      <Tooltip content={visibleText}>
        <span
          className={`badge badge-icon-only ${cls}`}
          aria-label={visibleText}
          data-intent={intent}
        >
          {Icon()}
        </span>
      </Tooltip>
    )
  }

  return (
    <span className={`badge ${cls}`} data-intent={intent}>
      {!hideIcon && Icon()}
      {visibleText}
    </span>
  )
}
