import { MetricIngestionManager } from '../features/metric-ingestion'
import { SectionErrorBoundary } from '../shared/ui'

export function MetricsIngestionPage() {
  return (
    <SectionErrorBoundary name="metrics-ingestion">
      <MetricIngestionManager />
    </SectionErrorBoundary>
  )
}
