import { ReactorUniverseManager } from '../features/reactor-universe'
import { SectionErrorBoundary } from '../shared/ui'

export function ReactorUniversePage() {
  return (
    <SectionErrorBoundary name="reactor-universe">
      <ReactorUniverseManager />
    </SectionErrorBoundary>
  )
}
