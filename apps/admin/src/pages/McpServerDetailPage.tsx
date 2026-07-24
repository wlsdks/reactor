import { useTranslation } from 'react-i18next'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'
import { McpServerDetailView } from '../features/mcp-servers'

export default function McpServerDetailPage() {
  const { t } = useTranslation()
  // BX audit P1-2: Detail pages do not use the shared PageHeader, so we
  // set the browser tab title here. Use the parent list label as a stable
  // baseline; per-record naming would require lifting the loaded server
  // name into this wrapper.
  useDocumentTitle(t('nav.mcpServers'))
  return (
    <SectionErrorBoundary name="mcp-server-detail">
      <McpServerDetailView />
    </SectionErrorBoundary>
  )
}
