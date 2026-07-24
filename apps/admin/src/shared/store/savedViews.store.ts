import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

/**
 * Per-scope shareable filter view.
 *
 * `scope` matches a DataTable `urlStateKey` (or any caller-defined identifier)
 * so filter snapshots stay local to the table that produced them. `params` is
 * a plain `Record<string, string>` snapshot of the URL search params slice
 * relevant to that scope — applied via `setSearchParams` when the user
 * recalls the view.
 */
export interface SavedView {
  /** Stable id; generated with `crypto.randomUUID()` on creation. */
  id: string
  /** Scope identifier (typically the DataTable `urlStateKey`). */
  scope: string
  /** User-typed view name. */
  name: string
  /** URL search params snapshot (key → string) for the scope. */
  params: Record<string, string>
  /** ISO-8601 creation timestamp. */
  createdAt: string
}

interface SavedViewsState {
  /** All saved views across all scopes. Filtered at read time via `list()`. */
  views: SavedView[]
  /** Persist a new view for the given scope and return the created entry. */
  add: (scope: string, name: string, params: Record<string, string>) => SavedView
  /** Remove a view by id (no-op if missing). */
  remove: (id: string) => void
  /** Rename a view by id (no-op if missing). */
  rename: (id: string, name: string) => void
  /** Read all views for the given scope, in insertion order. */
  list: (scope: string) => SavedView[]
}

const STORAGE_KEY = 'reactor-admin-saved-views'

/**
 * Generate a UUID. Uses the standard `crypto.randomUUID` when available and
 * falls back to a Math.random-based generator for older runtimes (jsdom in
 * some test environments). The fallback is collision-resistant enough for
 * client-side IDs that never leave the browser.
 */
function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  // RFC4122-ish v4 fallback.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export const useSavedViewsStore = create<SavedViewsState>()(
  persist(
    (set, get) => ({
      views: [],
      add: (scope, name, params) => {
        const trimmed = name.trim()
        const view: SavedView = {
          id: generateId(),
          scope,
          name: trimmed,
          // Defensive copy so mutations to the caller-supplied object never
          // bleed into stored state.
          params: { ...params },
          createdAt: new Date().toISOString(),
        }
        set((state) => ({ views: [...state.views, view] }))
        return view
      },
      remove: (id) => {
        set((state) => ({ views: state.views.filter((v) => v.id !== id) }))
      },
      rename: (id, name) => {
        const trimmed = name.trim()
        if (!trimmed) return
        set((state) => ({
          views: state.views.map((v) => (v.id === id ? { ...v, name: trimmed } : v)),
        }))
      },
      list: (scope) => get().views.filter((v) => v.scope === scope),
    }),
    {
      name: STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
      // Only persist the views array — methods are reconstructed on load.
      partialize: (state) => ({ views: state.views }),
      version: 1,
    },
  ),
)

/**
 * Storage key used for persistence; exported for tests and tooling that need
 * to clear or seed the bucket directly.
 */
export const SAVED_VIEWS_STORAGE_KEY = STORAGE_KEY
