import { useTranslation } from 'react-i18next'
import { ApprovalsManager } from '../features/approvals'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'

export function ApprovalsPage() {
  const { t } = useTranslation()
  // BX audit P1-2: ApprovalsManager renders PageHeader (which drives the tab
  // title), but it lives behind data-loading branches. Setting the title
  // here ensures the browser tab reflects the route immediately, before the
  // inner manager mounts.
  useDocumentTitle(t('nav.approvals'))
  return (
    <SectionErrorBoundary name="approvals">
      <ApprovalsManager />
    </SectionErrorBoundary>
  )
}
