import { useTranslation } from 'react-i18next'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'
import { UsageDashboardManager } from '../features/usage'

export function UsagePage() {
  const { t } = useTranslation()
  // BX audit P1-2: Usage feature does not use the shared PageHeader, so we
  // set the browser tab title here.
  useDocumentTitle(t('nav.usage'))
  return (
    <SectionErrorBoundary name="usage">
      <UsageDashboardManager />
    </SectionErrorBoundary>
  )
}
