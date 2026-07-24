import type { CSSProperties } from 'react'

export type FieldStatus = 'idle' | 'validating' | 'valid' | 'error'

interface FieldStatusIndicatorProps {
  status: FieldStatus
  /** Optional accessible label override. */
  label?: string
}

/**
 * Small inline indicator for real-time form validation state.
 *
 * - idle: renders nothing
 * - validating: subtle pulsing dot (debounce window in progress)
 * - valid: green check mark using --color-success
 * - error: red cross using --color-error
 *
 * The element is decorative for sighted users; actual error text is rendered
 * separately in the form-error region with role="alert" + aria-describedby.
 * We expose an aria-label so screen readers can still announce status when
 * the indicator is focused via assistive tech.
 */
export function FieldStatusIndicator({ status, label }: FieldStatusIndicatorProps) {
  if (status === 'idle') return null

  const baseStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 16,
    height: 16,
    marginLeft: 6,
    fontSize: 'var(--text-xs)',
    lineHeight: 1,
    verticalAlign: 'middle',
  }

  if (status === 'validating') {
    return (
      <span
        className="field-status field-status--validating"
        aria-label={label ?? 'Validating'}
        role="status"
        style={baseStyle}
      >
        <span
          aria-hidden="true"
          style={{
            display: 'inline-block',
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: 'var(--text-dim)',
            opacity: 0.65,
            animation: 'fieldStatusPulse 1s ease-in-out infinite',
          }}
        />
      </span>
    )
  }

  if (status === 'valid') {
    return (
      <span
        className="field-status field-status--valid"
        aria-label={label ?? 'Valid'}
        role="status"
        style={{ ...baseStyle, color: 'var(--color-success)', fontWeight: 'var(--font-weight-strong)' }}
      >
        <span aria-hidden="true">✓</span>
      </span>
    )
  }

  // error
  return (
    <span
      className="field-status field-status--error"
      aria-label={label ?? 'Invalid'}
      role="status"
      style={{ ...baseStyle, color: 'var(--color-error)', fontWeight: 'var(--font-weight-strong)' }}
    >
      <span aria-hidden="true">✗</span>
    </span>
  )
}
