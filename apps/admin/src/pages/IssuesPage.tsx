import { IssueCenterManager } from '../features/issues'
import { SectionErrorBoundary } from '../shared/ui'

export function IssuesPage() {
  return (
    <SectionErrorBoundary name="issues">
      <IssueCenterManager />
    </SectionErrorBoundary>
  )
}
