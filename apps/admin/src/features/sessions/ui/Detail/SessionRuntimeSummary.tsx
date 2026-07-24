import { useTranslation } from 'react-i18next'
import { Tooltip } from '../../../../shared/ui'
import type { SessionDetailData } from '../../types'

interface SessionRuntimeSummaryProps {
  session: SessionDetailData
}

function compactId(value: string | undefined): string {
  if (!value) return '—'
  const normalized = value.replace(/^(run|trace|thread)[_-]?/i, '')
  return `#${(normalized || value).slice(0, 8).toUpperCase()}`
}

export function SessionRuntimeSummary({ session }: SessionRuntimeSummaryProps) {
  const { t } = useTranslation()
  const runtime = session.runtime

  const hasRuntimeEvidence = Boolean(
    session.threadId ||
      session.traceId ||
      runtime?.runtime ||
      runtime?.graph ||
      runtime?.graphProfile ||
      runtime?.modelProvider ||
      runtime?.model ||
      runtime?.approvalStatus ||
      runtime?.outputGuardStatus ||
      runtime?.hooksStatus ||
      runtime?.stopReason ||
      runtime?.tokenUsage,
  )

  if (!hasRuntimeEvidence) return null

  const facts = [
    [t('conversations.detail.runtime.thread'), session.threadId, true],
    [t('conversations.detail.runtime.trace'), session.traceId, true],
    [t('conversations.detail.runtime.graph'), runtime?.graph, false],
    [t('conversations.detail.runtime.profile'), runtime?.graphProfile, false],
    [t('conversations.detail.runtime.provider'), runtime?.modelProvider, false],
    [t('conversations.detail.runtime.model'), runtime?.model, false],
  ] as const

  const lifecycle = [
    [t('conversations.detail.runtime.approval'), runtime?.approvalStatus],
    [t('conversations.detail.runtime.outputGuard'), runtime?.outputGuardStatus],
    [t('conversations.detail.runtime.hooks'), runtime?.hooksStatus],
    [t('conversations.detail.runtime.stopReason'), runtime?.stopReason],
  ] as const

  function lifecycleLabel(value: string): string {
    const key = value.toLowerCase().replaceAll(' ', '_')
    const supported = ['not_required', 'allowed', 'completed', 'blocked', 'failed', 'pending']
    return supported.includes(key) ? t(`conversations.detail.runtime.values.${key}`) : t('conversations.status.unknown')
  }

  return (
    <section className="session-runtime" aria-labelledby="session-runtime-title">
      <div className="session-section-heading">
        <h2 id="session-runtime-title">{t('conversations.detail.runtime.title')}</h2>
        {runtime?.runtime && <span>{runtime.runtime}</span>}
      </div>

      <dl className="session-runtime-facts">
        {facts.map(([label, value, isId]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              {isId && value ? (
                <Tooltip content={value}><span className="data-mono">{compactId(value)}</span></Tooltip>
              ) : value ?? '—'}
            </dd>
          </div>
        ))}
      </dl>

      <div className="session-runtime-lifecycle" aria-label={t('conversations.detail.runtime.lifecycle')}>
        {lifecycle.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            {value ? <span className="session-status-text">{lifecycleLabel(value)}</span> : <span>—</span>}
          </div>
        ))}
      </div>

      {runtime?.tokenUsage && (
        <dl className="session-token-usage">
          <div><dt>{t('conversations.detail.runtime.inputTokens')}</dt><dd>{runtime.tokenUsage.inputTokens.toLocaleString()}</dd></div>
          <div><dt>{t('conversations.detail.runtime.outputTokens')}</dt><dd>{runtime.tokenUsage.outputTokens.toLocaleString()}</dd></div>
          <div><dt>{t('conversations.detail.runtime.totalTokens')}</dt><dd>{runtime.tokenUsage.totalTokens.toLocaleString()}</dd></div>
        </dl>
      )}
    </section>
  )
}
