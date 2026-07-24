import { DebugReplayManager } from '../features/debug-replay'
import { SectionErrorBoundary } from '../shared/ui'

export function DebugReplayPage() {
  return (
    <SectionErrorBoundary name="debug-replay">
      <DebugReplayManager />
    </SectionErrorBoundary>
  )
}
