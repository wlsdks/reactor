import { RagCacheManager } from '../features/rag-cache'
import { SectionErrorBoundary } from '../shared/ui'

export function RagCachePage() {
  return (
    <SectionErrorBoundary name="rag-cache">
      <RagCacheManager />
    </SectionErrorBoundary>
  )
}
