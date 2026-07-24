import { Fragment, useEffect, useRef } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, Menu, X } from 'lucide-react'
import { useFeatureAvailability } from '../../features/capabilities'
import { useIssueCenterSnapshot } from '../../features/issues'
import { useRoleVisibility } from '../../features/workspace'
import { useSidebarStore } from '../../shared/store/sidebar.store'
import { useSidenavGroupsStore } from '../../shared/store/sidenav-groups.store'
import { useScrollAffordance } from './useScrollAffordance'
import { useViewportMatch } from './useViewportMatch'

const MOBILE_BREAKPOINT = 768
/** Auto-collapse the sidebar below this viewport width unless the user has
 *  explicitly expanded it. Matches the tablet tier in layout.css. */
const TABLET_COLLAPSE_BREAKPOINT = 1024
const SWIPE_THRESHOLD = 50

export function SideNav() {
  const { t } = useTranslation()
  const location = useLocation()
  const { isRouteAvailable, isLoading } = useFeatureAvailability()
  const { getVisibleNavGroups } = useRoleVisibility()
  const { data: issueSnapshot } = useIssueCenterSnapshot()
  const { collapsed, mobileOpen, toggle, close, toggleMobile, closeMobile } = useSidebarStore()
  const collapsedGroups = useSidenavGroupsStore((s) => s.collapsedGroups)
  const toggleGroup = useSidenavGroupsStore((s) => s.toggleGroup)
  const visibleGroups = getVisibleNavGroups(isRouteAvailable)
  const touchStartX = useRef<number | null>(null)
  const {
    ref: scrollRef,
    canScrollUp,
    canScrollDown,
  } = useScrollAffordance<HTMLDivElement>([visibleGroups, collapsed, mobileOpen])

  const isMobile = useViewportMatch(`(max-width: ${MOBILE_BREAKPOINT}px)`)
  const isTabletOrBelow = useViewportMatch(`(max-width: ${TABLET_COLLAPSE_BREAKPOINT}px)`)
  const isExpanded = isMobile ? mobileOpen : !collapsed

  // Auto-collapse when the viewport crosses into tablet range, unless the
  // user explicitly opened the sidebar themselves (the `open()` action in the
  // store writes `false` to localStorage; the stored preference wins on next
  // page load, and here we only force-collapse on the downward transition).
  const prevIsTabletRef = useRef<boolean | null>(null)
  useEffect(() => {
    const wasTablet = prevIsTabletRef.current
    prevIsTabletRef.current = isTabletOrBelow
    if (wasTablet === null) return
    if (!wasTablet && isTabletOrBelow && !collapsed) {
      close()
    }
  }, [isTabletOrBelow, collapsed, close])

  // Close sidebar on route change (mobile)
  useEffect(() => {
    if (isMobile) {
      closeMobile()
    }
  }, [location.pathname, isMobile, closeMobile])

  // Close on Escape — but only if no modal/dialog is open. Modal Esc must
  // win over the sidebar so users don't accidentally collapse the menu while
  // dismissing a confirmation dialog or detail drawer. Pattern mirrors
  // PageHelpOverlay's global key listener (see PageHelpOverlay.tsx:101).
  useEffect(() => {
    if (!isExpanded) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Escape') return
      if (document.querySelector('[role="dialog"]')) return
      if (isMobile) closeMobile()
      else close()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isExpanded, isMobile, close, closeMobile])

  // Swipe gesture: swipe right from left edge to open, swipe left to close
  useEffect(() => {
    if (!isMobile) return

    function handleTouchStart(e: TouchEvent) {
      const touch = e.touches[0]
      if (!touch) return
      // Only capture swipe from left edge (within 30px) when collapsed
      if (!mobileOpen && touch.clientX < 30) {
        touchStartX.current = touch.clientX
      }
      // Capture any swipe when expanded (for closing)
      if (mobileOpen) {
        touchStartX.current = touch.clientX
      }
    }

    function handleTouchEnd(e: TouchEvent) {
      if (touchStartX.current === null) return
      const touch = e.changedTouches[0]
      if (!touch) return
      const deltaX = touch.clientX - touchStartX.current
      touchStartX.current = null

      if (!mobileOpen && deltaX > SWIPE_THRESHOLD) {
        toggleMobile() // swipe right → open
      }
      if (mobileOpen && deltaX < -SWIPE_THRESHOLD) {
        closeMobile() // swipe left → close
      }
    }

    document.addEventListener('touchstart', handleTouchStart, { passive: true })
    document.addEventListener('touchend', handleTouchEnd, { passive: true })
    return () => {
      document.removeEventListener('touchstart', handleTouchStart)
      document.removeEventListener('touchend', handleTouchEnd)
    }
  }, [isMobile, mobileOpen, toggleMobile, closeMobile])

  function scrollToBottom() {
    scrollRef.current?.scrollBy({ top: 150, behavior: 'smooth' })
  }

  return (
    <>
      {/* Mobile overlay backdrop */}
      {isMobile && mobileOpen && (
        <div className="sidenav-overlay" onClick={closeMobile} aria-hidden="true" />
      )}

      <nav
        className={`sidenav${isExpanded ? ' expanded' : ''}`}
        role="navigation"
        aria-label={t('common.aria.mainNavigation')}
      >
        <button
          className="sidenav-toggle"
          onClick={isMobile ? toggleMobile : toggle}
          aria-label={isExpanded ? t('nav.collapse') : t('nav.expand')}
          type="button"
        >
          {isExpanded ? <X size="var(--icon-size-md)" strokeWidth={1.5} /> : <Menu size="var(--icon-size-md)" strokeWidth={1.5} />}
          {isExpanded && (
            <span className="sidenav-toggle-label">{t('nav.navigation')}</span>
          )}
        </button>

        <div className="sidenav-scroll-area" ref={scrollRef}>
          {canScrollUp && <div className="sidenav-fade sidenav-fade--top" />}

          {!isLoading && visibleGroups.map((group, groupIdx) => {
            const safeKey = group.titleKey.replace(/\./g, '-')
            const groupLabelId = `sidenav-group-${safeKey}`
            const groupListId = `sidenav-group-list-${safeKey}`
            const isGroupCollapsed = collapsedGroups.has(group.titleKey)
            const releaseStepNumbers = group.items
              .map((item) => item.releaseStepNumber)
              .filter((step): step is number => typeof step === 'number')
            const releaseStepMin = releaseStepNumbers.length > 0
              ? Math.min(...releaseStepNumbers)
              : null
            const releaseStepMax = releaseStepNumbers.length > 0
              ? Math.max(...releaseStepNumbers)
              : null
            const releaseStepRange = releaseStepMin === null || releaseStepMax === null
              ? null
              : releaseStepMin === releaseStepMax
                ? `${releaseStepMin}`
                : `${releaseStepMin}-${releaseStepMax}`
            // Per-group collapse only applies when the sidebar itself is
            // expanded — when the rail is icon-only (collapsed), the group
            // header is hidden so there's no toggle affordance. Items always
            // render in icon-only mode so navigation stays reachable.
            const itemsHidden = isExpanded && isGroupCollapsed
            return (
              <Fragment key={group.titleKey}>
                {groupIdx > 0 && <div className="sidenav-divider" aria-hidden="true" />}
                <section className="sidenav-group" aria-labelledby={groupLabelId}>
                  {isExpanded && (
                    <h2 className="sidenav-group-heading">
                      <button
                        type="button"
                        id={groupLabelId}
                        className="sidenav-group-toggle"
                        aria-expanded={!isGroupCollapsed}
                        aria-controls={groupListId}
                        onClick={() => toggleGroup(group.titleKey)}
                      >
                        <span className="sidenav-group-label">{t(group.titleKey)}</span>
                        {releaseStepRange && (
                          <span
                            className="sidenav-group-step-range"
                            aria-label={t('nav.releaseStepRange', { range: releaseStepRange })}
                          >
                            {t('nav.releaseStepRangeShort', { range: releaseStepRange })}
                          </span>
                        )}
                        <ChevronDown
                          size="var(--icon-size-xs)"
                          strokeWidth={2}
                          className={`sidenav-group-chevron${isGroupCollapsed ? ' collapsed' : ''}`}
                          aria-hidden="true"
                        />
                      </button>
                    </h2>
                  )}
                  {isExpanded && group.descriptionKey && !itemsHidden && (
                    <p className="sidenav-group-description">
                      {t(group.descriptionKey)}
                    </p>
                  )}
                  {!isExpanded && (
                    <span id={groupLabelId} className="sr-only">{t(group.titleKey)}</span>
                  )}
                  <ul
                    id={groupListId}
                    role="list"
                    className="sidenav-group-list"
                    hidden={itemsHidden}
                  >
                    {group.items.map((item) => {
                      const IconComponent = item.icon
                      const navLabel = item.releaseStepNumber
                        ? `${item.releaseStepNumber}. ${t(item.label)}`
                        : t(item.label)
                      return (
                        <li key={item.path}>
                          <NavLink
                            to={item.path}
                            end={item.path === '/'}
                            className={({ isActive }) =>
                              `sidenav-item${isActive ? ' active' : ''}`
                            }
                            title={!isExpanded ? navLabel : undefined}
                            aria-label={navLabel}
                          >
                            <span className="sidenav-item-icon">
                              <IconComponent size="var(--icon-size-md)" strokeWidth={1.75} />
                            </span>
                            {isExpanded && item.releaseStepNumber && (
                              <span className="sidenav-step" aria-hidden="true">
                                {item.releaseStepNumber}
                              </span>
                            )}
                            <span className="sidenav-item-copy">
                              <span className="sidenav-item-label">{t(item.label)}</span>
                              {isExpanded && item.releaseStepNumber && (
                                <span className="sidenav-item-description" aria-hidden="true">
                                  {t(item.description)}
                                </span>
                              )}
                            </span>
                            {isExpanded && item.path === '/issues' && issueSnapshot && issueSnapshot.total > 0 && (
                              <span className={`sidenav-badge ${issueSnapshot.criticalCount > 0 ? 'critical' : 'warning'}`}>
                                {issueSnapshot.total}
                              </span>
                            )}
                          </NavLink>
                        </li>
                      )
                    })}
                  </ul>
                </section>
              </Fragment>
            )
          })}

          {canScrollDown && <div className="sidenav-fade sidenav-fade--bottom" />}
        </div>

        {canScrollDown && (
          <button
            className="sidenav-scroll-hint"
            onClick={scrollToBottom}
            aria-label={t('common.aria.scrollDown')}
            type="button"
          >
            <ChevronDown size="var(--icon-size-sm)" strokeWidth={1.5} />
          </button>
        )}
      </nav>
    </>
  )
}
