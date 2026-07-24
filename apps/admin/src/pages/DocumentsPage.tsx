import { useTranslation } from 'react-i18next'
import { DocumentsManager } from '../features/documents'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'

export function DocumentsPage() {
  const { t } = useTranslation()
  // BX audit P1-2: DocumentsManager renders PageHeader (which drives the tab
  // title), but it lives behind data-loading branches. Setting the title
  // here ensures the browser tab reflects the route immediately, before the
  // inner manager mounts.
  useDocumentTitle(t('nav.documents'))
  return (
    <SectionErrorBoundary name="documents">
      <DocumentsManager />
    </SectionErrorBoundary>
  )
}
