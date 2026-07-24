/**
 * Token in the page range list. A numeric value renders as a clickable page
 * button; the literal `'ellipsis'` renders as a non-clickable gap indicator.
 */
export type PageRangeItem = number | 'ellipsis'

/**
 * Compute a page-button row centered on `current`, returning at most `window`
 * tokens (default 7). Always includes page 1 and the last page; inserts an
 * 'ellipsis' marker between non-adjacent shown pages.
 *
 * Token budget (window=7):
 *   - total ≤ window                       → every page, no ellipsis
 *   - One trailing ellipsis (near start)   → 5 numerics + ellipsis + last
 *   - One leading  ellipsis (near end)     → first + ellipsis + 5 numerics
 *   - Both ellipses (middle)               → first + ellipsis + 3 numerics + ellipsis + last
 *
 * Examples (window=7):
 *   total=5,  current=3  → [1, 2, 3, 4, 5]
 *   total=99, current=1  → [1, 2, 3, 4, 5, 'ellipsis', 99]
 *   total=99, current=50 → [1, 'ellipsis', 49, 50, 51, 'ellipsis', 99]
 *   total=99, current=99 → [1, 'ellipsis', 95, 96, 97, 98, 99]
 */
export function pageRange(
  current: number,
  total: number,
  window = 7,
): PageRangeItem[] {
  if (total <= 0) return []
  if (total <= window) {
    return Array.from({ length: total }, (_, i) => i + 1)
  }
  const clamped = Math.min(total, Math.max(1, current))
  // The "edge zone" is the segment near each anchor in which a single ellipsis
  // suffices on the opposite side. For window=7 this is the first/last 4 pages
  // (1..4 and total-3..total): a 5-page run + ellipsis + opposite anchor = 7.
  const edgeZone = window - 3

  // Near the start: pages 1..(edgeZone+1) get the [1..N, …, last] layout.
  if (clamped <= edgeZone + 1) {
    const out: PageRangeItem[] = []
    for (let p = 1; p <= edgeZone + 1; p++) out.push(p)
    out.push('ellipsis')
    out.push(total)
    return out
  }

  // Near the end: symmetric.
  if (clamped >= total - edgeZone) {
    const out: PageRangeItem[] = [1, 'ellipsis']
    for (let p = total - edgeZone; p <= total; p++) out.push(p)
    return out
  }

  // Middle: [first, ellipsis, current-N..current+N, ellipsis, last].
  // Adapts to larger windows by widening the inner span symmetrically.
  const innerHalf = Math.floor((window - 4) / 2) // = 1 when window=7
  const out: PageRangeItem[] = [1, 'ellipsis']
  for (let p = clamped - innerHalf; p <= clamped + innerHalf; p++) out.push(p)
  out.push('ellipsis')
  out.push(total)
  return out
}
