import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { CollapsibleSection } from '../../../shared/ui/CollapsibleSection'
import { CopyButton } from '../../../shared/ui/CopyButton'
import { SkeletonText } from '../../../shared/ui/Skeleton'
import { Tooltip } from '../../../shared/ui/Tooltip'
import { useAnnouncer } from '../../../shared/ui/LiveAnnouncer'
import { queryKeys } from '../../../shared/lib/queryKeys'
import { STALE_TIMES } from '../../../shared/lib/staleTimes'
import { getAgentSpecSystemPrompt } from '../api'

export interface SystemPromptSectionProps {
  /** Agent spec id whose resolved system prompt should be revealed. */
  specId: string
}

/**
 * Reveal-style viewer for the resolved system prompt of an agent spec.
 *
 * Behaviour:
 * - Collapsed by default; the audit-log pill is shown next to the toggle so
 *   admins are warned BEFORE expanding (the BE writes an audit entry on every
 *   GET to /api/admin/agent-specs/{id}/system-prompt).
 * - First expansion triggers the fetch. The query uses `staleTime: Infinity`
 *   and `gcTime: Infinity` so collapsing + re-expanding does NOT re-call the
 *   endpoint and re-write the audit log.
 * - A manual refresh button explicitly opts back in to a re-fetch (and a new
 *   audit-log entry).
 * - The body is wrapped in a `role="region"` with `tabIndex={0}` and an
 *   explicit `aria-label` so keyboard users can scroll it without trapping
 *   focus and assistive tech announces it as a discrete landmark.
 */
export function SystemPromptSection({ specId }: SystemPromptSectionProps) {
  const { t } = useTranslation()
  const { announce } = useAnnouncer()
  const [expanded, setExpanded] = useState(false)

  const query = useQuery({
    queryKey: queryKeys.reactorUniverse.systemPrompt(specId),
    queryFn: () => getAgentSpecSystemPrompt(specId),
    enabled: expanded,
    staleTime: STALE_TIMES.IMMUTABLE,
    gcTime: Infinity,
  })
  const systemPrompt = query.data?.systemPrompt ?? ''

  function handleToggle(open: boolean) {
    setExpanded(open)
  }

  function handleRefresh() {
    void query.refetch()
    announce(t('reactorUniverse.systemPrompt.refreshAnnouncement'))
  }

  return (
    <CollapsibleSection
      bodyId={`system-prompt-body-${specId}`}
      onToggle={handleToggle}
      title={
        <span className="system-prompt-section__title">
          <span>{t('reactorUniverse.systemPrompt.toggle')}</span>
          <Tooltip content={t('reactorUniverse.systemPrompt.auditPillTooltip')}>
            <span
              className="system-prompt-section__audit-note"
              aria-label={t('reactorUniverse.systemPrompt.auditPillAriaLabel')}
            >
              {t('reactorUniverse.systemPrompt.auditPillLabel')}
            </span>
          </Tooltip>
        </span>
      }
    >
      <div className="system-prompt-section__body">
        {query.isPending && expanded && (
          <div aria-live="polite" aria-label={t('reactorUniverse.systemPrompt.loading')}>
            <SkeletonText lines={6} />
          </div>
        )}

        {query.isError && (
          <div className="system-prompt-section__error" role="alert">
            <AlertTriangle size={16} aria-hidden="true" />
            <span>{t('reactorUniverse.systemPrompt.error')}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void query.refetch()}
            >
              {t('reactorUniverse.systemPrompt.errorRetry')}
            </button>
          </div>
        )}

        {query.data && (
          <>
            <div className="system-prompt-section__toolbar">
              <CopyButton
                value={systemPrompt}
                label={t('reactorUniverse.systemPrompt.copyButtonLabel')}
              />
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={handleRefresh}
                disabled={query.isFetching}
              >
                <RefreshCw size={14} aria-hidden="true" />
                <span>{t('reactorUniverse.systemPrompt.refresh')}</span>
              </button>
            </div>
            {systemPrompt ? (
              <div
                role="region"
                tabIndex={0}
                aria-label={t('reactorUniverse.systemPrompt.regionLabel')}
                className="system-prompt-section__prompt"
              >
                {query.data.systemPrompt}
              </div>
            ) : (
              <p className="system-prompt-section__empty">
                {t('reactorUniverse.systemPrompt.empty')}
              </p>
            )}
          </>
        )}
      </div>
    </CollapsibleSection>
  )
}
