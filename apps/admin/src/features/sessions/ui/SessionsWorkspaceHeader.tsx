import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '../../../shared/ui/PageHeader'

interface SessionsWorkspaceHeaderProps {
  title: string
  description: string
}

const WORKSPACE_ROUTES = [
  { to: '/sessions', labelKey: 'conversations.workspace.overview', end: true },
  { to: '/sessions/feed', labelKey: 'conversations.workspace.feed', end: false },
  { to: '/sessions/users', labelKey: 'conversations.workspace.users', end: false },
] as const

export function SessionsWorkspaceHeader({ title, description }: SessionsWorkspaceHeaderProps) {
  const { t } = useTranslation()

  return (
    <>
      <PageHeader title={title} description={description} />
      <nav className="sessions-workspace-nav" aria-label={t('conversations.workspace.ariaLabel')}>
        {WORKSPACE_ROUTES.map((route) => (
          <NavLink
            key={route.to}
            to={route.to}
            end={route.end}
            className={({ isActive }) =>
              `sessions-workspace-nav__link${isActive ? ' is-active' : ''}`
            }
          >
            {t(route.labelKey)}
          </NavLink>
        ))}
      </nav>
    </>
  )
}
