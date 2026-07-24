import { PromptStudioManager } from '../features/prompt-studio'
import { SectionErrorBoundary } from '../shared/ui'

export function PromptStudioPage() {
  return (
    <SectionErrorBoundary name="prompt-studio">
      <PromptStudioManager />
    </SectionErrorBoundary>
  )
}
