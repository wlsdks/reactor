/**
 * Lightweight in-memory search index for Command Palette data search.
 *
 * Records are sourced from existing TanStack Query caches via
 * {@link useGlobalSearchRecords}. We do NOT persist anything to IndexedDB —
 * the records live as long as the underlying queries stay in cache.
 *
 * Search algorithm:
 *  - Lowercased substring match against `title` and `haystack`
 *  - Score buckets:
 *      title startsWith query   → +3
 *      title includes query     → +2
 *      haystack includes query  → +1
 *  - Sort by score desc, then alphabetic title asc
 *  - Return top `limit` matches
 *
 * Empty / whitespace-only queries return an empty list (the palette has its
 * own UX for "no query yet").
 */

export type SearchScope = 'release' | 'persona' | 'prompt' | 'feedback' | 'audit' | 'session'

export interface SearchableRecord {
  /** Stable identifier for React keys. Unique within a scope. */
  id: string
  /** Logical bucket — used for the scope chip and i18n label. */
  scope: SearchScope
  /** Primary visible label, shown as the result's main line. */
  title: string
  /** Optional secondary line (dim). */
  subtitle?: string
  /** Optional release workflow step number for release-scoped records. */
  stepNumber?: number
  /** Route path that the palette should navigate to on Enter / click. */
  navigateTo: string
  /**
   * Pre-lowercased searchable blob (title + tags + relevant fields).
   * Callers must lowercase before passing in — `searchRecords` does NOT
   * re-normalise this string for performance.
   */
  haystack: string
}

interface ScoredRecord {
  record: SearchableRecord
  score: number
}

const TITLE_STARTS_WITH = 3
const TITLE_INCLUDES = 2
const HAYSTACK_INCLUDES = 1

/**
 * Score a single record against the (already lowercased) query.
 * Returns 0 when there is no match — caller should drop these.
 */
function scoreRecord(record: SearchableRecord, q: string): number {
  const title = record.title.toLowerCase()
  let score = 0
  if (title.startsWith(q)) {
    score += TITLE_STARTS_WITH
  } else if (title.includes(q)) {
    score += TITLE_INCLUDES
  }
  // haystack already lowercased per the SearchableRecord contract
  if (record.haystack.includes(q)) {
    score += HAYSTACK_INCLUDES
  }
  return score
}

/**
 * Search records for `query` and return the top `limit` matches sorted by
 * score (desc) then title (asc). An empty / whitespace-only query returns an
 * empty array — call sites are expected to short-circuit before invoking
 * this function for the "no query" UX path.
 */
export function searchRecords(
  query: string,
  records: SearchableRecord[],
  limit = 20,
): SearchableRecord[] {
  const trimmed = query.trim().toLowerCase()
  if (!trimmed) return []

  const scored: ScoredRecord[] = []
  for (const record of records) {
    const score = scoreRecord(record, trimmed)
    if (score > 0) {
      scored.push({ record, score })
    }
  }

  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    return a.record.title.localeCompare(b.record.title)
  })

  return scored.slice(0, Math.max(0, limit)).map((s) => s.record)
}
