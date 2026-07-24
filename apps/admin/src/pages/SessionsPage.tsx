import { useTranslation } from 'react-i18next'
import { ConversationOverview, SessionsWorkspaceHeader } from '../features/sessions'
import { SectionErrorBoundary } from '../shared/ui'

export function SessionsPage() {
  const { t } = useTranslation()
  return (
    <>
      <SessionsWorkspaceHeader
        title={t('conversations.title')}
        description={t('conversations.workspace.overviewDescription')}
      />
      <SectionErrorBoundary name="sessions">
        <ConversationOverview />
      </SectionErrorBoundary>
    </>
  )
}
