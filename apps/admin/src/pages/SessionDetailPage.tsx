import { useTranslation } from 'react-i18next'
import { SessionDetail } from '../features/sessions'
import { SectionErrorBoundary } from '../shared/ui'
import { useDocumentTitle } from '../shared/lib'

export function SessionDetailPage() {
  const { t } = useTranslation()
  // BX audit P1-2: Detail pages do not use the shared PageHeader, so we
  // set the browser tab title here.
  useDocumentTitle(t('nav.sessions'))
  return (
    <SectionErrorBoundary name="session-detail">
      <SessionDetail />
    </SectionErrorBoundary>
  )
}
