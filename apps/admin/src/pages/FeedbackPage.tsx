import { FeedbackManager } from '../features/feedback'
import { SectionErrorBoundary } from '../shared/ui'

export function FeedbackPage() {
  return (
    <SectionErrorBoundary name="feedback">
      <FeedbackManager />
    </SectionErrorBoundary>
  )
}
