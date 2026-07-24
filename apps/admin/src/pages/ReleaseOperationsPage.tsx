import { SectionErrorBoundary } from '../shared/ui'
import { ReleaseOperationsWorkspace } from '../features/release-operations'

export function ReleaseOperationsPage() {
  return (
    <SectionErrorBoundary name="release-operations">
      <ReleaseOperationsWorkspace />
    </SectionErrorBoundary>
  )
}
