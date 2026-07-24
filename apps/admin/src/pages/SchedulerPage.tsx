import { SchedulerManager } from '../features/scheduler'
import { SectionErrorBoundary } from '../shared/ui'

export function SchedulerPage() {
  return (
    <SectionErrorBoundary name="scheduler">
      <SchedulerManager />
    </SectionErrorBoundary>
  )
}
