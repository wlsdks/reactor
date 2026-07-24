/**
 * Tiny inline status icons for StatusBadge — colorblind-safe redundancy
 * for semantic intent badges (WCAG 2.1 SC 1.4.1: Use of Color).
 *
 * Each icon:
 * - 16x16 viewBox, sized externally via CSS (default 12px in `.badge svg`).
 * - Uses `currentColor` so it inherits the parent badge's text color.
 * - `aria-hidden` + `focusable="false"` — the parent badge owns the label.
 *
 * Stroke widths are tuned for visibility at 12px on dark surfaces.
 */

import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

const baseProps: IconProps = {
  viewBox: '0 0 16 16',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: false,
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M3 8.5 L6.5 12 L13 4.5" />
    </svg>
  )
}

export function WarningIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M8 2 L14.5 13.5 L1.5 13.5 Z" />
      <line x1="8" y1="6.5" x2="8" y2="9.5" />
      <circle cx="8" cy="11.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function XIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <line x1="3.5" y1="3.5" x2="12.5" y2="12.5" />
      <line x1="12.5" y1="3.5" x2="3.5" y2="12.5" />
    </svg>
  )
}

export function InfoIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <circle cx="8" cy="8" r="6.5" />
      <line x1="8" y1="7" x2="8" y2="11.5" />
      <circle cx="8" cy="4.75" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function HourglassIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <line x1="3.5" y1="2.5" x2="12.5" y2="2.5" />
      <line x1="3.5" y1="13.5" x2="12.5" y2="13.5" />
      <path d="M4 2.5 L12 2.5 L8 8 L12 13.5 L4 13.5 L8 8 Z" />
    </svg>
  )
}

export function ProcessingIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M13.5 8 A5.5 5.5 0 1 1 11.5 3.7" />
      <polyline points="13.5,2 13.5,4.5 11,4.5" />
    </svg>
  )
}

export function StarIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <path d="M8 2 L9.7 6.2 L14 6.6 L10.7 9.5 L11.7 13.7 L8 11.4 L4.3 13.7 L5.3 9.5 L2 6.6 L6.3 6.2 Z" />
    </svg>
  )
}

export function DotIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <circle cx="8" cy="8" r="3" fill="currentColor" stroke="none" />
    </svg>
  )
}

/**
 * Lock icon used by the EmptyState forbidden variant. Communicates that the
 * absence of data is the consequence of a permission boundary (HTTP 403)
 * rather than missing or filtered data — the user cannot resolve it by
 * adjusting filters or retrying.
 */
export function LockIcon(props: IconProps) {
  return (
    <svg {...baseProps} {...props}>
      <rect x="3.5" y="7.5" width="9" height="6.5" rx="1" />
      <path d="M5.5 7.5 V5.5 a2.5 2.5 0 0 1 5 0 V7.5" />
      <circle cx="8" cy="10.5" r="0.75" fill="currentColor" stroke="none" />
    </svg>
  )
}
