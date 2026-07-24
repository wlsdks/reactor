import './PlatformUserRolesTab.css'
import { useTranslation } from 'react-i18next'
import { LoadingSpinner, WorkspaceUnavailable } from '../../../shared/ui'
import { formatISODate } from '../../../shared/lib/formatters'
import { getErrorMessage } from '../../../shared/lib/getErrorMessage'
import { ApiError } from '../../../shared/api/errors'
import type { PlatformUserRole, PlatformUserSummary } from '../types'

interface PlatformUserRolesTabProps {
  userLookupEmail: string
  selectedUser: PlatformUserSummary | null
  selectedUserRole: PlatformUserRole
  updatingUserRole: boolean
  userLookupLoading: boolean
  lookupError: unknown
  updateError: string | null
  onUserLookupEmailChange: (email: string) => void
  onSelectedUserRoleChange: (role: PlatformUserRole) => void
  onLookupUser: () => void
  onUpdateUserRole: () => void
}

const ROLE_LABEL_KEYS: Record<PlatformUserRole, string> = {
  USER: 'accessControlPage.roleLabels.USER',
  ADMIN_MANAGER: 'accessControlPage.roleLabels.ADMIN_MANAGER',
  ADMIN_DEVELOPER: 'accessControlPage.roleLabels.ADMIN_DEVELOPER',
  ADMIN: 'accessControlPage.roleLabels.ADMIN',
}

const SCOPE_LABEL_KEYS: Record<string, string> = {
  FULL: 'accessControlPage.scopeLabels.FULL',
  MANAGER: 'accessControlPage.scopeLabels.MANAGER',
  DEVELOPER: 'accessControlPage.scopeLabels.DEVELOPER',
}

export function PlatformUserRolesTab({
  userLookupEmail,
  selectedUser,
  selectedUserRole,
  updatingUserRole,
  userLookupLoading,
  lookupError,
  updateError,
  onUserLookupEmailChange,
  onSelectedUserRoleChange,
  onLookupUser,
  onUpdateUserRole,
}: PlatformUserRolesTabProps) {
  const { t } = useTranslation()
  const userNotFound = lookupError instanceof ApiError && lookupError.status === 404
  const roleLabel = (role: PlatformUserRole) => t(ROLE_LABEL_KEYS[role])
  const scopeLabel = (scope: string | null | undefined) => scope == null
    ? t('accessControlPage.scopeNone')
    : t(SCOPE_LABEL_KEYS[scope] ?? 'accessControlPage.scopeUnknown')

  return (
    <section className="member-access" aria-labelledby="member-access-title">
      <div className="member-access__heading">
        <h2 id="member-access-title">{t('platformAdminPage.adminUserRoles')}</h2>
        <p>{t('platformAdminPage.adminUserRolesDescription')}</p>
      </div>

      <form className="member-access__lookup" onSubmit={(event) => { event.preventDefault(); onLookupUser() }}>
        <label htmlFor="user-lookup-email">
          <span>{t('accessControlPage.memberEmail')}</span>
          <input id="user-lookup-email" type="email" value={userLookupEmail} onChange={(event) => onUserLookupEmailChange(event.target.value)} placeholder={t('platformAdminPage.userEmailPlaceholder')} autoComplete="off" />
        </label>
        <button className="btn btn-secondary" type="submit" disabled={userLookupLoading || userLookupEmail.trim().length === 0}>
          {userLookupLoading ? <LoadingSpinner size="sm" /> : t('platformAdminPage.lookupUser')}
        </button>
      </form>

      {lookupError && !userNotFound ? (
        <WorkspaceUnavailable
          title={t('accessControlPage.memberLookupUnavailableTitle')}
          description={t('accessControlPage.memberLookupUnavailableDescription')}
          retryLabel={t('common.retry')}
          retryingLabel={t('common.retrying')}
          onRetry={onLookupUser}
          isRetrying={userLookupLoading}
          secondaryAction={{ label: t('common.openStatusPage'), to: '/health' }}
          guide={{
            title: t('accessControlPage.recoveryTitle'),
            steps: [t('accessControlPage.recoveryAccount'), t('accessControlPage.recoveryConnection')],
            technicalLabel: t('common.technicalDetails'),
            technicalDetail: getErrorMessage(lookupError),
          }}
        />
      ) : userNotFound ? (
        <div className="member-access__empty" role="status">
          <h3>{t('accessControlPage.memberNotFoundTitle')}</h3>
          <p>{t('accessControlPage.memberNotFoundDescription')}</p>
        </div>
      ) : selectedUser ? (
        <div className="member-access__result">
          <dl className="member-access__identity">
            <div><dt>{t('common.name')}</dt><dd>{selectedUser.name}</dd></div>
            <div><dt>{t('auth.email')}</dt><dd>{selectedUser.email}</dd></div>
            <div><dt>{t('common.createdAt')}</dt><dd>{formatISODate(selectedUser.createdAt)}</dd></div>
            <div><dt>{t('platformAdminPage.currentRole')}</dt><dd>{roleLabel(selectedUser.role)}</dd></div>
            <div><dt>{t('platformAdminPage.currentScope')}</dt><dd>{scopeLabel(selectedUser.adminScope)}</dd></div>
          </dl>
          <div className="member-access__role-editor">
            <label htmlFor="user-target-role"><span>{t('platformAdminPage.targetRole')}</span><select id="user-target-role" value={selectedUserRole} onChange={(event) => onSelectedUserRoleChange(event.target.value as PlatformUserRole)}>{Object.keys(ROLE_LABEL_KEYS).map((value) => <option key={value} value={value}>{roleLabel(value as PlatformUserRole)}</option>)}</select></label>
            <button className="btn btn-primary" type="button" onClick={onUpdateUserRole} disabled={updatingUserRole || selectedUserRole === selectedUser.role}>{updatingUserRole ? <LoadingSpinner size="sm" /> : t('platformAdminPage.updateRole')}</button>
          </div>
          {updateError ? (
            <div className="member-access__action-error" role="alert">
              <span>{t('accessControlPage.memberUpdateFailed')}</span>
              <details>
                <summary>{t('common.technicalDetails')}</summary>
                <code>{updateError}</code>
              </details>
            </div>
          ) : null}
        </div>
      ) : (
        <div className="member-access__empty" role="status">
          <h3>{t('platformAdminPage.noUserSelected')}</h3>
          <p>{t('accessControlPage.memberLookupEmpty')}</p>
        </div>
      )}
    </section>
  )
}
