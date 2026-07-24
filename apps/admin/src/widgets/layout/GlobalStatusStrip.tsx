import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../features/auth'
import { useDashboardData } from '../../features/dashboard/useDashboardData'
import { useIssueCenterSnapshot } from '../../features/issues'

/**
 * Format a timestamp as `HH:MM` in the local timezone.
 *
 * Used by the status strip's "last updated" chip — kept inline (not exported
 * from formatters) because no other surface needs this exact format.
 */
function formatClockHHMM(epochMs: number | null | undefined): string {
  if (epochMs == null) return ''
  try {
    return new Intl.DateTimeFormat('en-GB', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(epochMs))
  } catch {
    return ''
  }
}

/**
 * Persistent strip in the global Header showing live aggregate state across
 * feature domains. Visualises the brand promise "데이터를 한 곳에 모은다"
 * structurally rather than narrating it in copy.
 *
 * Each chip is a `<Link>` so keyboard users can tab through and screen
 * readers expose the destination. Chips reuse existing TanStack Query
 * polling — the dedupe of `useDashboardData()` and `useIssueCenterSnapshot()`
 * means mounting this in the global header does not double the request rate.
 *
 * Hides gracefully:
 *   - When unauthenticated (auth gate avoids unnecessary queries on /login).
 *   - When all chips are empty/unloaded (avoids visual noise on cold starts).
 *   - Per-chip: MCP total 0 hides the MCP chip; missing data hides the
 *     specific chip without breaking the rest of the strip.
 */
export function GlobalStatusStrip() {
  const { t } = useTranslation()
  const { isAuthenticated, isAdmin } = useAuth()

  // Auth gate: avoid kicking off polling for users not logged in. The hooks
  // themselves are idempotent under React strict-mode; gating prevents the
  // login screen from issuing dashboard/issue-center requests.
  const enabled = isAuthenticated && isAdmin
  const dashboard = useDashboardData(undefined, false, enabled)
  const issuesQuery = useIssueCenterSnapshot(enabled)

  if (!enabled) return null

  // Loading state for the very first paint — return null so the header
  // doesn't flash a skeleton during the brief warm-up window.
  //
  // Resilience: every property access below uses optional chaining all the way
  // through, so a partial / malformed response (e.g. unmocked endpoint in an
  // e2e spec returning HTML or `{}`) falls back to safe defaults rather than
  // throwing and tearing down the layout. The strip is decorative — operators
  // diagnose real failures on /integrations, not via a status chip — so it is
  // correct to render nothing on error rather than show broken state.
  const dashboardData = dashboard.data ?? null
  const issuesData = issuesQuery.data ?? null
  const dashboardReady = dashboardData != null
  const issuesReady = issuesData != null
  if (!dashboardReady && !issuesReady) return null

  // Errors: hide gracefully instead of showing broken chips. Each domain has
  // its own page-level error UI; the global strip just gets out of the way.
  const dashboardError = dashboard.error != null
  const issuesError = issuesQuery.isError

  // Defensive: even with `dashboardReady`, the response might be partial when
  // talking to an unmocked / proxied backend. Coerce missing keys to 0/empty.
  const mcpTotal = dashboardData?.mcp?.total ?? 0
  const mcpReady = dashboardData?.mcp?.statusCounts?.CONNECTED ?? 0
  const showMcp = !dashboardError && mcpTotal > 0

  const issueCount = issuesData != null
    ? (issuesData.criticalCount ?? 0) + (issuesData.warningCount ?? 0)
    : 0
  const showIssues = !issuesError && issuesReady

  const approvalsCount = dashboardData?.approvals?.pendingCount ?? 0
  const showApprovals = !dashboardError && dashboardReady && dashboardData?.approvals != null

  const lastUpdated = dashboardData?.generatedAt ?? issuesData?.generatedAt ?? null
  const lastUpdatedText = formatClockHHMM(lastUpdated)
  const showLastUpdated = lastUpdatedText.length > 0

  // If after gating every chip is hidden, render nothing (vs an empty strip).
  if (!showMcp && !showIssues && !showApprovals && !showLastUpdated) return null

  return (
    <div
      className="global-status-strip"
      role="group"
      aria-label={t('layout.globalStatusStrip.aria.label')}
    >
      {showMcp && (
        <Link
          to="/mcp-servers"
          className="global-status-strip__chip"
          data-chip="mcp"
          aria-label={t('layout.globalStatusStrip.aria.mcp', { ready: mcpReady, total: mcpTotal })}
        >
          <span className="global-status-strip__chip-label">
            {t('layout.globalStatusStrip.mcpLabel')}
          </span>
          <span className="global-status-strip__chip-value">
            {t('layout.globalStatusStrip.mcpValue', { ready: mcpReady, total: mcpTotal })}
          </span>
        </Link>
      )}
      {showIssues && (
        <Link
          to="/issues"
          className="global-status-strip__chip"
          data-chip="issues"
          data-active={issueCount > 0 ? 'true' : 'false'}
          aria-label={t('layout.globalStatusStrip.aria.issues', { count: issueCount })}
        >
          <span className="global-status-strip__chip-label">
            {t('layout.globalStatusStrip.issuesLabel')}
          </span>
          <span className="global-status-strip__chip-value">
            {issueCount}
          </span>
        </Link>
      )}
      {showApprovals && (
        <Link
          to="/approvals"
          className="global-status-strip__chip"
          data-chip="approvals"
          data-active={approvalsCount > 0 ? 'true' : 'false'}
          aria-label={t('layout.globalStatusStrip.aria.approvals', { count: approvalsCount })}
        >
          <span className="global-status-strip__chip-label">
            {t('layout.globalStatusStrip.approvalsLabel')}
          </span>
          <span className="global-status-strip__chip-value">
            {approvalsCount}
          </span>
        </Link>
      )}
      {showLastUpdated && (
        <span
          className="global-status-strip__chip global-status-strip__chip--static"
          data-chip="last-updated"
          aria-label={t('layout.globalStatusStrip.aria.lastUpdated', { time: lastUpdatedText })}
        >
          <span className="global-status-strip__chip-label">
            {t('layout.globalStatusStrip.lastUpdatedLabel')}
          </span>
          <span className="global-status-strip__chip-value">
            {lastUpdatedText}
          </span>
        </span>
      )}
    </div>
  )
}
