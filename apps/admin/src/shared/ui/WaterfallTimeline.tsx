import { useTranslation } from 'react-i18next'

export interface WaterfallSpan {
  id: string
  parentId: string | null
  name: string
  type: 'request' | 'input_guard' | 'llm_call' | 'tool_call' | 'output_guard'
  startMs: number
  durationMs: number
  status: 'ok' | 'error' | 'blocked'
  detail?: Record<string, unknown>
}

interface WaterfallTimelineProps {
  spans: WaterfallSpan[]
  totalDurationMs: number
  selectedSpanId?: string | null
  onSpanClick?: (span: WaterfallSpan) => void
}

function buildTree(spans: WaterfallSpan[]): Map<string | null, WaterfallSpan[]> {
  const childrenMap = new Map<string | null, WaterfallSpan[]>()
  for (const span of spans) {
    const existing = childrenMap.get(span.parentId) ?? []
    existing.push(span)
    childrenMap.set(span.parentId, existing)
  }
  return childrenMap
}

function flattenWithDepth(
  childrenMap: Map<string | null, WaterfallSpan[]>,
  parentId: string | null,
  depth: number,
): Array<{ span: WaterfallSpan; depth: number }> {
  const children = childrenMap.get(parentId) ?? []
  const result: Array<{ span: WaterfallSpan; depth: number }> = []
  for (const child of children) {
    result.push({ span: child, depth })
    result.push(...flattenWithDepth(childrenMap, child.id, depth + 1))
  }
  return result
}

function formatDuration(ms: number): string {
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}

export function WaterfallTimeline({
  spans,
  totalDurationMs,
  selectedSpanId,
  onSpanClick,
}: WaterfallTimelineProps) {
  const { t } = useTranslation()
  const childrenMap = buildTree(spans)
  const flatSpans = flattenWithDepth(childrenMap, null, 0)
  const safeTotalMs = Math.max(totalDurationMs, 1)

  return (
    <div className="waterfall-timeline" role="list" aria-label={t('traces.aria.timeline')}>
      {flatSpans.map(({ span, depth }) => {
        const leftPercent = (span.startMs / safeTotalMs) * 100
        const widthPercent = Math.max((span.durationMs / safeTotalMs) * 100, 0.5)
        const isSelected = selectedSpanId === span.id
        const isError = span.status === 'error' || span.status === 'blocked'

        return (
          <div
            key={span.id}
            className={`waterfall-row ${isSelected ? 'waterfall-row--selected' : ''} ${isError ? 'waterfall-row--error' : ''}`}
            role="listitem"
            onClick={onSpanClick ? () => onSpanClick(span) : undefined}
            onKeyDown={onSpanClick ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onSpanClick(span)
              }
            } : undefined}
            tabIndex={onSpanClick ? 0 : undefined}
            aria-label={`${span.name} ${formatDuration(span.durationMs)} ${span.status}`}
          >
            <div
              className="waterfall-name"
              style={{ paddingLeft: `${depth * 16}px` }}
            >
              <span className="waterfall-name-text">{span.name}</span>
            </div>
            <div className="waterfall-bar-area">
              <div
                className={`waterfall-bar ${isSelected ? 'waterfall-bar--selected' : ''}`}
                style={{
                  left: `${leftPercent}%`,
                  width: `${widthPercent}%`,
                  minWidth: '4px',
                }}
              />
              <span className="waterfall-duration">
                {formatDuration(span.durationMs)}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
