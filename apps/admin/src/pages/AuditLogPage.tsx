import { useTranslation } from 'react-i18next'
import { AuditLogManager } from '../features/audit'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'

export function AuditLogPage() {
  const { t } = useTranslation()
  // BX audit P1-2: AuditLogManager renders PageHeader (which drives the tab
  // title), but it lives behind data-loading branches. Setting the title
  // here ensures the browser tab reflects the route immediately, before the
  // inner manager mounts.
  useDocumentTitle(t('nav.audit'))
  return (
    <SectionErrorBoundary name="audit-log">
      <AuditLogManager />
    </SectionErrorBoundary>
  )
}
