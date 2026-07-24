import { TraceViewerManager } from '../features/traces'
import { SectionErrorBoundary } from '../shared/ui'

export function TracesPage() {
  return (
    <SectionErrorBoundary name="traces">
      <TraceViewerManager />
    </SectionErrorBoundary>
  )
}
