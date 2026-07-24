/**
 * Recursively converts all object keys from snake_case to camelCase.
 * Arrays are traversed element-by-element; primitives pass through unchanged.
 */
export function snakeToCamel(obj: unknown): unknown {
  if (Array.isArray(obj)) return obj.map(snakeToCamel)
  if (obj !== null && typeof obj === 'object') {
    return Object.fromEntries(
      Object.entries(obj as Record<string, unknown>).map(([key, val]) => [
        key.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase()),
        snakeToCamel(val),
      ]),
    )
  }
  return obj
}
