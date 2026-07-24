import './layout.css'
import { useEffect } from 'react'
import { Outlet, Navigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../features/auth'
import { useRoleVisibility } from '../../features/workspace'
import { SideNav } from './SideNav'
import { Header } from './Header'
import { LoadingSpinner, ErrorBoundary, NetworkStatus, CommandPalette, PageHelpOverlay, OnboardingTour } from '../../shared/ui'
import type { TourStep } from '../../shared/ui'
import { useFeatureAvailability } from '../../features/capabilities'

export function AdminLayout() {
  const { t } = useTranslation()
  const location = useLocation()
  const { isAuthenticated, isAdmin, isAuthRequired, isLoading } = useAuth()
  const { getVisibleNavGroups, effectiveRole } = useRoleVisibility()
  const { isRouteAvailable } = useFeatureAvailability()
  const visibleNavGroups = getVisibleNavGroups(isRouteAvailable)

  useEffect(() => {
    document.body.style.overflow = ''
    document.querySelectorAll('body > .modal-overlay').forEach(el => el.remove())
  }, [location.pathname])

  if (isLoading) {
    return (
      <div className="loading-fullscreen">
        <LoadingSpinner size="lg" />
        <span className="loading-fullscreen-text">{t('app.initializing')}</span>
      </div>
    )
  }

  if (isAuthRequired && (!isAuthenticated || !isAdmin)) {
    return <Navigate to="/login" replace />
  }

  // First-login onboarding tour. Only renders on the dashboard route so
  // the release workflow and dashboard spotlight targets exist on the page.
  const showOnboarding = location.pathname === '/'
  const onboardingSteps: TourStep[] = [
    {
      id: 'release-workflow',
      selector: '#release-workflow',
      title: t('onboarding.tour.step1Title'),
      description: t('onboarding.tour.step1Description'),
      position: 'bottom',
    },
    {
      id: 'cmd-palette',
      selector: '[data-testid="cmd-palette-trigger"]',
      title: t('onboarding.tour.step2Title'),
      description: t('onboarding.tour.step2Description'),
      position: 'bottom',
    },
    {
      id: 'sidebar-nav',
      selector: '.sidenav',
      title: t('onboarding.tour.step3Title'),
      description: t('onboarding.tour.step3Description'),
      position: 'right',
    },
    {
      id: 'health-badge',
      selector: '.header-health-badge',
      title: t('onboarding.tour.step4Title'),
      description: t('onboarding.tour.step4Description'),
      position: 'bottom',
    },
  ]

  return (
    <div className="shell">
      <a href="#main-content" className="skip-link">{t('common.skipToContent')}</a>
      <CommandPalette navGroups={visibleNavGroups} />
      <PageHelpOverlay />
      {showOnboarding && (
        <OnboardingTour
          steps={onboardingSteps}
          storageKey="reactor-admin-v1-1-release-onboarding-completed"
        />
      )}
      <NetworkStatus />
      <Header />
      <div className="app-body">
        <SideNav />
        <main id="main-content" className="app-content">
          <ErrorBoundary level="route" key={location.pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <footer className="app-footer">
        <span className="app-footer-tenant">{t('app.consoleTitle')}</span>
        {effectiveRole && (
          <span className="app-footer-role">{t(`auth.roleNames.${effectiveRole}`)}</span>
        )}
      </footer>
    </div>
  )
}
