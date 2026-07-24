import { useSearchParams } from 'react-router-dom'

/**
 * Allowed value types for URL-synced state. Strings round-trip directly;
 * numeric values are coerced via `Number(...)` on read. `undefined` slots are
 * treated as "no default" (the param is removed unless explicitly set).
 */
export type UrlStatePrimitive = string | number | undefined

export interface UseUrlStateOptions {
  /**
   * Optional namespace prefix for param keys. A prefix `audit` turns a logical
   * key `page` into the URL param `audit_page`, allowing multiple sibling
   * tables on the same route to coexist without colliding.
   */
  prefix?: string
  /**
   * When true (the default), updates use `replace: true` so that filter /
   * pagination changes do not pollute the browser history stack. Set to
   * `false` to preserve a back-button entry per change.
   */
  replace?: boolean
}

/**
 * Sync a small Record-shaped state container with URL search params.
 *
 * Behaviour:
 *  - Reads each key from `useSearchParams`, falling back to `defaults[key]`.
 *  - Numeric defaults trigger `Number(...)` coercion on read; non-finite
 *    values fall back to the default.
 *  - Writes go through `setSearchParams(..., { replace })`.
 *  - Setting a value equal to its default removes the param from the URL,
 *    keeping shareable links clean.
 *  - An optional `prefix` namespaces every param key as `${prefix}_${key}`.
 *
 * The returned setter accepts a partial patch; only provided keys are
 * touched, mirroring `useState`'s setter ergonomics for object slices.
 */
export function useUrlState<T extends Record<string, UrlStatePrimitive>>(
  defaults: T,
  options: UseUrlStateOptions = {},
): [T, (next: Partial<T>) => void] {
  const { prefix, replace = true } = options
  const [searchParams, setSearchParams] = useSearchParams()

  const namespacedKey = (key: string): string =>
    prefix ? `${prefix}_${key}` : key

  // Read current values. Each key falls back to its default when the URL
  // omits it, when coercion fails, or when the raw string is empty.
  const value: T = {} as T
  for (const key of Object.keys(defaults) as Array<keyof T>) {
    const defaultValue = defaults[key]
    const raw = searchParams.get(namespacedKey(String(key)))
    if (raw == null || raw === '') {
      value[key] = defaultValue
      continue
    }
    if (typeof defaultValue === 'number') {
      const parsed = Number(raw)
      value[key] = (Number.isFinite(parsed) ? parsed : defaultValue) as T[keyof T]
    } else {
      // String slot (default may be `undefined`); store the raw value.
      value[key] = raw as T[keyof T]
    }
  }

  function setValue(patch: Partial<T>): void {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const key of Object.keys(patch) as Array<keyof T>) {
          const incoming = patch[key]
          const defaultValue = defaults[key]
          const paramKey = namespacedKey(String(key))
          // Treat undefined or "default" values as URL-clear so links stay
          // tidy and bookmarked URLs only encode meaningful state.
          const isDefault =
            incoming === undefined ||
            incoming === defaultValue ||
            (typeof defaultValue === 'number' && Number(incoming) === defaultValue)
          if (isDefault) {
            next.delete(paramKey)
          } else {
            next.set(paramKey, String(incoming))
          }
        }
        return next
      },
      { replace },
    )
  }

  return [value, setValue]
}

/**
 * Read a snapshot of every URL search param whose key starts with
 * `${prefix}_`. Used by `SavedViewsControl` to build a per-scope params
 * object that can later be re-applied via `applyScopedParams`.
 *
 * Returns a plain `Record<string, string>` containing the *raw* keys (still
 * prefixed) so the snapshot can round-trip through `URLSearchParams.set` /
 * `URLSearchParams.get` without further translation.
 */
export function extractScopedParams(
  searchParams: URLSearchParams,
  prefix: string,
): Record<string, string> {
  const result: Record<string, string> = {}
  const pfx = `${prefix}_`
  for (const [key, value] of searchParams.entries()) {
    if (key.startsWith(pfx)) {
      result[key] = value
    }
  }
  return result
}

/**
 * Replace every `${prefix}_*` key in `existing` with the entries from
 * `incoming`. Other params (including those owned by sibling tables on the
 * same page) are left untouched so applying a saved view scoped to one
 * table does not clobber another's pagination.
 *
 * Returns a fresh `URLSearchParams` so callers can hand it directly to
 * `setSearchParams`.
 */
export function applyScopedParams(
  existing: URLSearchParams,
  prefix: string,
  incoming: Record<string, string>,
): URLSearchParams {
  const next = new URLSearchParams(existing)
  const pfx = `${prefix}_`
  // Drop any current scoped entries first so the snapshot fully replaces
  // them (including keys present in the URL but absent from `incoming`).
  for (const key of Array.from(next.keys())) {
    if (key.startsWith(pfx)) next.delete(key)
  }
  for (const [key, value] of Object.entries(incoming)) {
    next.set(key, value)
  }
  return next
}
