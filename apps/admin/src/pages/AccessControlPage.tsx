import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router-dom'
import { RbacManager } from '../features/rbac'
import {
  PlatformUserRolesTab,
  usePlatformAdminData,
} from '../features/platform-admin'
import { SectionErrorBoundary, Tabs } from '../shared/ui'
import { PageHeader } from '../shared/ui'
import './access-control.css'

type AccessControlTab = 'permissions' | 'members'

function isValidTab(value: string | null): value is AccessControlTab {
  return value === 'permissions' || value === 'members'
}

function MembersTabPanel() {
  const {
    userLookupEmail,
    selectedUser,
    selectedUserRole,
    updatingUserRole,
    userLookupLoading,
    selectedUserError,
    error,
    setUserLookupEmail,
    setSelectedUserRole,
    handleLookupUser,
    handleUpdateUserRole,
  } = usePlatformAdminData(undefined, { users: true })

  return (
    <PlatformUserRolesTab
      userLookupEmail={userLookupEmail}
      selectedUser={selectedUser}
      selectedUserRole={selectedUserRole}
      updatingUserRole={updatingUserRole}
      userLookupLoading={userLookupLoading}
      lookupError={selectedUserError}
      updateError={error}
      onUserLookupEmailChange={setUserLookupEmail}
      onSelectedUserRoleChange={setSelectedUserRole}
      onLookupUser={handleLookupUser}
      onUpdateUserRole={() => void handleUpdateUserRole()}
    />
  )
}

/**
 * Access Control page — replaces /rbac in the new navigation structure.
 * Two sibling tabs: Permissions (role definitions, from RbacManager) and
 * Members (user-to-role assignment, from PlatformUserRolesTab).
 */
export function AccessControlPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const tabParam = searchParams.get('tab')
  const activeTab: AccessControlTab = isValidTab(tabParam) ? tabParam : 'permissions'

  const tabs = [
    {
      value: 'permissions',
      label: t('accessControlPage.tabPermissions'),
      panel: <RbacManager embedded />,
    },
    {
      value: 'members',
      label: t('accessControlPage.tabMembers'),
      panel: <MembersTabPanel />,
    },
  ]

  return (
    <SectionErrorBoundary name="access-control">
      <div className="page access-control-workspace">
        <PageHeader
          title={t('accessControlPage.title')}
          description={t('accessControlPage.description')}
        />
        <Tabs
          tabs={tabs}
          value={activeTab}
          onChange={(next) => {
            const params = new URLSearchParams(searchParams)
            params.set('tab', next)
            setSearchParams(params, { replace: true })
          }}
          ariaLabel={t('accessControlPage.tabsLabel')}
        />
      </div>
    </SectionErrorBoundary>
  )
}
