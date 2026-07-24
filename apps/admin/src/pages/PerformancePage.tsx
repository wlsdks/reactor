import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'

import { LatencyDashboardManager } from '../features/latency'
import { ToolsSegment } from '../features/tool-stats/ui/ToolsSegment'
import { PageHeader, SectionErrorBoundary, SkeletonChart, Tabs } from '../shared/ui'

const ConversationAnalyticsTab = lazy(() =>
  import('../features/conversation-analytics/ui/ConversationAnalyticsTab').then((module) => ({
    default: module.ConversationAnalyticsTab,
  })),
)

type Segment = 'latency' | 'conversations' | 'tools'

const VALID_SEGMENTS: ReadonlySet<Segment> = new Set(['latency', 'conversations', 'tools'])

function parseSegment(value: string | null): Segment {
  return value && (VALID_SEGMENTS as Set<string>).has(value)
    ? (value as Segment)
    : 'latency'
}

export function PerformancePage() {
  const { t } = useTranslation()
  // BX audit P1-2: PageHeader (rendered below) wires `document.title` via
  // `useDocumentTitle`, so no separate hook call is needed here.
  const [searchParams, setSearchParams] = useSearchParams()
  const value = parseSegment(searchParams.get('seg'))

  const handleChange = (next: string) => {
    setSearchParams(
      (prev) => {
        const updated = new URLSearchParams(prev)
        if (next === 'latency') {
          // Default segment — drop the param so shareable URLs stay tidy.
          updated.delete('seg')
        } else {
          updated.set('seg', next)
        }
        return updated
      },
      { replace: true },
    )
  }

  return (
    <SectionErrorBoundary name="performance">
      <PageHeader
        title={t('performancePage.title')}
        description={t('performancePage.description')}
      />
      <Tabs
        ariaLabel={t('performancePage.tabsAriaLabel')}
        value={value}
        onChange={handleChange}
        tabs={[
          {
            value: 'latency',
            label: t('performancePage.segments.latency'),
            panel: (
              <SectionErrorBoundary name="performance-latency">
                <LatencyDashboardManager />
              </SectionErrorBoundary>
            ),
          },
          {
            value: 'conversations',
            label: t('performancePage.segments.conversations'),
            panel: (
              <SectionErrorBoundary name="performance-conversations">
                <Suspense fallback={<SkeletonChart height={260} />}>
                  <ConversationAnalyticsTab />
                </Suspense>
              </SectionErrorBoundary>
            ),
          },
          {
            value: 'tools',
            label: t('performancePage.segments.tools'),
            panel: (
              <SectionErrorBoundary name="performance-tools">
                <ToolsSegment />
              </SectionErrorBoundary>
            ),
          },
        ]}
      />
    </SectionErrorBoundary>
  )
}
