import { McpServersListView } from '../features/mcp-servers'
import { SectionErrorBoundary } from '../shared/ui'

export function McpServersPage() {
  return (
    <SectionErrorBoundary name="mcp-servers">
      <McpServersListView />
    </SectionErrorBoundary>
  )
}
