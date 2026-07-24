import { useTranslation } from 'react-i18next'
import { SessionsFeed, SessionsWorkspaceHeader } from '../features/sessions'
import { SectionErrorBoundary } from '../shared/ui'

export function SessionsFeedPage() {
  const { t } = useTranslation()
  return (
    <>
      <SessionsWorkspaceHeader
        title={t('conversations.title')}
        description={t('conversations.workspace.feedDescription')}
      />
      <SectionErrorBoundary name="sessions-feed">
        <SessionsFeed />
      </SectionErrorBoundary>
    </>
  )
}
