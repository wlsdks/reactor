import { useId, type CSSProperties, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Minus, Plus } from 'lucide-react'

export interface NumberInputStepperProps {
  value: number | null
  onChange: (next: number | null) => void
  min?: number
  max?: number
  /** Step size for increment/decrement buttons and arrow keys. Defaults to 1. */
  step?: number
  /**
   * Number of decimals to round to when displaying / emitting values.
   * Derived from `step` when omitted (e.g. step 0.1 → precision 1).
   */
  precision?: number
  ariaLabel?: string
  placeholder?: string
  disabled?: boolean
  /** 'sm' renders compact 24×24 buttons; 'md' (default) renders 28×28. */
  size?: 'sm' | 'md'
  /** Trailing dim suffix rendered inside the group (e.g. "초", "%"). */
  suffix?: string
  className?: string
  id?: string
  name?: string
  required?: boolean
  /** Hooks for react-hook-form interop / a11y wiring. */
  onBlur?: () => void
  'aria-invalid'?: boolean
  'aria-describedby'?: string
  'aria-required'?: boolean
}

/**
 * Derive decimal precision from a step value (e.g. 0.25 → 2, 1 → 0).
 * Used to avoid floating-point dust in displayed / emitted values.
 */
function derivePrecisionFromStep(step: number): number {
  if (!Number.isFinite(step) || step === 0) return 0
  const str = Math.abs(step).toString()
  const dotIndex = str.indexOf('.')
  if (dotIndex === -1) return 0
  return str.length - dotIndex - 1
}

function roundTo(value: number, precision: number): number {
  if (precision <= 0) return Math.round(value)
  const factor = 10 ** precision
  return Math.round(value * factor) / factor
}

function clamp(value: number, min: number | undefined, max: number | undefined): number {
  let next = value
  if (typeof min === 'number' && next < min) next = min
  if (typeof max === 'number' && next > max) next = max
  return next
}

/**
 * Numeric input with explicit increment/decrement controls and clamped keyboard adjustments.
 *
 * Why a primitive instead of native `<input type="number">`:
 * - Native steppers vary across browsers and are tiny / hard to hit.
 * - Mono-font display + dim suffix matches the data-numeric DESIGN.md style.
 * - Clamps + keyboard handling (Shift+Arrow = step×10) are unified once.
 */
export function NumberInputStepper({
  value,
  onChange,
  min,
  max,
  step = 1,
  precision,
  ariaLabel,
  placeholder,
  disabled = false,
  size = 'md',
  suffix,
  className,
  id,
  name,
  required,
  onBlur,
  'aria-invalid': ariaInvalid,
  'aria-describedby': ariaDescribedBy,
  'aria-required': ariaRequired,
}: NumberInputStepperProps) {
  const { t } = useTranslation()
  const reactId = useId()
  const inputId = id ?? `nis-${reactId}`
  const effectivePrecision = precision ?? derivePrecisionFromStep(step)

  const numericValue = value ?? null
  const atMin = typeof min === 'number' && numericValue !== null && numericValue <= min
  const atMax = typeof max === 'number' && numericValue !== null && numericValue >= max

  const decrementDisabled = disabled || atMin
  const incrementDisabled = disabled || atMax

  function emit(next: number | null) {
    if (next === null) {
      onChange(null)
      return
    }
    const clamped = clamp(next, min, max)
    const rounded = roundTo(clamped, effectivePrecision)
    onChange(rounded)
  }

  function adjustBy(delta: number) {
    const base = numericValue ?? (typeof min === 'number' ? min : 0)
    emit(base + delta)
  }

  function handleInputChange(event: React.ChangeEvent<HTMLInputElement>) {
    const raw = event.target.value
    if (raw === '') {
      onChange(null)
      return
    }
    const parsed = Number(raw)
    if (Number.isNaN(parsed)) return
    // While typing we don't clamp aggressively — only round to precision so
    // partial inputs like "1." remain usable. Clamp on blur via parent.
    const rounded = roundTo(parsed, effectivePrecision)
    onChange(rounded)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return
    event.preventDefault()
    const multiplier = event.shiftKey ? 10 : 1
    const direction = event.key === 'ArrowUp' ? 1 : -1
    adjustBy(step * multiplier * direction)
  }

  const buttonSize = size === 'sm'
    ? 'var(--control-height-compact)'
    : 'var(--control-height-default)'
  const iconSize = size === 'sm'
    ? 'var(--icon-size-xs)'
    : 'var(--icon-size-sm)'
  const fontSize = size === 'sm' ? 'var(--text-xs)' : 'var(--text-sm)'

  const groupStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'stretch',
    border: '1px solid var(--border-standard)',
    borderRadius: 'var(--control-radius)',
    background: 'var(--bg-elevated)',
    overflow: 'hidden',
    width: '100%',
  }

  const buttonStyle: CSSProperties = {
    width: buttonSize,
    height: buttonSize,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--button-ghost-bg)',
    color: 'var(--text-primary)',
    border: 'none',
    cursor: 'pointer',
    flex: '0 0 auto',
  }

  const inputStyle: CSSProperties = {
    flex: 1,
    minWidth: 0,
    padding: '0 var(--space-2)',
    background: 'transparent',
    color: 'var(--text-primary)',
    border: 'none',
    outline: 'none',
    fontFamily: 'var(--font-mono)',
    fontWeight: 'var(--font-weight-emphasis)',
    fontSize,
    textAlign: 'right',
    // Hide native browser steppers — we provide our own.
    MozAppearance: 'textfield',
  }

  const suffixStyle: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    paddingRight: size === 'sm' ? 6 : 8,
    color: 'var(--text-dim)',
    fontSize: size === 'sm' ? 'var(--text-xxs)' : 'var(--text-xs)',
    fontFamily: 'var(--font-mono)',
    pointerEvents: 'none',
  }

  return (
    <span
      className={`number-input-stepper${className ? ` ${className}` : ''}`}
      style={groupStyle}
      data-size={size}
    >
      <button
        type="button"
        aria-label={t('common.numberStepper.decrementAria')}
        onClick={() => adjustBy(-step)}
        disabled={decrementDisabled}
        style={{
          ...buttonStyle,
          borderRight: '1px solid var(--border-standard)',
          opacity: decrementDisabled ? 0.4 : 1,
          cursor: decrementDisabled ? 'not-allowed' : 'pointer',
        }}
        tabIndex={-1}
      >
        <Minus aria-hidden="true" size={iconSize} strokeWidth={1.8} />
      </button>
      <input
        id={inputId}
        name={name}
        type="number"
        inputMode="decimal"
        value={numericValue === null ? '' : String(numericValue)}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onBlur={onBlur}
        disabled={disabled}
        placeholder={placeholder}
        min={min}
        max={max}
        step={step}
        required={required}
        aria-label={ariaLabel}
        aria-invalid={ariaInvalid}
        aria-describedby={ariaDescribedBy}
        aria-required={ariaRequired}
        style={inputStyle}
      />
      {suffix && (
        <span style={suffixStyle} aria-hidden="true">
          {suffix}
        </span>
      )}
      <button
        type="button"
        aria-label={t('common.numberStepper.incrementAria')}
        onClick={() => adjustBy(step)}
        disabled={incrementDisabled}
        style={{
          ...buttonStyle,
          borderLeft: '1px solid var(--border-standard)',
          opacity: incrementDisabled ? 0.4 : 1,
          cursor: incrementDisabled ? 'not-allowed' : 'pointer',
        }}
        tabIndex={-1}
      >
        <Plus aria-hidden="true" size={iconSize} strokeWidth={1.8} />
      </button>
    </span>
  )
}
