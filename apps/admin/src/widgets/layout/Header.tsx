import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, KeyRound, LogOut, Menu, Search, UserRound } from 'lucide-react'
import { useAuth } from '../../features/auth'
import { useRoleVisibility } from '../../features/workspace'
import { useChangePassword } from '../../features/auth/useChangePassword'
import { ChangePasswordModal } from '../../features/auth/ui/ChangePasswordModal'
import { useClockDisplay } from '../../shared/lib/useClockDisplay'
import { useSidebarStore } from '../../shared/store/sidebar.store'
import { GlobalStatusStrip } from './GlobalStatusStrip'
import { HeaderHealthBadge } from './HeaderHealthBadge'
import { ReactorMark } from '../../shared/ui'
import { useViewportMatch } from './useViewportMatch'

const MOBILE_NAV_QUERY = '(max-width: 768px)'

export function Header() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const { canToggleViewAs, viewAsManager, toggleViewAsManager } = useRoleVisibility()
  const { time, date } = useClockDisplay()
  const passwordState = useChangePassword()
  const isMobileNavigation = useViewportMatch(MOBILE_NAV_QUERY)
  const toggleDesktopSidebar = useSidebarStore((s) => s.toggle)
  const toggleMobileSidebar = useSidebarStore((s) => s.toggleMobile)
  const [accountMenuOpen, setAccountMenuOpen] = useState(false)
  const accountMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!accountMenuOpen) return

    function handlePointerDown(event: PointerEvent) {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setAccountMenuOpen(false)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setAccountMenuOpen(false)
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [accountMenuOpen])

  return (
    <>
      <header className="app-header">
        {/* Mobile menu button */}
        <button
          className="btn-icon mobile-menu-btn"
          onClick={isMobileNavigation ? toggleMobileSidebar : toggleDesktopSidebar}
          aria-label={t('common.aria.menu')}
          type="button"
        >
          <Menu size="var(--icon-size-md)" strokeWidth={1.5} />
        </button>

        {/* Brand */}
        <div className="app-header-brand">
          <ReactorMark className="logo-badge" label="Reactor" />
          <div className="brand-text">
            <span className="brand-prompt">Reactor</span>
            <span className="brand-subtitle">{t('workspace.operatorConsole')}</span>
          </div>
        </div>

        <div className="app-header-sep" />

        {/* Persistent global status strip — visualises "데이터를 한 곳에 모은다"
            structurally. Reuses dashboard / issue-center polling via TanStack
            Query dedupe, so mounting it globally adds no extra request load. */}
        <GlobalStatusStrip />

        <div className="app-header-spacer" />

        {/* Right actions */}
        <div className="app-header-right">
          {/* Command palette trigger — keyboard users still rely on Cmd+K,
              this provides a discoverable affordance for mouse users plus a
              spotlight target for the onboarding tour. */}
          <button
            type="button"
            className="cmd-palette-trigger"
            data-testid="cmd-palette-trigger"
            onClick={() => document.dispatchEvent(new CustomEvent('cmd-palette:open'))}
            aria-label={t('common.commandPalette.placeholder')}
            title={t('common.commandPalette.placeholder')}
          >
            <Search size="var(--icon-size-sm)" strokeWidth={1.5} aria-hidden="true" />
            <span className="cmd-palette-trigger__label">{t('header.commandPalette.label')}</span>
            <kbd className="cmd-palette-trigger__kbd" aria-hidden="true">⌘K</kbd>
          </button>

          {/* Operational health quick-glance — navigates to /health on click. */}
          <HeaderHealthBadge />

          {/* Clock */}
          <div className="clock">
            <span className="clock-time">{time}</span>
            <span>{date}</span>
          </div>

          <div className="app-header-sep" />

          {user && (
            <div className="app-header-account" ref={accountMenuRef}>
              <button
                type="button"
                className="btn-icon account-menu-trigger"
                aria-label={t('header.account.openMenu', { name: user.name })}
                aria-haspopup="menu"
                aria-expanded={accountMenuOpen}
                onClick={() => setAccountMenuOpen((open) => !open)}
              >
                <UserRound size="var(--icon-size-sm)" strokeWidth={1.75} aria-hidden="true" />
                <span className="account-menu-trigger__label">{user.name}</span>
                <ChevronDown size="var(--icon-size-xs)" strokeWidth={1.75} aria-hidden="true" />
              </button>

              {accountMenuOpen && (
                <div
                  className="account-menu"
                  role="menu"
                  aria-label={t('header.account.menuLabel')}
                >
                  <div className="account-menu__identity">
                    <strong>{user.name}</strong>
                    <span>{user.role}</span>
                  </div>

                  {canToggleViewAs && (
                    <button
                      type="button"
                      role="menuitem"
                      className="account-menu__item"
                      aria-pressed={viewAsManager}
                      onClick={() => {
                        toggleViewAsManager()
                        setAccountMenuOpen(false)
                      }}
                    >
                      <UserRound size="var(--icon-size-sm)" strokeWidth={1.75} aria-hidden="true" />
                      {viewAsManager ? t('header.viewAs.exitPreview') : t('header.viewAs.previewManager')}
                    </button>
                  )}

                  <div className="account-menu__divider" aria-hidden="true" />
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu__item"
                    aria-label={t('auth.changePassword')}
                    onClick={() => {
                      setAccountMenuOpen(false)
                      passwordState.open()
                    }}
                  >
                    <KeyRound size="var(--icon-size-sm)" strokeWidth={1.75} aria-hidden="true" />
                    {t('auth.changePassword')}
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    className="account-menu__item account-menu__item--danger"
                    aria-label={t('auth.logout')}
                    onClick={() => {
                      setAccountMenuOpen(false)
                      void logout()
                    }}
                  >
                    <LogOut size="var(--icon-size-sm)" strokeWidth={1.75} aria-hidden="true" />
                    {t('auth.logout')}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      <ChangePasswordModal state={passwordState} />
    </>
  )
}
