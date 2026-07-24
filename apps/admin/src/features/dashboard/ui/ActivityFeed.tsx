import { formatDateTime } from '../../../shared/lib/formatters'
import { formatRelativeTimeKo } from '../../../shared/lib/formatRelativeTimeKo'
import { useRelativeTime } from '../../../shared/lib/useRelativeTime'
import { useTranslation } from 'react-i18next'
import { humanizeMetricName } from '../presenters'
import type { OpsMetricSnapshot, DashboardRecentTrustEvent } from '../types'

interface ActivityFeedItem {
  type: 'metric' | 'trust'
  label: string
  value: string | number
  timestamp: number
}

interface ActivityFeedProps {
  metrics: OpsMetricSnapshot[]
  trustEvents: DashboardRecentTrustEvent[]
  generatedAt: number
}

/**
 * Render a relative timestamp that falls back to a compact absolute string for
 * future or >=24h-old events. Wrapping the hook in a child component keeps
 * the parent free of per-row hook calls (rules-of-hooks compliance).
 */
function FeedTimestamp({ timestamp }: { timestamp: number }) {
  const relative = useRelativeTime(timestamp, {
    formatFn: (date) => {
      const diffMs = Date.now() - date.getTime()
      // Future timestamps and anything older than ~24h fall back to the
      // absolute datetime so admins do not see vague "1일 전" labels for
      // events that have a precise wall-clock anchor.
      if (diffMs < 0) return formatDateTime(date.getTime())
      if (diffMs >= 24 * 3_600_000) return formatDateTime(date.getTime())
      return formatRelativeTimeKo(date)
    },
  })
  return <>{relative}</>
}

export function ActivityFeed({ metrics, trustEvents, generatedAt }: ActivityFeedProps) {
  const { t } = useTranslation()
  const metricItems: ActivityFeedItem[] = metrics
    .filter((m) => m.meterCount > 0)
    .map((m) => ({
      type: 'metric' as const,
      label: humanizeMetricName(m.name, t),
      value: m.meterCount,
      timestamp: generatedAt,
    }))

  const trustItems: ActivityFeedItem[] = trustEvents.map((event) => ({
    type: 'trust' as const,
    label: event.type,
    value: event.severity,
    timestamp: event.occurredAt,
  }))

  const items = [...metricItems, ...trustItems]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, 5)

  if (items.length === 0) return null

  return (
    <div className="feed-list">
      {items.map((item, i) => (
        <div key={i} className="feed-item">
          <span
            className="feed-item__dot"
            style={{ background: item.type === 'metric' ? 'var(--green)' : 'var(--blue)' }}
          />
          <div className="feed-item__content">
            <div className="feed-item__label">{item.label}</div>
            <div className="feed-item__meta">
              {String(item.value)} &middot; <FeedTimestamp timestamp={item.timestamp} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
