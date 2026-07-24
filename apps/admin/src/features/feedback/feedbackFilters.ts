import type { FeedbackEntry } from './types'

export interface FeedbackClientFilters {
  q?: string
  hasComment?: boolean
  from?: string
  to?: string
}

function timestamp(value: string | undefined): number | null {
  if (!value) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function filterFeedbackItems(
  items: FeedbackEntry[],
  filters: FeedbackClientFilters,
): FeedbackEntry[] {
  const query = filters.q?.trim().toLowerCase() ?? ''
  const from = timestamp(filters.from)
  const to = timestamp(filters.to)

  return items.filter((item) => {
    if (query) {
      const searchable = `${item.query}\n${item.comment ?? ''}`.toLowerCase()
      if (!searchable.includes(query)) return false
    }
    if (filters.hasComment !== undefined && Boolean(item.comment?.trim()) !== filters.hasComment) {
      return false
    }
    const itemTime = timestamp(item.timestamp)
    if (from !== null && (itemTime === null || itemTime < from)) return false
    if (to !== null && (itemTime === null || itemTime > to)) return false
    return true
  })
}
