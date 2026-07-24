/**
 * Safe localStorage wrapper.
 *
 * Centralises three concerns that were previously scattered across ~11 call
 * sites:
 *   1. SSR / non-browser guard (`typeof window === 'undefined'`).
 *   2. `try/catch` around every read/write (Safari private mode, disabled
 *      cookies, quota errors).
 *   3. JSON parse/serialise with a sane fallback when the stored payload is
 *      malformed (e.g. partially-written value, schema migration).
 *
 * All keys live under {@link STORAGE_KEYS} so the catalogue of persisted UI
 * state is discoverable in one place. New entries should be added there
 * rather than declared inline at the call site.
 */

/**
 * Common prefix for keys owned by this admin app. Older keys without this
 * prefix (e.g. `mcp-server-tags`) are kept verbatim in {@link STORAGE_KEYS}
 * for backwards compatibility — renaming them would orphan existing user
 * preferences.
 */
export const STORAGE_PREFIX = 'reactor-admin-'

/**
 * Centralised catalogue of every localStorage key the app reads or writes.
 *
 * Adding a new persisted key? Add it here first, then reference it via
 * `STORAGE_KEYS.<name>` in the call site. This keeps the surface auditable
 * and prevents collisions / typos.
 *
 * Note: keys are intentionally heterogeneous in prefix because some predate
 * the `reactor-admin-` convention. Migrating them in place would erase
 * users' saved preferences, so we accept the inconsistency in exchange for
 * upgrade safety.
 */
export const STORAGE_KEYS = {
  /** JWT bearer token (managed by `shared/api/client.ts`). */
  authToken: `${STORAGE_PREFIX}token`,
  /** Cached user record placeholder (cleared on logout). */
  authUser: `${STORAGE_PREFIX}user`,
  /** ADMIN-only "View as Manager" preview toggle. */
  viewAs: 'reactor-admin-view-as',
  /** Sidebar collapsed state (current). */
  sidebarCollapsed: 'reactor-admin-sidebar-collapsed',
  /** Sidebar collapsed state (legacy, one-way migrated). */
  sidebarCollapsedLegacy: 'reactor-sidebar-collapsed',
  /** Per-group collapsed state in the sidenav. */
  sidenavCollapsedGroups: 'reactor-admin-sidenav-collapsed-groups',
  /** Saved DataTable filter views (Zustand persist middleware key). */
  savedViews: 'reactor-admin-saved-views',
  /** Issues page topology view ('graph' | 'list'). */
  issuesView: 'reactor-admin-issues-view',
  /** Quick-search history on the RAG cache page. */
  ragSearchHistory: `${STORAGE_PREFIX}rag-search-history`,
  /** MCP server tag map (server name → tag list). */
  mcpServerTags: 'mcp-server-tags',
  /** i18n language preference (currently only ever removed). */
  langLegacy: 'reactor-admin-lang',
} as const

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS]

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

/**
 * Read a raw string value. Returns `defaultValue` (or `null` if omitted) when
 * the key is missing, the storage API is unavailable, or any access error
 * occurs.
 */
export function safeGet(key: string, defaultValue: string | null = null): string | null {
  if (!isBrowser()) return defaultValue
  try {
    const value = window.localStorage.getItem(key)
    return value === null ? defaultValue : value
  } catch {
    return defaultValue
  }
}

/**
 * Read and JSON-parse a value. Returns `defaultValue` (or `null` if omitted)
 * when the key is missing, parsing fails, or the storage API is unavailable.
 *
 * The `T` generic is *unchecked* — callers should validate the parsed shape
 * before trusting it (e.g. via a Zod schema or an `Array.isArray` guard).
 */
export function safeGetJson<T>(key: string, defaultValue: T | null = null): T | null {
  if (!isBrowser()) return defaultValue
  try {
    const raw = window.localStorage.getItem(key)
    if (raw === null) return defaultValue
    return JSON.parse(raw) as T
  } catch {
    return defaultValue
  }
}

/**
 * Write a raw string value. Returns `true` on success, `false` if the storage
 * API is unavailable or the write was rejected (most commonly
 * `QuotaExceededError`). A quota error is logged once via `console.warn` so
 * the operator can investigate without crashing the UI.
 */
export function safeSet(key: string, value: string): boolean {
  if (!isBrowser()) return false
  try {
    window.localStorage.setItem(key, value)
    return true
  } catch (err) {
    if (err instanceof DOMException && err.name === 'QuotaExceededError') {
      console.warn(`[safeLocalStorage] quota exceeded for "${key}"`)
    }
    return false
  }
}

/**
 * JSON-serialise and write a value. Returns `false` if serialisation fails
 * (e.g. circular structure) or the underlying write is rejected.
 */
export function safeSetJson<T>(key: string, value: T): boolean {
  if (!isBrowser()) return false
  try {
    return safeSet(key, JSON.stringify(value))
  } catch {
    return false
  }
}

/**
 * Remove a key. Silently no-ops if storage is unavailable.
 */
export function safeRemove(key: string): void {
  if (!isBrowser()) return
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* noop — storage unavailable */
  }
}
