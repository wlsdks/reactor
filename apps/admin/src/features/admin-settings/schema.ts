import { z } from 'zod/v4'
import i18n from 'i18next'

function maxMsg(max: number): string {
  return i18n.t('common.validation.maxLength', { max })
}

export const settingEditSchema = z.object({
  value: z.string().min(1, i18n.t('common.validation.required')).max(50000, maxMsg(50000)),
})

export type SettingEditFormValues = z.infer<typeof settingEditSchema>

/**
 * Typed value kinds supported by the edit modal. These describe how the raw
 * value string is interpreted for display and how it is serialized before
 * being POSTed to the backend.
 */
export const valueTypeKinds = ['string', 'number', 'boolean', 'object', 'array'] as const
export type ValueTypeKind = (typeof valueTypeKinds)[number]

/**
 * Heuristic mapping of known key-name patterns to a default type. Used to
 * pre-select the Type dropdown when opening the edit modal on a setting
 * whose stored value does not unambiguously reveal its intended type
 * (for example, SECRETs or empty strings).
 */
export function inferTypeFromKey(key: string): ValueTypeKind | null {
  const k = key.toLowerCase()
  // Matches *.enabled, *.disabled, is*, has*, *.flag
  if (/\.(enabled|disabled|active|flag)$/.test(k)) return 'boolean'
  if (/^(is|has|should|allow|deny)[_.-]?[a-z]/.test(k)) return 'boolean'
  // Numeric counters, limits, timeouts, order, ports
  if (/\.(order|count|limit|max|min|port|timeout|ttl|size|priority)$/.test(k)) return 'number'
  if (/requestspersecond|requestsperminute|requestsperhour/.test(k)) return 'number'
  if (/\.(interval|delay|duration|threshold|retries|retry)$/.test(k)) return 'number'
  return null
}

/**
 * Infer a value kind from the already-persisted raw string. This is best
 * effort — strings that happen to parse as JSON numbers or booleans are
 * treated as that type.
 */
export function inferTypeFromValue(raw: string): ValueTypeKind {
  if (raw == null) return 'string'
  const trimmed = raw.trim()
  if (trimmed === 'true' || trimmed === 'false') return 'boolean'
  if (trimmed !== '' && !Number.isNaN(Number(trimmed)) && /^-?\d+(\.\d+)?$/.test(trimmed)) return 'number'
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed: unknown = JSON.parse(trimmed)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return 'object'
    } catch {
      /* fallthrough */
    }
  }
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    try {
      const parsed: unknown = JSON.parse(trimmed)
      if (Array.isArray(parsed)) return 'array'
    } catch {
      /* fallthrough */
    }
  }
  return 'string'
}

export interface JsonValidationResult {
  valid: boolean
  /** Human-readable parse error (used as tooltip under the textarea). */
  error?: string
}

/**
 * Live JSON validation used for the object/array textarea modes. Returns
 * `valid: false` with a parse-error message when JSON.parse throws, or when
 * the parsed shape does not match the expected kind.
 */
export function validateJson(raw: string, kind: 'object' | 'array'): JsonValidationResult {
  const trimmed = raw.trim()
  if (trimmed === '') return { valid: false, error: i18n.t('common.validation.required') }
  try {
    const parsed: unknown = JSON.parse(trimmed)
    if (kind === 'object') {
      if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return { valid: false, error: i18n.t('adminSettingsTab.validation.expectedJsonObject') }
      }
    } else if (!Array.isArray(parsed)) {
      return { valid: false, error: i18n.t('adminSettingsTab.validation.expectedJsonArray') }
    }
    return { valid: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : i18n.t('adminSettingsTab.validation.invalidJson')
    return { valid: false, error: message }
  }
}

/**
 * Serialize a raw value string into its canonical storage form before the
 * PUT call. String values pass through unchanged; number/boolean are
 * normalized; object/array are validated and re-stringified to strip
 * incidental whitespace.
 */
export function serializeValue(raw: string, kind: ValueTypeKind): string {
  switch (kind) {
    case 'string':
      return raw
    case 'number':
      return String(Number(raw))
    case 'boolean':
      return raw === 'true' ? 'true' : 'false'
    case 'object':
    case 'array': {
      const parsed: unknown = JSON.parse(raw)
      return JSON.stringify(parsed)
    }
  }
}
