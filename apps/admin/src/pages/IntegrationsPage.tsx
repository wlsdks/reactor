import { SectionErrorBoundary } from '../shared/ui'
import { IntegrationsManager } from '../features/integrations'

export function IntegrationsPage() {
  return (
    <SectionErrorBoundary name="integrations">
      <IntegrationsManager />
    </SectionErrorBoundary>
  )
}
