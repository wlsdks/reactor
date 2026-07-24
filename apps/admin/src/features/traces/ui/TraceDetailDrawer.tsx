import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { SideDrawer, SkeletonCard, SkeletonText } from '../../../shared/ui'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { formatDuration } from '../../../shared/lib/formatters'
import { getTraceSpans } from '../api'
import type { TraceSpan } from '../types'
import { SpanDetail } from './SpanDetail'
import { SpanTree } from './SpanTree'

interface TraceDetailDrawerProps {
  traceId: string | null
  open: boolean
  onClose: () => void
}

export function TraceDetailDrawer({ traceId, open, onClose }: TraceDetailDrawerProps) {
  const { t } = useTranslation()
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  const { data: spans = [], isLoading } = useQuery({
    queryKey: queryKeys.traces.detail(traceId ?? ''),
    queryFn: () => getTraceSpans(traceId!),
    enabled: !!traceId && open,
  })

  const selectedSpan = spans.find((s) => s.spanId === selectedSpanId) ?? null

  // Wall-clock duration of the trace — the time between the earliest span start
  // and the latest span end. Using max(durationMs) alone would understate the
  // total when spans run sequentially.
  const minTime = spans.length > 0 ? Math.min(...spans.map((s) => s.time)) : 0
  const maxEnd = spans.length > 0
    ? Math.max(...spans.map((s) => s.time + s.durationMs))
    : 0
  const totalDurationMs = Math.max(0, maxEnd - minTime)

  const handleTreeSelect = (span: TraceSpan | null) => {
    setSelectedSpanId(span ? span.spanId : null)
  }

  const operatorTraceId = traceId
    ? `#${traceId.replace(/^run[_-]?/i, '').slice(0, 8).toUpperCase()}`
    : '-'

  return (
    <SideDrawer
      open={open}
      title={t('tracesPage.drawer.title')}
      onClose={onClose}
      size="wide"
    >
      {isLoading ? (
        // Drawer placeholder roughly matches: summary block + waterfall timeline
        // + span tree. Reduces apparent latency when opening a trace.
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <SkeletonText lines={3} lastLineWidth="60%" />
          <SkeletonCard height={120} />
          <SkeletonCard height={220} />
        </div>
      ) : (
        <div className="trace-detail-layout">
          <div className="trace-detail">
            <section id="trace-section-summary" className="trace-detail-summary">
              <h4 className="trace-detail-section-title">{t('tracesPage.drawer.summary')}</h4>
              <div className="trace-detail-grid">
                <div className="trace-detail-field">
                  <span className="trace-detail-label">{t('tracesPage.drawer.traceId')}</span>
                  <span className="trace-detail-value mono" title={traceId ?? undefined} aria-label={traceId ?? undefined}>
                    {operatorTraceId}
                  </span>
                </div>
                <div className="trace-detail-field">
                  <span className="trace-detail-label">{t('tracesPage.drawer.spanCount')}</span>
                  <span className="trace-detail-value">{t('tracesPage.stepCount', { count: spans.length })}</span>
                </div>
                <div className="trace-detail-field">
                  <span className="trace-detail-label">{t('tracesPage.drawer.duration')}</span>
                  <span className="trace-detail-value mono">{formatDuration(totalDurationMs)}</span>
                </div>
              </div>
            </section>

            <section id="trace-section-tree" className="trace-detail-tree">
              <h4 className="trace-detail-section-title">{t('tracesPage.drawer.spanTree')}</h4>
              <SpanTree
                spans={spans}
                totalDurationMs={totalDurationMs}
                traceStartTime={minTime}
                selectedSpanId={selectedSpanId}
                onSelectSpan={handleTreeSelect}
              />
            </section>

            {selectedSpan && (
              <section id="trace-section-span" className="trace-detail-span">
                <SpanDetail span={selectedSpan} />
              </section>
            )}
          </div>
        </div>
      )}
    </SideDrawer>
  )
}
