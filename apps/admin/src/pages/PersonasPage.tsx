import { PersonaManager } from '../features/personas'
import { SectionErrorBoundary } from '../shared/ui'

export function PersonasPage() {
  return (
    <SectionErrorBoundary name="personas">
      <PersonaManager />
    </SectionErrorBoundary>
  )
}
