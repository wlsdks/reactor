import { useEffect, useState } from 'react'

/**
 * useFormDraft
 *
 * Persists form values to localStorage on a debounced cadence so an admin can
 * recover unsaved input after an accidental modal close, refresh, or session
 * timeout. The hook is intentionally caller-driven: it never mutates the
 * react-hook-form state itself — instead, it surfaces the recovered draft and
 * lets the caller decide whether to apply it (`form.reset(draft)`) or discard.
 *
 * Storage layout: every entry lives under the `reactor-admin-draft:` namespace so
 * all drafts are introspectable (and clearable in bulk) via a single prefix
 * filter. Each entry is a JSON envelope `{ values, savedAt }` — the timestamp
 * powers the relative "X minutes ago" hint shown in the recovery banner.
 */

const STORAGE_PREFIX = 'reactor-admin-draft:'

export interface UseFormDraftOptions<T> {
  /** Unique key for this draft, e.g. 'prompt-studio:create' or `personas:edit:${id}`. */
  storageKey: string
  /** Current form values (typically from react-hook-form's `useWatch`). */
  values: T
  /**
   * Whether the draft hook is active. When false the hook is a no-op: it
   * skips reads on mount, cancels any pending debounce write, and never
   * touches localStorage. Use this to gate the hook on modal `open` state.
   */
  enabled?: boolean
  /** Debounce window in milliseconds (default 1500). */
  debounceMs?: number
  /** Custom serializer (default JSON.stringify). */
  serialize?: (v: T) => string
  /** Custom deserializer (default JSON.parse). */
  deserialize?: (s: string) => T
}

export interface FormDraftApi<T> {
  /** Saved draft from localStorage on mount; null if none. */
  recoveredDraft: T | null
  /** ISO timestamp when the recovered draft was last saved. */
  recoveredAt: string | null
  /**
   * Acknowledge that the caller is applying the recovered draft. This does
   * NOT call `form.reset` — the caller wires that itself. It clears the
   * `recoveredDraft` state so the banner unmounts.
   */
  acceptRecovery: () => void
  /** Discard recovered draft (clears localStorage entry + banner state). */
  dismissRecovery: () => void
  /** Manually clear draft (call after a successful save / submit). */
  clearDraft: () => void
  /** True while a write is queued in the debounce window. */
  isDirtyPending: boolean
}

function buildStorageKey(storageKey: string): string {
  return `${STORAGE_PREFIX}${storageKey}`
}

interface DraftEnvelope {
  values: unknown
  savedAt: string
}

function readDraft<T>(
  storageKey: string,
  deserialize: (s: string) => T,
): { values: T; savedAt: string } | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(buildStorageKey(storageKey))
    if (!raw) return null
    // Envelopes are JSON {values, savedAt}; the inner `values` is then handed
    // to the caller's deserializer so custom deserialize() implementations can
    // remain agnostic of the envelope.
    const parsed = JSON.parse(raw) as DraftEnvelope
    if (!parsed || typeof parsed !== 'object' || !('values' in parsed)) return null
    const valuesRaw = JSON.stringify(parsed.values)
    return { values: deserialize(valuesRaw), savedAt: String(parsed.savedAt ?? '') }
  } catch {
    return null
  }
}

function writeDraft<T>(
  storageKey: string,
  values: T,
  serialize: (v: T) => string,
): void {
  if (typeof window === 'undefined') return
  try {
    // Round-trip the serialized payload so the envelope stores the intended
    // shape (e.g. custom serialize() may strip secrets) but JSON.stringify of
    // the full envelope still produces a single contiguous string.
    const serialized = serialize(values)
    const envelope: DraftEnvelope = {
      values: JSON.parse(serialized) as unknown,
      savedAt: new Date().toISOString(),
    }
    window.localStorage.setItem(buildStorageKey(storageKey), JSON.stringify(envelope))
  } catch {
    /* localStorage quota or serialization error — best-effort persistence */
  }
}

function removeDraft(storageKey: string): void {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(buildStorageKey(storageKey))
  } catch {
    /* noop */
  }
}

const defaultSerialize = <T,>(v: T): string => JSON.stringify(v)
const defaultDeserialize = <T,>(s: string): T => JSON.parse(s) as T

export function useFormDraft<T>(options: UseFormDraftOptions<T>): FormDraftApi<T> {
  const {
    storageKey,
    values,
    enabled = true,
    debounceMs = 1500,
    serialize = defaultSerialize,
    deserialize = defaultDeserialize,
  } = options

  const [recoveredDraft, setRecoveredDraft] = useState<T | null>(() => {
    if (!enabled) return null
    const found = readDraft<T>(storageKey, deserialize)
    return found ? found.values : null
  })
  const [recoveredAt, setRecoveredAt] = useState<string | null>(() => {
    if (!enabled) return null
    const found = readDraft<T>(storageKey, deserialize)
    return found ? found.savedAt : null
  })

  // Track the storage key we last read from; when it changes (e.g. re-opening
  // the modal for a different record id) refresh `recoveredDraft` *during
  // render* per the React docs' "storing information from previous renders"
  // pattern. This avoids both setState-in-effect lint warnings and the extra
  // render that an effect-based refresh would cost.
  const [lastReadKey, setLastReadKey] = useState<string | null>(enabled ? storageKey : null)
  if (enabled && lastReadKey !== storageKey) {
    setLastReadKey(storageKey)
    const found = readDraft<T>(storageKey, deserialize)
    setRecoveredDraft(found ? found.values : null)
    setRecoveredAt(found ? found.savedAt : null)
  } else if (!enabled && lastReadKey !== null) {
    setLastReadKey(null)
  }

  // Compute the canonical change signal — comparing the JSON projection (not
  // object identity) lets callers pass new object literals on every render
  // (common with `useWatch()`) without triggering a write storm.
  let serializedValues: string
  try {
    serializedValues = serialize(values)
  } catch {
    serializedValues = ''
  }

  // Track the last value that was actually persisted; the difference between
  // it and `serializedValues` is the dirty signal. Persisted state lives in
  // useState (not a ref) so it can be read safely during render.
  const [persistedSerialized, setPersistedSerialized] = useState<string | null>(null)
  const isDirtyPending = enabled && persistedSerialized !== serializedValues

  // Debounced write effect: re-runs whenever the *serialized* form of values
  // changes. Cleanup cancels the pending write so rapid edits coalesce into a
  // single localStorage hit.
  useEffect(() => {
    if (!enabled) return
    if (persistedSerialized === serializedValues) return
    const timer = window.setTimeout(() => {
      writeDraft(storageKey, values, serialize)
      setPersistedSerialized(serializedValues)
    }, debounceMs)
    return () => {
      window.clearTimeout(timer)
    }
    // `values` is intentionally omitted from deps: `serializedValues` is the
    // canonical change signal.
  }, [serializedValues, storageKey, enabled, debounceMs, serialize, persistedSerialized])

  function acceptRecovery(): void {
    setRecoveredDraft(null)
    setRecoveredAt(null)
  }

  function dismissRecovery(): void {
    removeDraft(storageKey)
    setRecoveredDraft(null)
    setRecoveredAt(null)
  }

  function clearDraft(): void {
    removeDraft(storageKey)
    setRecoveredDraft(null)
    setRecoveredAt(null)
    // Mark current values as "persisted" (== empty string fallback) so the
    // dirty flag clears immediately. The next caller-driven edit re-arms the
    // debounced write.
    setPersistedSerialized(serializedValues)
  }

  return {
    recoveredDraft,
    recoveredAt,
    acceptRecovery,
    dismissRecovery,
    clearDraft,
    isDirtyPending,
  }
}
