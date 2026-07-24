import { useTranslation } from 'react-i18next'
import { SectionErrorBoundary } from '../shared/ui'
import { EvalDashboardManager } from '../features/evals'
import { useDocumentTitle } from '../shared/lib'

export function EvalsPage() {
  const { t } = useTranslation()
  // BX audit P1-2: EvalDashboardManager renders PageHeader (which drives the
  // tab title), but it lives behind data-loading branches. Setting the title
  // here ensures the browser tab reflects the route immediately, before the
  // inner manager mounts.
  useDocumentTitle(t('evalsPage.title'))
  return (
    <SectionErrorBoundary name="evals">
      <EvalDashboardManager />
    </SectionErrorBoundary>
  )
}
