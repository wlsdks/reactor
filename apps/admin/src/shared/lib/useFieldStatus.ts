import { useDebouncedValue } from './useDebouncedValue'
import type { FieldStatus } from '../ui/FieldStatusIndicator'

/**
 * useFieldStatus
 *
 * Derives a real-time validation status for a single form field.
 *
 * - idle:        the field is empty (and untouched OR no error)
 * - validating:  user is actively typing (raw value differs from debounced)
 * - error:       react-hook-form has reported an error for this field
 * - valid:       the field has a non-empty value AND no error AND debounce settled
 *
 * Caller passes the current raw value and the resolved error (if any).
 */
export function useFieldStatus(opts: {
  value: unknown
  hasError: boolean
  isDirty: boolean
  delay?: number
}): FieldStatus {
  const { value, hasError, isDirty, delay = 250 } = opts
  const debounced = useDebouncedValue(value, delay)

  const isEmpty = value === undefined || value === null || value === '' ||
    (Array.isArray(value) && value.length === 0)

  if (isEmpty && !hasError) return 'idle'
  if (hasError) return 'error'
  if (!isDirty) return 'idle'
  if (value !== debounced) return 'validating'
  return 'valid'
}
