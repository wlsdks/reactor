import { useTranslation } from 'react-i18next'
import { SessionsWorkspaceHeader, UsersList } from '../features/sessions'
import { SectionErrorBoundary } from '../shared/ui'

export function SessionUsersPage() {
  const { t } = useTranslation()
  return (
    <>
      <SessionsWorkspaceHeader
        title={t('conversations.title')}
        description={t('conversations.workspace.usersDescription')}
      />
      <SectionErrorBoundary name="session-users">
        <UsersList />
      </SectionErrorBoundary>
    </>
  )
}
