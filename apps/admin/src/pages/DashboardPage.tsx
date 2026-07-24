import { useTranslation } from 'react-i18next'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'
import { DashboardView } from '../features/dashboard'

export function DashboardPage() {
  const { t } = useTranslation()
  // BX audit P1-2: Dashboard does not use the shared PageHeader (sui generis),
  // so we set the browser tab title manually.
  useDocumentTitle(t('nav.dashboard'))
  return (
    <SectionErrorBoundary name="dashboard">
      <DashboardView />
    </SectionErrorBoundary>
  )
}
