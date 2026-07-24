import { useTranslation } from 'react-i18next'
import { ChatInspectorManager } from '../features/chat-inspector'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'

export function ChatInspectorPage() {
  const { t } = useTranslation()
  // BX audit P1-2: ChatInspectorManager renders PageHeader (which drives the
  // tab title), but it lives behind data-loading branches. Setting the title
  // here ensures the browser tab reflects the route immediately, before the
  // inner manager mounts.
  useDocumentTitle(t('nav.chatInspector'))
  return (
    <SectionErrorBoundary name="chat-inspector">
      <ChatInspectorManager />
    </SectionErrorBoundary>
  )
}
