import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { formatDuration } from '../../../shared/lib/formatters'
import { Tooltip } from '../../../shared/ui'
import type { TraceSpan } from '../types'
import {
  deriveSpanKind,
  localizeKnownSecondaryLabel,
  localizeSpanError,
  localizeSpanKind,
} from './spanLabels'

/** Return a non-empty string value from an attribute record, or null. */
function pickString(data: Record<string, unknown>, key: string): string | null {
  const v = data[key]
  if (typeof v === 'string') return v.length > 0 ? v : null
  if (typeof v === 'number') return String(v)
  return null
}

interface SpanTreeProps {
  spans: TraceSpan[]
  /** Total wall-clock duration of the trace, used for the inline proportional bar. */
  totalDurationMs: number
  /** Earliest span start time used to compute the start offset shown on each row. */
  traceStartTime: number
  selectedSpanId?: string | null
  onSelectSpan?: (span: TraceSpan | null) => void
}

interface FlatNode {
  span: TraceSpan
  depth: number
  /** Number of direct children this span has. */
  childCount: number
  /** Whether this row is visible (all ancestors expanded). */
  visible: boolean
}

function buildChildrenMap(spans: TraceSpan[]): Map<string | null, TraceSpan[]> {
  const map = new Map<string | null, TraceSpan[]>()
  const ids = new Set(spans.map((s) => s.spanId))
  for (const span of spans) {
    // Treat parent ids that do not exist in the set as roots so orphaned
    // spans are still rendered instead of silently disappearing.
    const parent = span.parentSpanId && ids.has(span.parentSpanId) ? span.parentSpanId : null
    const existing = map.get(parent) ?? []
    existing.push(span)
    map.set(parent, existing)
  }
  // Stable ordering: earliest start first, falling back to spanId.
  for (const [key, arr] of map.entries()) {
    arr.sort((a, b) => (a.time - b.time) || a.spanId.localeCompare(b.spanId))
    map.set(key, arr)
  }
  return map
}

/**
 * Depth-first flatten honouring the collapsed set. Children of a collapsed
 * node are still included in the flat list (so keyboard ArrowRight can expand
 * without rebuilding), but carry `visible: false`.
 */
function flatten(
  childrenMap: Map<string | null, TraceSpan[]>,
  collapsed: Set<string>,
): FlatNode[] {
  const out: FlatNode[] = []
  const walk = (parentId: string | null, depth: number, parentVisible: boolean) => {
    const children = childrenMap.get(parentId) ?? []
    for (const child of children) {
      const childCount = (childrenMap.get(child.spanId) ?? []).length
      out.push({ span: child, depth, childCount, visible: parentVisible })
      const isCollapsed = collapsed.has(child.spanId)
      // Descendants are only visible if the current node is both visible
      // and not collapsed.
      walk(child.spanId, depth + 1, parentVisible && !isCollapsed)
    }
  }
  walk(null, 0, true)
  return out
}

function errorMessageFrom(span: TraceSpan): string | null {
  const fromAttrs = pickString(span.attributes, 'error') ?? pickString(span.attributes, 'errorMessage')
  if (fromAttrs) return fromAttrs
  if (span.errorClass) return span.errorClass
  return null
}

function stackTraceFrom(span: TraceSpan): string | null {
  return pickString(span.attributes, 'stack') ?? pickString(span.attributes, 'stackTrace')
}

export function SpanTree({
  spans,
  totalDurationMs,
  traceStartTime,
  selectedSpanId,
  onSelectSpan,
}: SpanTreeProps) {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set())
  const [focusIndex, setFocusIndex] = useState(0)

  const childrenMap = buildChildrenMap(spans)
  const flat = flatten(childrenMap, collapsed)
  const visibleRows = flat.filter((node) => node.visible)
  const safeTotal = Math.max(totalDurationMs, 1)
  // Clamp focusIndex during render so it never points past the visible rows
  // after a collapse hides descendants. This avoids the cascading-render
  // smell of calling setState inside a useEffect just to clamp.
  const effectiveFocusIndex = visibleRows.length === 0
    ? 0
    : Math.min(focusIndex, visibleRows.length - 1)

  // Empty state
  if (spans.length === 0) {
    return (
      <div className="span-tree span-tree--empty" data-testid="span-tree-empty">
        <p className="span-tree-empty-message">{t('tracesPage.drawer.noSpanData')}</p>
        <p className="span-tree-empty-hint">{t('tracesPage.drawer.noSpanDataHint')}</p>
      </div>
    )
  }

  const toggleCollapse = (spanId: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(spanId)) next.delete(spanId)
      else next.add(spanId)
      return next
    })
  }

  const expand = (spanId: string) => {
    setCollapsed((prev) => {
      if (!prev.has(spanId)) return prev
      const next = new Set(prev)
      next.delete(spanId)
      return next
    })
  }

  const collapse = (spanId: string) => {
    setCollapsed((prev) => {
      if (prev.has(spanId)) return prev
      const next = new Set(prev)
      next.add(spanId)
      return next
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (visibleRows.length === 0) return
    const current = visibleRows[effectiveFocusIndex]
    if (!current) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = Math.min(effectiveFocusIndex + 1, visibleRows.length - 1)
      setFocusIndex(next)
      onSelectSpan?.(visibleRows[next].span)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.max(effectiveFocusIndex - 1, 0)
      setFocusIndex(next)
      onSelectSpan?.(visibleRows[next].span)
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      if (current.childCount > 0 && collapsed.has(current.span.spanId)) {
        expand(current.span.spanId)
      }
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      if (current.childCount > 0 && !collapsed.has(current.span.spanId)) {
        collapse(current.span.spanId)
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelectSpan?.(current.span)
    }
  }

  const handleRowClick = (node: FlatNode, idx: number) => {
    setFocusIndex(idx)
    onSelectSpan?.(node.span)
  }

  return (
    <div
      className="span-tree"
      role="tree"
      aria-label={t('tracesPage.drawer.spanTreeAria')}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      data-testid="span-tree"
    >
      {visibleRows.map((node, idx) => {
        const { span, depth, childCount } = node
        const isCollapsed = collapsed.has(span.spanId)
        const isFocused = idx === effectiveFocusIndex
        const isSelected = selectedSpanId === span.spanId
        const isError = !span.success || !!span.errorClass
        const startOffset = Math.max(0, span.time - traceStartTime)
        const widthPercent = Math.min(100, Math.max((span.durationMs / safeTotal) * 100, 0.5))
        const leftPercent = Math.min(100 - widthPercent, (startOffset / safeTotal) * 100)
        const errorMessage = isError ? errorMessageFrom(span) : null
        const stack = isError ? stackTraceFrom(span) : null
        const spanKind = deriveSpanKind(span.operationName)
        const secondaryValue = spanKind === 'tool_call'
          ? pickString(span.attributes, 'toolName')
          : spanKind === 'llm_call'
            ? pickString(span.attributes, 'model')
            : null
        const extraLabel = localizeKnownSecondaryLabel(t, spanKind, secondaryValue)
        const localizedError = isError ? localizeSpanError(t, span.errorClass ?? errorMessage) : null

        return (
          <div
            key={span.spanId}
            className={[
              'span-tree-node',
              isError ? 'span-tree-node--error' : '',
              isFocused ? 'span-tree-node--focused' : '',
              isSelected ? 'span-tree-node--selected' : '',
            ].filter(Boolean).join(' ')}
            role="treeitem"
            aria-level={depth + 1}
            aria-expanded={childCount > 0 ? !isCollapsed : undefined}
            aria-selected={isSelected}
            data-testid={`span-tree-row-${span.spanId}`}
            onClick={() => handleRowClick(node, idx)}
          >
            <div
              className="span-tree-row"
              style={{ paddingLeft: `${depth * 16}px` }}
            >
              {childCount > 0 ? (
                <button
                  type="button"
                  className="span-tree-toggle"
                  aria-label={isCollapsed ? t('tracesPage.drawer.expand') : t('tracesPage.drawer.collapse')}
                  onClick={(e) => {
                    e.stopPropagation()
                    toggleCollapse(span.spanId)
                  }}
                  data-testid={`span-tree-toggle-${span.spanId}`}
                >
                  {isCollapsed
                    ? <ChevronRight size="var(--icon-size-sm)" aria-hidden="true" />
                    : <ChevronDown size="var(--icon-size-sm)" aria-hidden="true" />}
                </button>
              ) : (
                <span className="span-tree-toggle-placeholder" aria-hidden="true" />
              )}

              <span
                className={`span-tree-status span-tree-status--${isError ? 'error' : 'ok'}`}
                aria-label={isError ? t('tracesPage.drawer.statusError') : t('tracesPage.drawer.statusOk')}
                title={isError ? t('tracesPage.drawer.statusError') : t('tracesPage.drawer.statusOk')}
              />

              <Tooltip content={span.operationName}>
                <span className="span-tree-name">
                  {localizeSpanKind(t, spanKind)}
                </span>
              </Tooltip>

              {extraLabel && (
                <Tooltip content={extraLabel}>
                  <span className="span-tree-extra mono">
                    {extraLabel}
                  </span>
                </Tooltip>
              )}

              <span className="span-tree-offset mono">
                +{formatDuration(startOffset)}
              </span>

              <div className="span-tree-bar-area">
                {span.durationMs > 0 && (
                  <div
                    className={`span-tree-bar span-tree-bar--${isError ? 'error' : 'ok'}`}
                    style={{ left: `${leftPercent}%`, width: `${widthPercent}%` }}
                    aria-hidden="true"
                  />
                )}
                <span className="span-tree-duration mono">
                  {formatDuration(span.durationMs)}
                </span>
              </div>
            </div>

            {isError && localizedError && (
              <div className="span-tree-error-panel" role="note">
                <div className="span-tree-error-label">
                  {t('tracesPage.drawer.errorReason')}
                </div>
                <div className="span-tree-error-message">{localizedError}</div>
                {stack && (
                  <details className="span-tree-technical-detail">
                    <summary>{t('tracesPage.spanDetail.technicalDetails')}</summary>
                    <pre className="span-tree-error-stack mono">{stack}</pre>
                  </details>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
